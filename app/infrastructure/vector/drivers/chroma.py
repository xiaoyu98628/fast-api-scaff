"""使用 Chroma PersistentClient 和 AsyncHttpClient 适配统一向量协议。"""

from base64 import b64encode
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import partial
from typing import cast

import chromadb
import httpx
from anyio import CapacityLimiter, to_thread
from chromadb.api import AsyncClientAPI, ClientAPI
from chromadb.errors import ChromaError, NotFoundError, UniqueConstraintError

from app.config.vector import ChromaLocalVectorSettings, ChromaRemoteVectorSettings, parse_vector_connection
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
    validate_limit,
    validate_query_vector,
)
from app.infrastructure.vector.resource import VectorResource

type ChromaResult = object

_DIMENSION_METADATA = "_vector_dimension"
_METRIC_METADATA = "_vector_metric"
_RECORD_METADATA = "_vector_record"
_METRICS: dict[VectorMetric, str] = {
    VectorMetric.COSINE: "cosine",
    VectorMetric.DOT_PRODUCT: "ip",
    VectorMetric.L2: "l2",
}


class _ChromaBackend:
    """把同步本地和异步远程 Chroma API 收敛为等待接口。"""

    def __init__(self, client: ClientAPI | AsyncClientAPI, *, local: bool) -> None:
        """保存客户端，并为本地同步模式配置串行线程限制器。"""

        self._client = client
        self._local = local
        self._limiter = CapacityLimiter(1) if local else None

    async def client_call(self, method: str, /, **kwargs: object) -> ChromaResult:
        """调用客户端方法并保留可稳定识别的资源异常。"""

        operation = getattr(self._client, method)
        return await self._call(operation, **kwargs)

    async def collection_call(self, collection: object, method: str, /, **kwargs: object) -> ChromaResult:
        """调用同步或异步 Collection 方法。"""

        operation = getattr(collection, method)
        return await self._call(operation, **kwargs)

    async def aclose(self) -> None:
        """完成统一关闭入口；Chroma 当前客户端没有公开 close 方法。"""

    async def _call(self, operation: object, /, **kwargs: object) -> ChromaResult:
        try:
            if self._local:
                sync_operation = cast(Callable[..., ChromaResult], operation)
                assert self._limiter is not None
                return await to_thread.run_sync(
                    partial(sync_operation, **kwargs),
                    abandon_on_cancel=False,
                    limiter=self._limiter,
                )
            async_operation = cast(Callable[..., Awaitable[ChromaResult]], operation)
            return await async_operation(**kwargs)
        except NotFoundError as error:
            raise VectorCollectionNotFoundError("Chroma Collection 不存在") from error
        except UniqueConstraintError as error:
            raise VectorCollectionConflictError("Chroma Collection 已存在") from error
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as error:
            raise VectorConnectionError("Chroma 客户端无法访问目标存储") from error
        except ChromaError as error:
            raise VectorOperationError("Chroma 操作失败") from error


