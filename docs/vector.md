# 向量存储

向量基础设施提供“命名连接 + Provider + 延迟资源 + 统一异步客户端”。当前支持 Milvus Lite、远程 Milvus、Chroma 本地持久化、远程 Chroma 和远程 Elasticsearch。三种驱动统一 Collection 管理、向量 CRUD、顶层标量等值过滤和近邻检索，但不负责生成 Embedding。

## 1. 本地连接配置

默认连接使用 Chroma 本地持久化目录：

```dotenv
VECTOR_DEFAULT=chroma_local
VECTOR_CONNECTIONS__CHROMA_LOCAL__DRIVER=chroma
VECTOR_CONNECTIONS__CHROMA_LOCAL__MODE=local
VECTOR_CONNECTIONS__CHROMA_LOCAL__PATH=data/vectors/chroma
```

Milvus Lite 使用另一个命名连接和单个数据库文件：

```dotenv
VECTOR_CONNECTIONS__MILVUS_LOCAL__DRIVER=milvus
VECTOR_CONNECTIONS__MILVUS_LOCAL__MODE=local
VECTOR_CONNECTIONS__MILVUS_LOCAL__PATH=data/vectors/milvus.db
VECTOR_CONNECTIONS__MILVUS_LOCAL__TIMEOUT=10
```

相对路径统一解析到项目 `storage/`。创建 `VectorStoreManager` 只校验配置；第一次 `await container.vectors.get()` 才构造 SDK 客户端，并在本地模式创建对应文件或目录。

本地模式的脚手架契约是单进程开发和小规模数据。不要让 Uvicorn 多 worker、HTTP 与独立 Worker、多个容器或多个应用进程共享同一个 Milvus Lite 文件或 Chroma 目录。需要多进程共享、独立扩缩容或生产运维时，应连接远程服务。

## 2. 远程连接配置

公开配置不接受连接 URL。协议、主机、端口和认证字段分别配置，驱动内部才组装连接参数。

### 2.1 Milvus

```dotenv
VECTOR_CONNECTIONS__MILVUS_REMOTE__DRIVER=milvus
VECTOR_CONNECTIONS__MILVUS_REMOTE__MODE=remote
VECTOR_CONNECTIONS__MILVUS_REMOTE__HOST=127.0.0.1
VECTOR_CONNECTIONS__MILVUS_REMOTE__PORT=19530
VECTOR_CONNECTIONS__MILVUS_REMOTE__DATABASE=default
VECTOR_CONNECTIONS__MILVUS_REMOTE__USERNAME=root
VECTOR_CONNECTIONS__MILVUS_REMOTE__PASSWORD=Milvus
VECTOR_CONNECTIONS__MILVUS_REMOTE__SSL=false
VECTOR_CONNECTIONS__MILVUS_REMOTE__TIMEOUT=10
```

`USERNAME` 与 `PASSWORD` 必须同时配置或同时省略。远程模式使用 `AsyncMilvusClient`；本地 Milvus Lite 的同步 SDK 调用会在线程中串行执行，不阻塞应用事件循环。

### 2.2 Chroma

```dotenv
VECTOR_CONNECTIONS__CHROMA_REMOTE__DRIVER=chroma
VECTOR_CONNECTIONS__CHROMA_REMOTE__MODE=remote
VECTOR_CONNECTIONS__CHROMA_REMOTE__HOST=127.0.0.1
VECTOR_CONNECTIONS__CHROMA_REMOTE__PORT=8000
VECTOR_CONNECTIONS__CHROMA_REMOTE__TENANT=default_tenant
VECTOR_CONNECTIONS__CHROMA_REMOTE__DATABASE=default_database
VECTOR_CONNECTIONS__CHROMA_REMOTE__USERNAME=reader
VECTOR_CONNECTIONS__CHROMA_REMOTE__PASSWORD=secret
VECTOR_CONNECTIONS__CHROMA_REMOTE__SSL=false
```

此处按照前置代理使用 HTTP Basic Auth 配置，适配器会生成 `Authorization` 请求头。Chroma 1.x 自托管服务没有内置认证；没有认证代理时，应同时删除 `USERNAME` 和 `PASSWORD`。

