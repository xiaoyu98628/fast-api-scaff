"""使用 PyMilvus 适配本地 Milvus Lite 和远程 Milvus 服务。"""

import json
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache, partial
from importlib import import_module
from threading import Lock
from typing import Protocol, cast

from anyio import CapacityLimiter, to_thread

from app.config.vector import MilvusLocalVectorSettings, MilvusRemoteVectorSettings, parse_vector_connection
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

type MilvusResult = dict[str, object] | list[object] | str | int | bool | None
type MilvusClientFactory = Callable[..., object]

_METRICS: dict[VectorMetric, str] = {
    VectorMetric.COSINE: "COSINE",
    VectorMetric.DOT_PRODUCT: "IP",
    VectorMetric.L2: "L2",
}
_METRICS_FROM_MILVUS = {value: key for key, value in _METRICS.items()}
_RESERVED_FIELDS = frozenset(("id", "vector"))
_SDK_IMPORT_LOCK = Lock()


class _SyncMilvusClient(Protocol):
    """声明本地后端实际使用的同步客户端能力。"""

    def close(self) -> None:
        """关闭本地客户端。"""

        ...


class _AsyncMilvusClient(Protocol):
    """声明远程后端实际使用的异步客户端能力。"""

    async def close(self) -> None:
        """关闭远程客户端。"""

        ...


@dataclass(frozen=True, slots=True)
class _MilvusSdk:
    """保存延迟导入的 PyMilvus 构造器和异常类型。"""

    sync_client: MilvusClientFactory
    async_client: MilvusClientFactory
    connection_errors: tuple[type[Exception], ...]
    operation_errors: tuple[type[Exception], ...]


class _MilvusBackend(Protocol):
    """把同步和异步 PyMilvus 客户端收敛为统一等待接口。"""

    async def call(self, method: str, /, **kwargs: object) -> MilvusResult:
        """调用指定 PyMilvus 方法并转换连接或操作异常。"""

        ...

    async def aclose(self) -> None:
        """释放 PyMilvus 客户端。"""

        ...


class _LocalMilvusBackend:
    """在线程中串行执行 Milvus Lite 同步调用。"""

    def __init__(self, client: _SyncMilvusClient, sdk: _MilvusSdk) -> None:
        """保存本地客户端，并限制同一文件的进程内并发。"""

        self._client = client
        self._sdk = sdk
        self._limiter = CapacityLimiter(1)

    async def call(self, method: str, /, **kwargs: object) -> MilvusResult:
        """把同步调用卸载到工作线程，避免阻塞宿主事件循环。"""

        operation = cast(Callable[..., MilvusResult], getattr(self._client, method))
        try:
            return await to_thread.run_sync(partial(operation, **kwargs), abandon_on_cancel=False, limiter=self._limiter)
        except Exception as error:
            _raise_milvus_error(error, self._sdk, local=True)

    async def aclose(self) -> None:
        """在线程中关闭 Milvus Lite 及其内部回环服务。"""

        await to_thread.run_sync(self._client.close, abandon_on_cancel=False, limiter=self._limiter)


class _RemoteMilvusBackend:
    """通过 AsyncMilvusClient 调用远程 Milvus。"""

    def __init__(self, client: _AsyncMilvusClient, sdk: _MilvusSdk) -> None:
        """保存远程异步客户端。"""

        self._client = client
        self._sdk = sdk

    async def call(self, method: str, /, **kwargs: object) -> MilvusResult:
        """执行异步客户端方法并隔离 PyMilvus 异常。"""

        operation = cast(Callable[..., Awaitable[MilvusResult]], getattr(self._client, method))
        try:
            return await operation(**kwargs)
        except Exception as error:
            _raise_milvus_error(error, self._sdk, local=False)

    async def aclose(self) -> None:
        """关闭远程 Milvus 客户端连接。"""

        await self._client.close()


