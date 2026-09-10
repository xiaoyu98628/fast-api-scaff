"""验证三种内置驱动的配置映射、数据转换和本地持久化。"""

import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from typing import cast

import pytest

import app.infrastructure.vector.drivers.chroma as chroma_driver
import app.infrastructure.vector.drivers.elasticsearch as elasticsearch_driver
import app.infrastructure.vector.drivers.milvus as milvus_driver
from app.config.vector import VectorSettings
from app.infrastructure.vector.errors import VectorConfigurationError, VectorConnectionError
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
