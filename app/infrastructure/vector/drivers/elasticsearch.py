"""使用 AsyncElasticsearch 和 dense_vector 适配统一向量协议。"""

from collections.abc import Awaitable, Mapping, Sequence
from functools import partial
from typing import cast

from elastic_transport import ObjectApiResponse
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ApiError, ConflictError, NotFoundError
from elasticsearch.exceptions import ConnectionError as ElasticsearchConnectionError

from app.config.vector import ElasticsearchVectorSettings, parse_vector_connection
from app.infrastructure.vector.contracts.provider import VectorResourceDefinition
from app.infrastructure.vector.errors import (
    VectorCollectionConflictError,
    VectorCollectionNotFoundError,
    VectorConnectionError,
    VectorOperationError,
)
from app.infrastructure.vector.models import (
    MetadataScalar,
    VectorCollectionInfo,
    VectorCollectionSpec,
    VectorFilters,
    VectorMatch,
    VectorMetric,
    VectorPoint,
    validate_collection_name,
    validate_filters,
    validate_ids,
    validate_limit,
    validate_points,
    validate_query_vector,
)
from app.infrastructure.vector.resource import VectorResource

_METRICS: dict[VectorMetric, str] = {
    VectorMetric.COSINE: "cosine",
    VectorMetric.DOT_PRODUCT: "max_inner_product",
    VectorMetric.L2: "l2_norm",
}
_METRICS_FROM_ELASTICSEARCH = {value: key for key, value in _METRICS.items()}


