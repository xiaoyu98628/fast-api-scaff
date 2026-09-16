"""验证三种内置驱动的配置映射、数据转换和本地持久化。"""

import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

import app.infrastructure.vector.drivers.chroma as chroma_driver
import app.infrastructure.vector.drivers.elasticsearch as elasticsearch_driver
import app.infrastructure.vector.drivers.milvus as milvus_driver
from app.config.vector import VectorSettings
from app.infrastructure.vector.errors import (
    VectorCollectionConflictError,
    VectorCollectionNotFoundError,
    VectorConfigurationError,
    VectorConnectionError,
    VectorOperationError,
)
from app.infrastructure.vector.manager import VectorStoreManager
from app.infrastructure.vector.models import VectorCollectionInfo, VectorCollectionSpec, VectorMetric, VectorPoint
from app.runtime.paths import PROJECT_ROOT


class FakeAsyncMilvusClient:
    """模拟 PyMilvus 异步客户端，并记录收到的连接和检索参数。"""

    def __init__(self, **kwargs: object) -> None:
        self.connection_kwargs = kwargs
        self.exists = False
        self.closed = False
        self.search_kwargs: dict[str, object] = {}

    async def list_collections(self, **kwargs: object) -> list[str]:
        del kwargs
        return ["knowledge"] if self.exists else []

    async def has_collection(self, **kwargs: object) -> bool:
        del kwargs
        return self.exists

    async def create_collection(self, **kwargs: object) -> None:
        assert kwargs["metric_type"] == "COSINE"
        assert kwargs["id_type"] == "string"
        self.exists = True

    async def upsert(self, **kwargs: object) -> None:
        data = cast(list[dict[str, object]], kwargs["data"])
        assert data == [{"id": "doc-1", "vector": [1.0, 0.0], "kind": "guide"}]

    async def get(self, **kwargs: object) -> list[dict[str, object]]:
        del kwargs
        return [{"id": "doc-1", "vector": [1.0, 0.0], "kind": "guide"}]

    async def search(self, **kwargs: object) -> list[list[dict[str, object]]]:
        self.search_kwargs = kwargs
        return [[{"id": "doc-1", "distance": 0.95, "entity": {"kind": "guide"}}]]

    async def close(self) -> None:
        self.closed = True


class FakeElasticsearchIndices:
    """模拟 Elasticsearch Index API。"""

    def __init__(self) -> None:
        self.exists_value = False
        self.created: dict[str, object] = {}

    async def exists(self, *, index: str) -> bool:
        del index
        return self.exists_value

    async def create(self, **kwargs: object) -> dict[str, bool]:
        self.created = kwargs
        self.exists_value = True
        return {"acknowledged": True}

    async def get_mapping(self, *, index: str) -> dict[str, object]:
        return {
            index: {
                "mappings": {
                    "properties": {
                        "vector": {"type": "dense_vector", "dims": 2, "similarity": "cosine"},
                    }
                }
            }
        }

    async def delete(self, *, index: str) -> dict[str, bool]:
        del index
        self.exists_value = False
        return {"acknowledged": True}


class FakeAsyncElasticsearch:
    """模拟 Elasticsearch 异步客户端和 Bulk、kNN 返回结构。"""

    def __init__(self, **kwargs: object) -> None:
        self.connection_kwargs = kwargs
        self.indices = FakeElasticsearchIndices()
        self.bulk_operations: list[list[dict[str, object]]] = []
        self.search_kwargs: dict[str, object] = {}
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def bulk(self, *, operations: list[dict[str, object]], refresh: str) -> dict[str, object]:
        assert refresh == "wait_for"
        self.bulk_operations.append(operations)
        operation_name = next(iter(operations[0]))
        status = 200 if operation_name == "delete" else 201
        return {"items": [{operation_name: {"status": status}} for _ in range(0, len(operations), 2 if status == 201 else 1)]}

    async def mget(self, *, index: str, ids: list[str]) -> dict[str, object]:
        del index, ids
        return {
            "docs": [
                {
                    "_id": "doc-1",
                    "found": True,
                    "_source": {"vector": [1.0, 0.0], "metadata": {"kind": "guide"}},
                }
            ]
        }

    async def search(self, **kwargs: object) -> dict[str, object]:
        self.search_kwargs = kwargs
        return {"hits": {"hits": [{"_id": "doc-1", "_score": 1.5, "_source": {"metadata": {"kind": "guide"}}}]}}

    async def close(self) -> None:
        self.closed = True