Chroma Cloud 使用独立连接名以及平台提供的主机、`TENANT`、`DATABASE` 和 `API_KEY`：

```dotenv
VECTOR_CONNECTIONS__CHROMA_CLOUD__DRIVER=chroma
VECTOR_CONNECTIONS__CHROMA_CLOUD__MODE=remote
VECTOR_CONNECTIONS__CHROMA_CLOUD__HOST=your-chroma-cloud-host
VECTOR_CONNECTIONS__CHROMA_CLOUD__PORT=443
VECTOR_CONNECTIONS__CHROMA_CLOUD__TENANT=tenant-id
VECTOR_CONNECTIONS__CHROMA_CLOUD__DATABASE=database-name
VECTOR_CONNECTIONS__CHROMA_CLOUD__API_KEY=token
VECTOR_CONNECTIONS__CHROMA_CLOUD__SSL=true
```

`your-chroma-cloud-host` 需要替换为平台提供的主机名。`API_KEY` 不能与 `USERNAME/PASSWORD` 同时配置。远程模式使用 `AsyncHttpClient`；本地 `PersistentClient` 的同步调用会在线程中串行执行。Chroma SDK 当前没有公开客户端关闭方法，因此统一 `aclose()` 不执行额外关闭动作。

### 2.3 Elasticsearch

```dotenv
VECTOR_CONNECTIONS__SEARCH__DRIVER=elasticsearch
VECTOR_CONNECTIONS__SEARCH__MODE=remote
VECTOR_CONNECTIONS__SEARCH__HOST=127.0.0.1
VECTOR_CONNECTIONS__SEARCH__PORT=9200
VECTOR_CONNECTIONS__SEARCH__USERNAME=elastic
VECTOR_CONNECTIONS__SEARCH__PASSWORD=secret
VECTOR_CONNECTIONS__SEARCH__SSL=false
VECTOR_CONNECTIONS__SEARCH__VERIFY_CERTS=true
VECTOR_CONNECTIONS__SEARCH__CONNECTIONS_PER_NODE=10
VECTOR_CONNECTIONS__SEARCH__MAX_RETRIES=3
VECTOR_CONNECTIONS__SEARCH__RETRY_ON_TIMEOUT=true
VECTOR_CONNECTIONS__SEARCH__TIMEOUT=10
```

Elasticsearch 没有嵌入式本地模式。`USERNAME/PASSWORD` 必须同时配置或同时省略；使用自定义 CA 时可额外配置 `VECTOR_CONNECTIONS__SEARCH__CA_CERTS` 证书文件路径。适配器使用 `AsyncElasticsearch`、`dense_vector`、Bulk API 和 kNN 查询。

## 3. 公共调用方式

宿主层通过 `ApplicationContainer` 获取统一客户端：

```python
from app.infrastructure.vector.models import VectorCollectionSpec, VectorMetric, VectorPoint
from app.runtime.container import ApplicationContainer


async def index_documents(container: ApplicationContainer) -> None:
    vectors = await container.vectors.get()
    spec = VectorCollectionSpec(name="documents", dimension=3, metric=VectorMetric.COSINE)
    if not await vectors.has_collection(spec.name):
        await vectors.create_collection(spec)

    await vectors.upsert(
        spec.name,
        (
            VectorPoint(
                id="document-1",
                vector=(0.12, 0.34, 0.56),
                metadata={"category": "guide", "published": True},
            ),
        ),
    )

    matches = await vectors.search(
        spec.name,
        (0.11, 0.35, 0.55),
        limit=10,
        filters={"category": "guide"},
    )
    for match in matches:
        print(match.id, match.score, match.metadata)
```

`VectorClient` 还提供：

- `ping()`；
- `describe_collection(name)`；
- `delete_collection(name)`；
- `get(collection, ids)`，按调用方 ID 顺序返回存在项；
- `delete(collection, ids)`，缺失 ID 视为幂等成功；
- `aclose()`，通常由容器统一调用。