class MilvusVectorClient:
    """把 Milvus Collection 映射为公共向量客户端。"""

    def __init__(self, backend: _MilvusBackend, *, timeout: float) -> None:
        """保存后端和默认操作超时，不执行网络或文件操作。"""

        self._backend = backend
        self._timeout = timeout
        self._metrics: dict[str, VectorMetric] = {}

    async def ping(self) -> bool:
        """通过列出 Collection 验证 Milvus 可访问。"""

        await self._backend.call("list_collections", timeout=self._timeout)
        return True

    async def create_collection(self, spec: VectorCollectionSpec) -> None:
        """使用字符串主键、动态元数据和 AUTOINDEX 创建 Collection。"""

        if await self.has_collection(spec.name):
            raise VectorCollectionConflictError(f"Milvus Collection {spec.name!r} 已存在")
        await self._backend.call(
            "create_collection",
            collection_name=spec.name,
            dimension=spec.dimension,
            id_type="string",
            metric_type=_METRICS[spec.metric],
            auto_id=False,
            enable_dynamic_field=True,
            timeout=self._timeout,
        )
        self._metrics[spec.name] = spec.metric

    async def has_collection(self, name: str) -> bool:
        """判断 Milvus Collection 是否存在。"""

        validate_collection_name(name)
        result = await self._backend.call("has_collection", collection_name=name, timeout=self._timeout)
        return bool(result)

    async def describe_collection(self, name: str) -> VectorCollectionInfo:
        """从 Collection 字段和向量索引解析维度、距离算法。"""

        await self._require_collection(name)
        description = cast(
            dict[str, object],
            await self._backend.call("describe_collection", collection_name=name, timeout=self._timeout),
        )
        index = cast(
            dict[str, object],
            await self._backend.call("describe_index", collection_name=name, index_name="vector", timeout=self._timeout),
        )
        dimension = _milvus_dimension(description)
        metric = _METRICS_FROM_MILVUS.get(str(index.get("metric_type")))
        if metric is None:
            raise VectorOperationError(f"Milvus Collection {name!r} 使用了不支持的距离算法")
        self._metrics[name] = metric
        return VectorCollectionInfo(name=name, dimension=dimension, metric=metric)

    async def delete_collection(self, name: str) -> None:
        """删除 Milvus Collection，并清理本地结构缓存。"""

        await self._require_collection(name)
        await self._backend.call("drop_collection", collection_name=name, timeout=self._timeout)
        self._metrics.pop(name, None)

    async def upsert(self, collection: str, points: tuple[VectorPoint, ...]) -> None:
        """把公共 Point 转换为 Milvus 动态字段实体。"""

        validate_collection_name(collection)
        validate_points(points)
        if not points:
            return
        await self._require_collection(collection)
        data = [{"id": point.id, "vector": list(point.vector), **dict(point.metadata)} for point in points]
        await self._backend.call("upsert", collection_name=collection, data=data, timeout=self._timeout)

    async def get(self, collection: str, ids: tuple[str, ...]) -> tuple[VectorPoint, ...]:
        """读取 Milvus 实体并恢复调用方 ID 顺序。"""

        validate_collection_name(collection)
        validate_ids(ids)
        if not ids:
            return ()
        await self._require_collection(collection)
        rows = cast(
            list[dict[str, object]],
            await self._backend.call(
                "get",
                collection_name=collection,
                ids=list(ids),
                output_fields=["*"],
                timeout=self._timeout,
            ),
        )
        points = {point.id: point for point in (_milvus_point(row) for row in rows)}
        return tuple(points[point_id] for point_id in ids if point_id in points)

    async def delete(self, collection: str, ids: tuple[str, ...]) -> None:
        """按主键幂等删除 Milvus 实体。"""

        validate_collection_name(collection)
        validate_ids(ids)
        if not ids:
            return
        await self._require_collection(collection)
        await self._backend.call("delete", collection_name=collection, ids=list(ids), timeout=self._timeout)

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilters | None = None,
    ) -> tuple[VectorMatch, ...]:
        """执行 Milvus ANN 检索并把 L2 距离转换为高分优先。"""

        validate_collection_name(collection)
        validate_query_vector(vector)
        validate_limit(limit)
        validate_filters(filters)
        metric = self._metrics.get(collection) or (await self.describe_collection(collection)).metric
        result = cast(
            list[list[dict[str, object]]],
            await self._backend.call(
                "search",
                collection_name=collection,
                data=[list(vector)],
                filter=_milvus_filter(filters),
                limit=limit,
                output_fields=["*"],
                timeout=self._timeout,
            ),
        )
        hits = result[0] if result else []
        return tuple(_milvus_match(hit, metric) for hit in hits)

    async def aclose(self) -> None:
        """关闭同步或异步 Milvus 后端。"""

        await self._backend.aclose()

    async def _require_collection(self, name: str) -> None:
        if not await self.has_collection(name):
            raise VectorCollectionNotFoundError(f"Milvus Collection {name!r} 不存在")


class MilvusVectorProvider:
    """根据 mode 创建本地 Milvus Lite 或远程异步客户端。"""

    driver = "milvus"

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        """严格校验 Milvus 配置并返回延迟工厂。"""

        settings = parse_vector_connection(raw_config)
        if isinstance(settings, MilvusLocalVectorSettings):
            return VectorResourceDefinition(factory=partial(_create_local_resource, settings))
        if isinstance(settings, MilvusRemoteVectorSettings):
            return VectorResourceDefinition(factory=partial(_create_remote_resource, settings))
        raise ValueError("配置不是 Milvus 连接")