class ChromaVectorClient:
    """把 Chroma Collection 映射为公共异步向量客户端。"""

    def __init__(self, backend: _ChromaBackend) -> None:
        """保存已经创建的本地或远程 Chroma 后端。"""

        self._backend = backend

    async def ping(self) -> bool:
        """调用 Chroma heartbeat 验证资源可访问。"""

        await self._backend.client_call("heartbeat")
        return True

    async def create_collection(self, spec: VectorCollectionSpec) -> None:
        """创建禁用内置 Embedding、记录公共结构信息的 HNSW Collection。"""

        if await self.has_collection(spec.name):
            raise VectorCollectionConflictError(f"Chroma Collection {spec.name!r} 已存在")
        try:
            await self._backend.client_call(
                "create_collection",
                name=spec.name,
                configuration={"hnsw": {"space": _METRICS[spec.metric]}},
                metadata={_DIMENSION_METADATA: spec.dimension, _METRIC_METADATA: spec.metric.value},
                embedding_function=None,
            )
        except VectorCollectionConflictError as error:
            raise VectorCollectionConflictError(f"Chroma Collection {spec.name!r} 已存在") from error

    async def has_collection(self, name: str) -> bool:
        """判断 Chroma Collection 是否存在。"""

        validate_collection_name(name)
        try:
            await self._get_collection(name)
        except VectorCollectionNotFoundError:
            return False
        return True

    async def describe_collection(self, name: str) -> VectorCollectionInfo:
        """读取创建时持久化在 Collection metadata 中的公共结构。"""

        collection = await self._require_collection(name)
        metadata = getattr(collection, "metadata", None)
        if not isinstance(metadata, dict):
            raise VectorOperationError(f"Chroma Collection {name!r} 缺少公共结构元数据")
        dimension = metadata.get(_DIMENSION_METADATA)
        metric_value = metadata.get(_METRIC_METADATA)
        if not isinstance(dimension, int) or not isinstance(metric_value, str):
            raise VectorOperationError(f"Chroma Collection {name!r} 不是由公共向量接口创建")
        try:
            metric = VectorMetric(metric_value)
        except ValueError as error:
            raise VectorOperationError(f"Chroma Collection {name!r} 使用了不支持的距离算法") from error
        return VectorCollectionInfo(name=name, dimension=dimension, metric=metric)

    async def delete_collection(self, name: str) -> None:
        """删除 Chroma Collection。"""

        await self._require_collection(name)
        await self._backend.client_call("delete_collection", name=name)

    async def upsert(self, collection: str, points: tuple[VectorPoint, ...]) -> None:
        """写入调用方提供的向量和标量元数据。"""

        validate_collection_name(collection)
        if not points:
            return
        target = await self._require_collection(collection)
        await self._backend.collection_call(
            target,
            "upsert",
            ids=[point.id for point in points],
            embeddings=[list(point.vector) for point in points],
            metadatas=[{_RECORD_METADATA: True, **dict(point.metadata)} for point in points],
        )

    async def get(self, collection: str, ids: tuple[str, ...]) -> tuple[VectorPoint, ...]:
        """读取 Chroma 向量，并按调用方 ID 顺序返回存在项。"""

        validate_collection_name(collection)
        if not ids:
            return ()
        target = await self._require_collection(collection)
        result = cast(
            Mapping[str, object],
            await self._backend.collection_call(target, "get", ids=list(ids), include=["embeddings", "metadatas"]),
        )
        points = {point.id: point for point in _chroma_points(result)}
        return tuple(points[point_id] for point_id in ids if point_id in points)

    async def delete(self, collection: str, ids: tuple[str, ...]) -> None:
        """按 ID 幂等删除 Chroma 向量。"""

        validate_collection_name(collection)
        if not ids:
            return
        target = await self._require_collection(collection)
        await self._backend.collection_call(target, "delete", ids=list(ids))

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilters | None = None,
    ) -> tuple[VectorMatch, ...]:
        """执行 Chroma 近邻查询并统一为高分优先结果。"""

        validate_collection_name(collection)
        validate_query_vector(vector)
        validate_limit(limit)
        validate_filters(filters)
        target = await self._require_collection(collection)
        result = cast(
            Mapping[str, object],
            await self._backend.collection_call(
                target,
                "query",
                query_embeddings=[list(vector)],
                n_results=limit,
                where=dict(filters) if filters else None,
                include=["metadatas", "distances"],
            ),
        )
        return _chroma_matches(result)

    async def aclose(self) -> None:
        """执行 Chroma 后端的统一关闭入口。"""

        await self._backend.aclose()

    async def _get_collection(self, name: str) -> object:
        return await self._backend.client_call("get_collection", name=name, embedding_function=None)

    async def _require_collection(self, name: str) -> object:
        validate_collection_name(name)
        try:
            return await self._get_collection(name)
        except VectorCollectionNotFoundError as error:
            raise VectorCollectionNotFoundError(f"Chroma Collection {name!r} 不存在") from error


class ChromaVectorProvider:
    """根据 mode 创建 Chroma 本地持久化或远程异步客户端。"""

    driver = "chroma"

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        """严格校验 Chroma 配置并返回延迟资源工厂。"""

        settings = parse_vector_connection(raw_config)
        if isinstance(settings, ChromaLocalVectorSettings):
            return VectorResourceDefinition(factory=partial(_create_local_resource, settings))
        if isinstance(settings, ChromaRemoteVectorSettings):
            return VectorResourceDefinition(factory=partial(_create_remote_resource, settings))
        raise ValueError("配置不是 Chroma 连接")