def test_pymilvus_import_does_not_load_project_dotenv_into_process_environment() -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("APP_", "AUTH_", "CACHE_", "CORS_", "DB_", "HTTP_", "LOG_", "QUEUE_", "VECTOR_"))
    }
    environment.pop("PYTHON_DOTENV_DISABLED", None)
    script = """
import os
from app.infrastructure.vector.drivers.milvus import _load_milvus_sdk
_load_milvus_sdk()
assert os.environ.get("APP_DEBUG") is None
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_milvus_remote_maps_connection_crud_and_search(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeAsyncMilvusClient] = []

    def create_client(**kwargs: object) -> FakeAsyncMilvusClient:
        client = FakeAsyncMilvusClient(**kwargs)
        created.append(client)
        return client

    sdk = milvus_driver._MilvusSdk(
        sync_client=lambda *args, **kwargs: None,
        async_client=create_client,
        connection_errors=(ConnectionError,),
        operation_errors=(RuntimeError,),
    )
    monkeypatch.setattr(milvus_driver, "_load_milvus_sdk", lambda: sdk)
    manager = VectorStoreManager(
        VectorSettings(
            default="knowledge",
            connections={
                "knowledge": {
                    "driver": "milvus",
                    "mode": "remote",
                    "host": "milvus.internal",
                    "port": 19531,
                    "username": "root",
                    "password": "secret",
                    "database": "knowledge",
                }
            },
            _env_file=None,
        )
    )
    client = await manager.get()
    point = VectorPoint(id="doc-1", vector=(1.0, 0.0), metadata={"kind": "guide"})

    await client.create_collection(VectorCollectionSpec(name="knowledge", dimension=2))
    await client.upsert("knowledge", (point,))

    assert await client.get("knowledge", ("doc-1",)) == (point,)
    assert (await client.search("knowledge", (1.0, 0.0), limit=3, filters={"kind": "guide"}))[0].score == 0.95
    assert created[0].connection_kwargs == {
        "uri": "http://milvus.internal:19531",
        "user": "root",
        "password": "secret",
        "db_name": "knowledge",
        "timeout": 10.0,
    }
    assert created[0].search_kwargs["filter"] == 'kind == "guide"'

    await manager.aclose()
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_milvus_remote_builds_ipv6_uri_with_structured_url(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeAsyncMilvusClient] = []

    def create_client(**kwargs: object) -> FakeAsyncMilvusClient:
        client = FakeAsyncMilvusClient(**kwargs)
        created.append(client)
        return client

    sdk = milvus_driver._MilvusSdk(
        sync_client=lambda *args, **kwargs: None,
        async_client=create_client,
        connection_errors=(ConnectionError,),
        operation_errors=(RuntimeError,),
    )
    monkeypatch.setattr(milvus_driver, "_load_milvus_sdk", lambda: sdk)
    manager = VectorStoreManager(
        VectorSettings(
            default="knowledge",
            connections={"knowledge": {"driver": "milvus", "mode": "remote", "host": "::1"}},
            _env_file=None,
        )
    )

    await manager.get()

    assert created[0].connection_kwargs["uri"] == "http://[::1]:19530"
    await manager.aclose()


@pytest.mark.asyncio
async def test_milvus_remote_maps_invalid_address_to_configuration_error() -> None:
    manager = VectorStoreManager(
        VectorSettings(
            default="knowledge",
            connections={
                "knowledge": {
                    "driver": "milvus",
                    "mode": "remote",
                    "host": "[]",
                }
            },
            _env_file=None,
        )
    )

    with pytest.raises(VectorConfigurationError, match="连接地址不合法"):
        await manager.get()

    await manager.aclose()


@pytest.mark.asyncio
async def test_milvus_local_maps_directory_creation_failure(tmp_path: Path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("occupied")
    manager = VectorStoreManager(
        VectorSettings(
            default="local",
            connections={"local": {"driver": "milvus", "mode": "local", "path": str(blocking_file / "milvus.db")}},
            _env_file=None,
        )
    )

    with pytest.raises(VectorConnectionError, match="无法创建 Milvus Lite 数据目录"):
        await manager.get()

    await manager.aclose()


@pytest.mark.asyncio
async def test_milvus_maps_collection_creation_race_to_conflict() -> None:
    backend = Mock()
    backend.call = AsyncMock(side_effect=[False, VectorOperationError("create failed"), True])
    client = milvus_driver.MilvusVectorClient(cast(milvus_driver._MilvusBackend, backend), timeout=1)

    with pytest.raises(VectorCollectionConflictError, match="已存在"):
        await client.create_collection(VectorCollectionSpec(name="knowledge", dimension=2))

    assert [call.args[0] for call in backend.call.await_args_list] == [
        "has_collection",
        "create_collection",
        "has_collection",
    ]


@pytest.mark.asyncio
async def test_milvus_maps_collection_deletion_race_to_not_found() -> None:
    backend = Mock()
    backend.call = AsyncMock(side_effect=[True, VectorOperationError("drop failed"), False])
    client = milvus_driver.MilvusVectorClient(cast(milvus_driver._MilvusBackend, backend), timeout=1)
    client._metrics["knowledge"] = VectorMetric.COSINE

    with pytest.raises(VectorCollectionNotFoundError, match="不存在"):
        await client.delete_collection("knowledge")

    assert "knowledge" not in client._metrics
    assert [call.args[0] for call in backend.call.await_args_list] == [
        "has_collection",
        "drop_collection",
        "has_collection",
    ]


@pytest.mark.asyncio
async def test_chroma_local_persists_and_searches_without_an_embedding_function(tmp_path) -> None:
    manager = VectorStoreManager(
        VectorSettings(
            default="local",
            connections={"local": {"driver": "chroma", "mode": "local", "path": str(tmp_path / "chroma")}},
            _env_file=None,
        )
    )
    client = await manager.get()
    first = VectorPoint(id="doc-1", vector=(1.0, 0.0), metadata={"kind": "guide", "published": True})
    second = VectorPoint(id="doc-2", vector=(0.0, 1.0), metadata={"kind": "guide", "published": False})

    await client.create_collection(VectorCollectionSpec(name="knowledge", dimension=2))
    await client.upsert("knowledge", (first, second))

    assert await client.describe_collection("knowledge") == VectorCollectionInfo(
        name="knowledge",
        dimension=2,
        metric=VectorMetric.COSINE,
    )
    assert await client.get("knowledge", ("doc-2", "missing", "doc-1")) == (second, first)
    matches = await client.search("knowledge", (1.0, 0.0), limit=2, filters={"kind": "guide", "published": True})
    assert tuple(match.id for match in matches) == ("doc-1",)

    with pytest.raises(VectorConfigurationError, match="不能重复"):
        await client.upsert("knowledge", (first, first))
    with pytest.raises(VectorConfigurationError, match="不能重复"):
        await client.get("knowledge", ("doc-1", "doc-1"))
    with pytest.raises(VectorConfigurationError, match="不能重复"):
        await client.delete("knowledge", ("doc-1", "doc-1"))

    raw_client = cast(chroma_driver.ChromaVectorClient, client)._backend._client
    assert getattr(raw_client, "_closed") is False
    await manager.aclose()
    assert getattr(raw_client, "_closed") is True


@pytest.mark.asyncio
async def test_chroma_upsert_replaces_metadata_and_removes_stale_filter_matches(tmp_path) -> None:
    manager = VectorStoreManager(
        VectorSettings(
            default="local",
            connections={"local": {"driver": "chroma", "mode": "local", "path": str(tmp_path / "chroma")}},
            _env_file=None,
        )
    )
    try:
        client = await manager.get()
        await client.create_collection(VectorCollectionSpec(name="knowledge", dimension=2))
        await client.upsert(
            "knowledge",
            (
                VectorPoint(id="first", vector=(1.0, 0.0), metadata={"old": "secret", "kind": "guide"}),
                VectorPoint(id="second", vector=(0.0, 1.0), metadata={"old": "secret"}),
            ),
        )
        # 混合新建、更新和清空，并改变 ID 顺序，验证按 ID 而非返回位置匹配旧字段。
        replacements = (
            VectorPoint(id="second", vector=(1.0, 0.0)),
            VectorPoint(id="new", vector=(0.0, 1.0), metadata={"new": True}),
            VectorPoint(id="first", vector=(0.0, 1.0), metadata={"kind": "updated"}),
        )
        await client.upsert("knowledge", replacements)

        assert await client.get("knowledge", tuple(point.id for point in replacements)) == replacements
        assert await client.search("knowledge", (1.0, 0.0), limit=3, filters={"old": "secret"}) == ()
        matches = await client.search("knowledge", (0.0, 1.0), limit=3, filters={"kind": "updated"})
        assert tuple(match.id for match in matches) == ("first",)
        assert matches[0].metadata == {"kind": "updated"}
    finally:
        await manager.aclose()


@pytest.mark.parametrize("cancel_first", [False, True])
@pytest.mark.asyncio
async def test_chroma_concurrent_upserts_serialize_read_and_write(tmp_path, monkeypatch: pytest.MonkeyPatch, cancel_first: bool) -> None:
    manager = VectorStoreManager(
        VectorSettings(
            default="local",
            connections={"local": {"driver": "chroma", "mode": "local", "path": str(tmp_path / "chroma")}},
            _env_file=None,
        )
    )
    read_finished, release_read, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    try:
        client = cast(chroma_driver.ChromaVectorClient, await manager.get())
        await client.create_collection(VectorCollectionSpec(name="knowledge", dimension=2))
        call = client._backend.collection_call
        reads = 0

        async def pause_first_read(collection: object, method: str, /, **kwargs: object) -> object:
            nonlocal reads
            result = await call(collection, method, **kwargs)
            if method == "get":
                reads += 1
                if reads == 1:
                    # 固定第一个写入的读后写窗口，第二个写入不能在窗口内读取旧快照。
                    read_finished.set()
                    await release_read.wait()
            return result

        monkeypatch.setattr(client._backend, "collection_call", pause_first_read)
        first = VectorPoint(id="same", vector=(1.0, 0.0), metadata={"first": True})
        second = VectorPoint(id="same", vector=(0.0, 1.0), metadata={"second": True})

        async def write_second() -> None:
            second_started.set()
            await client.upsert("knowledge", (second,))

        async with asyncio.timeout(5):
            tasks.append(asyncio.create_task(client.upsert("knowledge", (first,))))
            await read_finished.wait()
            tasks.append(asyncio.create_task(write_second()))
            await second_started.wait()
            assert reads == 1
            if cancel_first:
                tasks[0].cancel()
                with pytest.raises(asyncio.CancelledError):
                    await tasks[0]
            release_read.set()
            await asyncio.gather(*(tasks[1:] if cancel_first else tasks))

        assert await client.get("knowledge", ("same",)) == (second,)
    finally:
        release_read.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await manager.aclose()


@pytest.mark.asyncio
async def test_chroma_remote_maps_basic_auth_to_proxy_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def create_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(chroma_driver.chromadb, "AsyncHttpClient", create_client)
    manager = VectorStoreManager(
        VectorSettings(
            default="remote",
            connections={
                "remote": {
                    "driver": "chroma",
                    "mode": "remote",
                    "host": "chroma.internal",
                    "username": "reader",
                    "password": "secret",
                }
            },
            _env_file=None,
        )
    )

    await manager.get()

    assert captured["host"] == "chroma.internal"
    assert captured["headers"] == {"Authorization": "Basic cmVhZGVyOnNlY3JldA=="}
    await manager.aclose()


@pytest.mark.asyncio
async def test_chroma_remote_creation_failure_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def create_client(**kwargs: object) -> object:
        del kwargs
        raise RuntimeError("SDK 初始化失败")

    monkeypatch.setattr(chroma_driver.chromadb, "AsyncHttpClient", create_client)
    manager = VectorStoreManager(
        VectorSettings(
            default="remote",
            connections={"remote": {"driver": "chroma", "mode": "remote", "host": "chroma.internal"}},
            _env_file=None,
        )
    )

    with pytest.raises(VectorConnectionError, match="无法创建"):
        await manager.get()
    await manager.aclose()


@pytest.mark.asyncio
async def test_chroma_remote_operation_timeout_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowChromaClient:
        async def heartbeat(self) -> None:
            await asyncio.Event().wait()

    async def create_client(**kwargs: object) -> object:
        del kwargs
        return SlowChromaClient()

    monkeypatch.setattr(chroma_driver.chromadb, "AsyncHttpClient", create_client)
    manager = VectorStoreManager(
        VectorSettings(
            default="remote",
            connections={
                "remote": {
                    "driver": "chroma",
                    "mode": "remote",
                    "host": "chroma.internal",
                    "timeout": 0.01,
                }
            },
            _env_file=None,
        )
    )
    client = await manager.get()

    with pytest.raises(VectorConnectionError, match="无法访问"):
        await client.ping()
    await manager.aclose()


@pytest.mark.asyncio
async def test_elasticsearch_maps_connection_index_bulk_and_knn(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeAsyncElasticsearch] = []

    def create_client(**kwargs: object) -> FakeAsyncElasticsearch:
        client = FakeAsyncElasticsearch(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(elasticsearch_driver, "AsyncElasticsearch", create_client)
    manager = VectorStoreManager(
        VectorSettings(
            default="search",
            connections={
                "search": {
                    "driver": "elasticsearch",
                    "mode": "remote",
                    "host": "search.internal",
                    "port": 9243,
                    "ssl": True,
                    "username": "elastic",
                    "password": "secret",
                }
            },
            _env_file=None,
        )
    )
    client = await manager.get()
    point = VectorPoint(id="doc-1", vector=(1.0, 0.0), metadata={"kind": "guide"})

    await client.create_collection(VectorCollectionSpec(name="knowledge", dimension=2))
    await client.upsert("knowledge", (point,))

    assert await client.describe_collection("knowledge") == VectorCollectionInfo(
        name="knowledge",
        dimension=2,
        metric=VectorMetric.COSINE,
    )
    assert await client.get("knowledge", ("doc-1",)) == (point,)
    assert (await client.search("knowledge", (1.0, 0.0), limit=3, filters={"kind": "guide"}))[0].score == 1.5
    assert created[0].connection_kwargs["hosts"] == [{"scheme": "https", "host": "search.internal", "port": 9243}]
    assert created[0].connection_kwargs["basic_auth"] == ("elastic", "secret")
    mappings = cast(Mapping[str, object], created[0].indices.created["mappings"])
    assert mappings["dynamic"] == "strict"
    assert elasticsearch_driver._METRICS[VectorMetric.DOT_PRODUCT] == "max_inner_product"
    knn = cast(Mapping[str, object], created[0].search_kwargs["knn"])
    assert knn["filter"] == [{"term": {"metadata.kind": "guide"}}]

    await manager.aclose()
    assert created[0].closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("document", [{"_id": "doc-1", "error": {"type": "unavailable_shards_exception"}}, {"_id": "doc-1"}])
async def test_elasticsearch_mget_rejects_partial_failure(document: dict[str, object]) -> None:
    from elasticsearch import AsyncElasticsearch

    sdk = FakeAsyncElasticsearch()
    sdk.indices.exists_value = True
    sdk.mget = AsyncMock(return_value={"docs": [document]})
    client = elasticsearch_driver.ElasticsearchVectorClient(cast(AsyncElasticsearch, sdk))
    with pytest.raises(VectorOperationError, match="Multi Get"):
        await client.get("knowledge", ("doc-1",))
    sdk.mget.return_value = {"docs": [{"_id": "doc-1", "found": False}]}
    assert await client.get("knowledge", ("doc-1",)) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("driver", ["chroma", "milvus"])
@pytest.mark.parametrize("close_next", [False, True])
async def test_local_cancellation_waits_for_thread_before_next_operation(driver: str, close_next: bool) -> None:
    from threading import Event

    from chromadb.api import ClientAPI

    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = Event()
    next_started = asyncio.Event()

    def slow() -> None:
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise RuntimeError("测试未释放工作线程")

    sdk = Mock(slow=slow, next=lambda: loop.call_soon_threadsafe(next_started.set), close=lambda: loop.call_soon_threadsafe(next_started.set))
    if driver == "chroma":
        backend = chroma_driver._ChromaBackend(cast(ClientAPI, sdk), local=True)
        call = backend.client_call
    else:
        backend = milvus_driver._LocalMilvusBackend(sdk, Mock(operation_errors=(), connection_errors=()))
        call = backend.call
    first = asyncio.create_task(call("slow"))
    second = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()  # 重复取消也不能提前释放线程额度或上层锁。
        second = asyncio.create_task(backend.aclose() if close_next else call("next"))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(next_started.wait(), 0.05)
        assert not first.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await asyncio.wait_for(second, 2)
        assert next_started.is_set()
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("driver", ["chroma", "milvus"])
async def test_cancelled_local_creation_closes_unpublished_client(driver: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from threading import Event

    from app.config.vector import ChromaLocalVectorSettings, MilvusLocalVectorSettings

    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = Event()
    client = Mock()

    def create(*args: object, **kwargs: object) -> object:
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise RuntimeError("测试未释放创建线程")
        return client

    if driver == "chroma":
        monkeypatch.setattr(chroma_driver.chromadb, "PersistentClient", create)
        creation = chroma_driver.create_chroma_resource(ChromaLocalVectorSettings(driver="chroma", mode="local", path=str(tmp_path)))
    else:
        monkeypatch.setattr(milvus_driver, "_load_milvus_sdk", lambda: Mock(sync_client=create, operation_errors=()))
        creation = milvus_driver.create_milvus_resource(MilvusLocalVectorSettings(driver="milvus", mode="local", path=str(tmp_path / "db")))
    task = asyncio.create_task(creation)
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        client.close.assert_called_once_with()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