class ElasticsearchVectorClient:
    """把 Elasticsearch Index 映射为公共向量 Collection。"""

    def __init__(self, client: AsyncElasticsearch) -> None:
        """保存异步客户端；构造过程本身不连接集群。"""

        self._client = client

    async def ping(self) -> bool:
        """调用 Elasticsearch ping 检查集群可访问性。"""

        try:
            return bool(await self._client.ping())
        except ElasticsearchConnectionError as error:
            raise VectorConnectionError("Elasticsearch 集群不可用") from error

    async def create_collection(self, spec: VectorCollectionSpec) -> None:
        """创建保留原始向量且支持 kNN 的 Elasticsearch Index。"""

        if await self.has_collection(spec.name):
            raise VectorCollectionConflictError(f"Elasticsearch Index {spec.name!r} 已存在")
        try:
            await self._call(
                self._client.indices.create(
                    index=spec.name,
                    settings={"index.mapping.exclude_source_vectors": False},
                    mappings={
                        "dynamic": "strict",
                        "properties": {
                            "vector": {
                                "type": "dense_vector",
                                "dims": spec.dimension,
                                "index": True,
                                "similarity": _METRICS[spec.metric],
                            },
                            "metadata": {"type": "flattened"},
                        },
                    },
                )
            )
        except VectorCollectionConflictError as error:
            raise VectorCollectionConflictError(f"Elasticsearch Index {spec.name!r} 已存在") from error

    async def has_collection(self, name: str) -> bool:
        """判断 Elasticsearch Index 是否存在。"""

        validate_collection_name(name)
        try:
            return bool(await self._call(self._client.indices.exists(index=name)))
        except VectorCollectionNotFoundError:
            return False

    async def describe_collection(self, name: str) -> VectorCollectionInfo:
        """从 Index mapping 解析 dense_vector 维度和相似度配置。"""

        await self._require_collection(name)
        response = await self._call(self._client.indices.get_mapping(index=name))
        mapping = _response_mapping(response)
        try:
            vector_mapping = cast(
                Mapping[str, object],
                cast(Mapping[str, object], cast(Mapping[str, object], mapping[name])["mappings"])["properties"],
            )["vector"]
        except (KeyError, TypeError) as error:
            raise VectorOperationError(f"Elasticsearch Index {name!r} 缺少公共 vector mapping") from error
        if not isinstance(vector_mapping, Mapping):
            raise VectorOperationError(f"Elasticsearch Index {name!r} 的 vector mapping 不合法")
        dimension = vector_mapping.get("dims")
        metric_value = vector_mapping.get("similarity")
        metric = _METRICS_FROM_ELASTICSEARCH.get(str(metric_value))
        if not isinstance(dimension, int) or metric is None:
            raise VectorOperationError(f"Elasticsearch Index {name!r} 的向量结构不受支持")
        return VectorCollectionInfo(name=name, dimension=dimension, metric=metric)

    async def delete_collection(self, name: str) -> None:
        """删除 Elasticsearch Index。"""

        await self._require_collection(name)
        try:
            await self._call(self._client.indices.delete(index=name))
        except VectorCollectionNotFoundError as error:
            raise VectorCollectionNotFoundError(f"Elasticsearch Index {name!r} 不存在") from error

    async def upsert(self, collection: str, points: tuple[VectorPoint, ...]) -> None:
        """使用 Bulk API 按文档 ID 插入或覆盖向量。"""

        validate_collection_name(collection)
        validate_points(points)
        if not points:
            return
        await self._require_collection(collection)
        operations: list[dict[str, object]] = []
        for point in points:
            operations.append({"index": {"_index": collection, "_id": point.id}})
            operations.append({"vector": list(point.vector), "metadata": dict(point.metadata)})
        response = await self._call(self._client.bulk(operations=operations, refresh="wait_for"))
        _raise_bulk_failures(_response_mapping(response), ignored_statuses=frozenset())

    async def get(self, collection: str, ids: tuple[str, ...]) -> tuple[VectorPoint, ...]:
        """通过 Multi Get 读取向量，并恢复调用方 ID 顺序。"""

        validate_collection_name(collection)
        validate_ids(ids)
        if not ids:
            return ()
        await self._require_collection(collection)
        response = await self._call(self._client.mget(index=collection, ids=list(ids)))
        documents = _response_mapping(response).get("docs")
        if not isinstance(documents, Sequence):
            raise VectorOperationError("Elasticsearch Multi Get 返回结构不合法")
        points = {point.id: point for point in (_elasticsearch_point(document) for document in documents if _is_found(document))}
        return tuple(points[point_id] for point_id in ids if point_id in points)

    async def delete(self, collection: str, ids: tuple[str, ...]) -> None:
        """通过 Bulk API 幂等删除一批向量文档。"""

        validate_collection_name(collection)
        validate_ids(ids)
        if not ids:
            return
        await self._require_collection(collection)
        operations = [{"delete": {"_index": collection, "_id": point_id}} for point_id in ids]
        response = await self._call(self._client.bulk(operations=operations, refresh="wait_for"))
        _raise_bulk_failures(_response_mapping(response), ignored_statuses=frozenset((404,)))

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilters | None = None,
    ) -> tuple[VectorMatch, ...]:
        """使用 dense_vector kNN 和 flattened term filter 检索近邻。"""

        validate_collection_name(collection)
        validate_query_vector(vector)
        validate_limit(limit)
        validate_filters(filters)
        await self._require_collection(collection)
        knn: dict[str, object] = {
            "field": "vector",
            "query_vector": list(vector),
            "k": limit,
            "num_candidates": min(max(limit * 10, 100), 10_000),
        }
        if filters:
            knn["filter"] = [{"term": {f"metadata.{key}": value}} for key, value in filters.items()]
        response = await self._call(
            self._client.search(
                index=collection,
                knn=knn,
                size=limit,
                source={"includes": ["metadata"], "excludes": ["vector"]},
            )
        )
        return _elasticsearch_matches(_response_mapping(response))

    async def aclose(self) -> None:
        """关闭 Elasticsearch aiohttp 连接池。"""

        await self._client.close()

    async def _require_collection(self, name: str) -> None:
        if not await self.has_collection(name):
            raise VectorCollectionNotFoundError(f"Elasticsearch Index {name!r} 不存在")

    @staticmethod
    async def _call[T](operation: Awaitable[T]) -> T:
        try:
            return await operation
        except NotFoundError as error:
            raise VectorCollectionNotFoundError("Elasticsearch Index 不存在") from error
        except ConflictError as error:
            raise VectorCollectionConflictError("Elasticsearch Index 已存在或发生版本冲突") from error
        except ElasticsearchConnectionError as error:
            raise VectorConnectionError("Elasticsearch 集群不可用") from error
        except ApiError as error:
            raise VectorOperationError("Elasticsearch 操作失败") from error


class ElasticsearchVectorProvider:
    """创建配置严格且连接延迟建立的 AsyncElasticsearch。"""

    driver = "elasticsearch"

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        """校验 Elasticsearch 配置并返回延迟资源工厂。"""

        settings = parse_vector_connection(raw_config)
        if not isinstance(settings, ElasticsearchVectorSettings):
            raise ValueError("配置不是 Elasticsearch 连接")
        return VectorResourceDefinition(factory=partial(_create_resource, settings))