具体限界上下文不能依赖 `ApplicationContainer`、`VectorStoreManager` 或具体 SDK。Application/Domain 层应定义业务语义明确的窄协议，例如 `KnowledgeRetriever`；上下文 Infrastructure 适配器再使用 `VectorClient` 实现它，并由 composition root 注入。

## 4. 可移植数据契约

Collection 名称必须是 3–63 位小写字母、数字、下划线或连字符，首尾为字母或数字。维度范围是 1–4096，采用三个驱动的共同上限；支持 `cosine`、`dot_product` 和 `l2`。

`VectorPoint` 由字符串 ID、调用方生成的有限浮点向量和元数据组成。ID 的 UTF-8 长度为 1–512 字节。元数据只接受字符串、整数、有限浮点数和布尔值；字段名只能包含字母、数字和下划线且不能以数字开头。`id`、`vector` 和 `_vector_*` 是内部保留字段。

过滤器是顶层元数据字段的 AND 等值匹配。公共接口不承诺范围、全文、嵌套布尔表达式或驱动专有过滤语法。公共 `dot_product` 在 Milvus/Chroma 使用 IP，在 Elasticsearch 使用无需单位向量的 `max_inner_product`。检索结果按相关度降序返回，`score` 越大越相关；不同驱动或不同 metric 的 score 数值不可直接比较。

调用方必须保证写入和查询向量与 Collection 维度一致。脚手架不选择 Embedding 模型、不调用模型服务，也不自动迁移维度；更换模型或维度需要使用新的 Collection 或执行明确的数据重建。

## 5. 驱动映射

| 公共概念 | Milvus | Chroma | Elasticsearch |
| --- | --- | --- | --- |
| Collection | Collection | Collection | Index |
| 主键 | 字符串 `id` | 字符串 ID | 文档 `_id` |
| 向量 | `vector` 字段 | embedding | `dense_vector` |
| 元数据 | 动态标量字段 | metadata | `flattened` metadata |
| 批量写入 | upsert | upsert | Bulk index |
| 检索 | ANN search | HNSW query | kNN search |

统一协议只暴露三者可靠交集。需要 Milvus partition、Chroma embedding function、Elasticsearch 全文混合检索等专有能力时，应在具体业务上下文定义专用端口和适配器，不要把专有参数塞入公共 `VectorClient`。

## 6. 生命周期与错误

`VectorStoreManager` 在容器构建时严格校验全部命名连接，但不会创建本地数据、连接远程服务或执行 ping。首次 `get(name)` 并发安全地创建一次客户端；关闭开始后拒绝新获取，并逆序关闭已初始化资源。`/health` 不主动探测向量存储。

公共异常：

| 异常 | 含义 |
| --- | --- |
| `VectorConfigurationError` | 连接、Collection、向量或过滤参数不合法 |
| `VectorConnectionError` | SDK 客户端或远程服务不可访问 |
| `VectorCollectionNotFoundError` | Collection/Index 不存在 |
| `VectorCollectionConflictError` | 创建的 Collection/Index 已存在 |
| `VectorOperationError` | 其他后端操作或返回结构不符合公共契约 |

脚手架不会在驱动失败时自动切换连接，也不会把连接故障当成空检索结果。是否降级、重试或回退到关键词检索属于具体业务策略。

## 7. 扩展新驱动

新增驱动需要同步完成：

1. 在 `app.config.vector` 增加严格配置模型和解析分支；
2. 在 `app.infrastructure.vector.drivers` 实现统一 `VectorClient` 和 SDK 异常转换；
3. 实现 `VectorProvider`，只在延迟工厂中创建资源；
4. 注册到 `DEFAULT_VECTOR_PROVIDERS`，或在组合根传入扩展后的注册表；
5. 增加配置、数据映射、生命周期和异常测试；
6. 同步 `sample.env`、本章与配置参考。

驱动 SDK 只能出现在 `app.infrastructure.vector.drivers`，业务层和宿主层不能直接导入。当前锁文件中的 PyMilvus、Chroma 和 Elasticsearch Python 客户端已在 Python 3.14 下通过静态检查与测试；升级任一 SDK 后需要重新执行全量质量检查和对应驱动测试。