async def _create_local_resource(settings: ChromaLocalVectorSettings) -> VectorResource:
    path = settings.resolved_path
    limiter = CapacityLimiter(1)
    try:
        client = await to_thread.run_sync(
            partial(chromadb.PersistentClient, path=path, tenant=settings.tenant, database=settings.database),
            abandon_on_cancel=False,
            limiter=limiter,
        )
    except (ChromaError, OSError) as error:
        raise VectorConnectionError(f"无法打开 Chroma 本地目录 {path}") from error
    return VectorResource(ChromaVectorClient(_ChromaBackend(client, local=True)))


async def _create_remote_resource(settings: ChromaRemoteVectorSettings) -> VectorResource:
    headers = _chroma_headers(settings)
    try:
        client = await chromadb.AsyncHttpClient(
            host=settings.host,
            port=settings.port,
            ssl=settings.ssl,
            headers=headers or None,
            tenant=settings.tenant,
            database=settings.database,
        )
    except (ChromaError, httpx.HTTPError, OSError) as error:
        raise VectorConnectionError(f"无法创建远程 Chroma 客户端 {settings.host}:{settings.port}") from error
    return VectorResource(ChromaVectorClient(_ChromaBackend(client, local=False)))


def _chroma_headers(settings: ChromaRemoteVectorSettings) -> dict[str, str]:
    if settings.api_key is not None:
        return {"x-chroma-token": settings.api_key.get_secret_value()}
    if settings.username is None or settings.password is None:
        return {}
    credentials = f"{settings.username}:{settings.password.get_secret_value()}".encode()
    return {"Authorization": f"Basic {b64encode(credentials).decode()}"}


def _chroma_points(result: Mapping[str, object]) -> tuple[VectorPoint, ...]:
    ids = _sequence(result.get("ids"))
    embeddings = _sequence(result.get("embeddings"))
    metadatas = _sequence(result.get("metadatas"))
    if len(ids) != len(embeddings):
        raise VectorOperationError("Chroma 返回的 ID 与向量数量不一致")

    points: list[VectorPoint] = []
    for index, (point_id, embedding) in enumerate(zip(ids, embeddings, strict=True)):
        if not isinstance(point_id, str) or not isinstance(embedding, Sequence):
            raise VectorOperationError("Chroma 返回了不符合公共结构的向量")
        metadata = metadatas[index] if index < len(metadatas) else {}
        points.append(
            VectorPoint(
                id=point_id,
                vector=tuple(float(value) for value in embedding),
                metadata=_clean_chroma_metadata(metadata),
            )
        )
    return tuple(points)


def _chroma_matches(result: Mapping[str, object]) -> tuple[VectorMatch, ...]:
    ids = _first_sequence(result.get("ids"))
    distances = _first_sequence(result.get("distances"))
    metadatas = _first_sequence(result.get("metadatas"))
    if len(ids) != len(distances):
        raise VectorOperationError("Chroma 返回的 ID 与距离数量不一致")

    matches: list[VectorMatch] = []
    for index, (point_id, distance) in enumerate(zip(ids, distances, strict=True)):
        if not isinstance(point_id, str) or not isinstance(distance, int | float):
            raise VectorOperationError("Chroma 返回了不符合公共结构的检索结果")
        metadata = metadatas[index] if index < len(metadatas) else {}
        matches.append(VectorMatch(id=point_id, score=-float(distance), metadata=_clean_chroma_metadata(metadata)))
    return tuple(matches)


def _clean_chroma_metadata(value: object) -> dict[str, MetadataScalar]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise VectorOperationError("Chroma 返回了不符合公共结构的元数据")
    return cast(dict[str, MetadataScalar], {key: item for key, item in value.items() if key != _RECORD_METADATA})


def _sequence(value: object) -> Sequence[object]:
    if value is None:
        return ()
    if isinstance(value, Sequence):
        return value
    converter = getattr(value, "tolist", None)
    if callable(converter):
        converted = converter()
        if isinstance(converted, Sequence):
            return converted
    raise VectorOperationError("Chroma 返回了无法解析的序列")


def _first_sequence(value: object) -> Sequence[object]:
    outer = _sequence(value)
    return _sequence(outer[0]) if outer else ()