async def _create_resource(settings: ElasticsearchVectorSettings) -> VectorResource:
    basic_auth = None
    if settings.username is not None and settings.password is not None:
        basic_auth = (settings.username, settings.password.get_secret_value())
    hosts = [{"scheme": "https" if settings.ssl else "http", "host": settings.host, "port": settings.port}]
    if settings.ca_certs is None:
        client = AsyncElasticsearch(
            hosts=hosts,
            basic_auth=basic_auth,
            verify_certs=settings.verify_certs,
            request_timeout=settings.timeout,
            connections_per_node=settings.connections_per_node,
            max_retries=settings.max_retries,
            retry_on_timeout=settings.retry_on_timeout,
        )
    else:
        client = AsyncElasticsearch(
            hosts=hosts,
            basic_auth=basic_auth,
            verify_certs=settings.verify_certs,
            ca_certs=settings.ca_certs,
            request_timeout=settings.timeout,
            connections_per_node=settings.connections_per_node,
            max_retries=settings.max_retries,
            retry_on_timeout=settings.retry_on_timeout,
        )
    return VectorResource(ElasticsearchVectorClient(client))


def _response_mapping(response: object) -> Mapping[str, object]:
    if isinstance(response, Mapping):
        return cast(Mapping[str, object], response)
    if isinstance(response, ObjectApiResponse) and isinstance(response.body, Mapping):
        return cast(Mapping[str, object], response.body)
    raise VectorOperationError("Elasticsearch 返回结构不合法")


def _is_found(document: object) -> bool:
    return isinstance(document, Mapping) and document.get("found") is True


def _elasticsearch_point(document: object) -> VectorPoint:
    if not isinstance(document, Mapping):
        raise VectorOperationError("Elasticsearch 返回了不合法的文档")
    point_id = document.get("_id")
    source = document.get("_source")
    if not isinstance(point_id, str) or not isinstance(source, Mapping):
        raise VectorOperationError("Elasticsearch 文档缺少 ID 或 _source")
    vector = source.get("vector")
    metadata = source.get("metadata", {})
    if not isinstance(vector, Sequence) or not isinstance(metadata, Mapping):
        raise VectorOperationError("Elasticsearch 文档缺少公共向量结构")
    return VectorPoint(
        id=point_id,
        vector=tuple(float(value) for value in vector),
        metadata=cast(Mapping[str, MetadataScalar], metadata),
    )


def _elasticsearch_matches(response: Mapping[str, object]) -> tuple[VectorMatch, ...]:
    hits_wrapper = response.get("hits")
    hits = hits_wrapper.get("hits") if isinstance(hits_wrapper, Mapping) else None
    if not isinstance(hits, Sequence):
        raise VectorOperationError("Elasticsearch 检索结果结构不合法")

    matches: list[VectorMatch] = []
    for hit in hits:
        if not isinstance(hit, Mapping):
            raise VectorOperationError("Elasticsearch 返回了不合法的命中")
        point_id = hit.get("_id")
        score = hit.get("_score")
        source = hit.get("_source", {})
        metadata = source.get("metadata", {}) if isinstance(source, Mapping) else None
        if not isinstance(point_id, str) or not isinstance(score, int | float) or not isinstance(metadata, Mapping):
            raise VectorOperationError("Elasticsearch 命中缺少公共向量结构")
        matches.append(VectorMatch(id=point_id, score=float(score), metadata=cast(Mapping[str, MetadataScalar], metadata)))
    return tuple(matches)


def _raise_bulk_failures(response: Mapping[str, object], *, ignored_statuses: frozenset[int]) -> None:
    items = response.get("items")
    if not isinstance(items, Sequence):
        raise VectorOperationError("Elasticsearch Bulk 返回结构不合法")
    for item in items:
        if not isinstance(item, Mapping) or not item:
            raise VectorOperationError("Elasticsearch Bulk 条目结构不合法")
        result = next(iter(item.values()))
        status = result.get("status") if isinstance(result, Mapping) else None
        if isinstance(status, int) and (status < 300 or status in ignored_statuses):
            continue
        raise VectorOperationError("Elasticsearch Bulk 操作包含失败条目")