async def _create_local_resource(settings: MilvusLocalVectorSettings) -> VectorResource:
    path = settings.resolved_path
    path.parent.mkdir(parents=True, exist_ok=True)
    limiter = CapacityLimiter(1)
    sdk = await to_thread.run_sync(_load_milvus_sdk, abandon_on_cancel=False, limiter=limiter)
    try:
        client = await to_thread.run_sync(partial(sdk.sync_client, str(path)), abandon_on_cancel=False, limiter=limiter)
    except Exception as error:
        if isinstance(error, sdk.operation_errors):
            raise VectorConnectionError(f"无法打开 Milvus Lite 文件 {path}") from error
        raise
    backend = _LocalMilvusBackend(cast(_SyncMilvusClient, client), sdk)
    return VectorResource(MilvusVectorClient(backend, timeout=settings.timeout))


async def _create_remote_resource(settings: MilvusRemoteVectorSettings) -> VectorResource:
    uri = f"{'https' if settings.ssl else 'http'}://{settings.url_host}:{settings.port}"
    sdk = await to_thread.run_sync(_load_milvus_sdk, abandon_on_cancel=False)
    try:
        client = sdk.async_client(
            uri=uri,
            user=settings.username or "",
            password=settings.password.get_secret_value() if settings.password is not None else "",
            db_name=settings.database,
            timeout=settings.timeout,
        )
    except Exception as error:
        if isinstance(error, sdk.operation_errors):
            raise VectorConnectionError(f"无法创建远程 Milvus 客户端 {settings.host}:{settings.port}") from error
        raise
    backend = _RemoteMilvusBackend(cast(_AsyncMilvusClient, client), sdk)
    return VectorResource(MilvusVectorClient(backend, timeout=settings.timeout))


@lru_cache(maxsize=1)
def _load_milvus_sdk() -> _MilvusSdk:
    """导入 PyMilvus，同时阻止其隐式读取并写入项目环境变量。"""

    with _SDK_IMPORT_LOCK:
        previous = os.environ.get("PYTHON_DOTENV_DISABLED")
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        try:
            module = import_module("pymilvus")
            exceptions = import_module("pymilvus.exceptions")
        finally:
            if previous is None:
                os.environ.pop("PYTHON_DOTENV_DISABLED", None)
            else:
                os.environ["PYTHON_DOTENV_DISABLED"] = previous

    return _MilvusSdk(
        sync_client=cast(MilvusClientFactory, getattr(module, "MilvusClient")),
        async_client=cast(MilvusClientFactory, getattr(module, "AsyncMilvusClient")),
        connection_errors=(
            cast(type[Exception], getattr(exceptions, "ConnectionConfigException")),
            cast(type[Exception], getattr(exceptions, "MilvusUnavailableException")),
        ),
        operation_errors=(cast(type[Exception], getattr(exceptions, "MilvusException")),),
    )


def _raise_milvus_error(error: Exception, sdk: _MilvusSdk, *, local: bool) -> None:
    if isinstance(error, sdk.connection_errors):
        target = "Milvus Lite 客户端" if local else "远程 Milvus"
        raise VectorConnectionError(f"{target}不可用") from error
    if isinstance(error, sdk.operation_errors):
        target = "Milvus Lite" if local else "远程 Milvus"
        raise VectorOperationError(f"{target}操作失败") from error
    raise error


def _milvus_dimension(description: Mapping[str, object]) -> int:
    fields = description.get("fields")
    if not isinstance(fields, list):
        raise VectorOperationError("Milvus Collection 描述缺少 fields")
    for field in fields:
        if not isinstance(field, dict) or field.get("name") != "vector":
            continue
        params = field.get("params")
        if isinstance(params, dict) and isinstance(params.get("dim"), int):
            return params["dim"]
    raise VectorOperationError("Milvus Collection 缺少公共 vector 字段")


def _milvus_point(row: Mapping[str, object]) -> VectorPoint:
    point_id = row.get("id")
    vector = row.get("vector")
    if not isinstance(point_id, str) or not isinstance(vector, list):
        raise VectorOperationError("Milvus 返回了不符合公共结构的实体")
    metadata = {key: value for key, value in row.items() if key not in _RESERVED_FIELDS}
    return VectorPoint(id=point_id, vector=tuple(float(value) for value in vector), metadata=cast(dict[str, MetadataScalar], metadata))


def _milvus_match(hit: Mapping[str, object], metric: VectorMetric) -> VectorMatch:
    entity = hit.get("entity")
    point_id = hit.get("id")
    distance = hit.get("distance")
    if not isinstance(entity, dict) or not isinstance(point_id, str) or not isinstance(distance, int | float):
        raise VectorOperationError("Milvus 返回了不符合公共结构的检索结果")
    metadata = {key: value for key, value in entity.items() if key not in _RESERVED_FIELDS}
    score = -float(distance) if metric is VectorMetric.L2 else float(distance)
    return VectorMatch(id=point_id, score=score, metadata=cast(dict[str, MetadataScalar], metadata))


def _milvus_filter(filters: VectorFilters | None) -> str:
    if not filters:
        return ""
    return " and ".join(f"{key} == {json.dumps(value, ensure_ascii=False)}" for key, value in filters.items())
