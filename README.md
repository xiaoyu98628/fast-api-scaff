# fast-api-scaff

基于 FastAPI 的 Python 3.14+ 后端脚手架。项目通过应用容器统一管理数据库和缓存等应用级资源，并采用延迟校验、延迟创建和延迟连接的方式，使未被业务使用的基础设施不会阻塞服务启动。

## 环境要求

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)

## 安装与启动

安装开发依赖：

```shell
uv sync --extra dev
```

复制环境变量示例并按本地环境修改：

```shell
cp sample.env .env
```

启动开发服务：

```shell
uv run uvicorn app.main:app --reload
```

## 应用容器

数据库和缓存管理器都保存在 `ApplicationContainer` 中。FastAPI 生命周期启动时会创建容器，并将其保存到 `app.state.container`；应用关闭时，容器会统一释放已经创建的数据库和缓存资源。

Controller 可以通过 `Request` 获取容器：

```python
from fastapi import Request

from app.bootstrap.container import ApplicationContainer


async def example(request: Request) -> dict[str, object]:
    container: ApplicationContainer = request.app.state.container
    return {
        "databases": container.databases.connection_names,
        "caches": container.caches.connection_names,
    }
```

业务代码应通过容器中的管理器获取资源，不要自行创建数据库 Engine、Redis 客户端或 Memcached 客户端。

## 延迟加载行为

数据库和缓存都不会在应用启动阶段连接外部服务。

| 阶段 | 数据库 | 缓存 |
|------|--------|------|
| 应用启动 | 读取原始配置，不校验具体连接 | 读取原始配置，不校验具体连接 |
| 第一次获取资源 | 校验指定连接并创建 Engine | 校验指定连接并创建客户端 |
| 第一次执行命令 | 建立数据库连接 | 连接 Redis 或 Memcached |
| 应用关闭 | 释放已创建的 Engine | 关闭已创建的客户端和连接池 |

因此，没有被业务使用的数据库或缓存即使配置不完整，也不会阻塞应用启动。配置修改后需要重启服务，使应用重新读取配置快照。

## 跨域访问

应用始终注册 FastAPI 官方的 `CORSMiddleware` 统一处理跨域访问。默认允许任意来源、方法和请求头，但不允许携带 Cookie 等凭证：

```env
CORS_ALLOW_ORIGINS=["*"]
CORS_ALLOW_METHODS=["*"]
CORS_ALLOW_HEADERS=["*"]
CORS_ALLOW_CREDENTIALS=false
CORS_EXPOSE_HEADERS=["*"]
CORS_MAX_AGE=600
```

来源、方法和请求头等列表配置使用 JSON 数组。需要跨域携带 Cookie 或其他凭证时，必须将来源配置为明确域名：

```env
CORS_ALLOW_ORIGINS=["https://app.example.com"]
CORS_ALLOW_CREDENTIALS=true
```

`CORS_ALLOW_ORIGINS` 包含 `"*"` 时不能同时启用 `CORS_ALLOW_CREDENTIALS`，非法组合会在加载配置时被拒绝。`X-Request-ID` 始终对浏览器暴露。默认的 `CORS_EXPOSE_HEADERS=["*"]` 会向不携带凭证的跨域请求暴露所有可访问的响应头；携带凭证时，`"*"` 不具备通配语义，但 `X-Request-ID` 仍会被明确暴露。生产环境可以根据需要将 `CORS_EXPOSE_HEADERS` 改为明确的响应头列表。

CORS 中间件作用于整个 FastAPI 应用，包括 `/health`、`/docs` 和 `/openapi.json`。浏览器来源不在允许列表中时，普通请求仍可能正常返回业务响应，但响应不会包含允许该来源跨域读取的响应头；不合法的预检请求由 CORS 中间件返回失败响应。

## 请求上下文

应用使用 `starlette-context` 的 `RawContextMiddleware` 管理请求级上下文，并通过 `RequestIdPlugin` 处理 `X-Request-ID`：

- 请求未携带 `X-Request-ID` 时自动生成 UUID4；
- 请求携带合法 UUID 时沿用该值；
- 请求携带的值不是合法 UUID 时返回 `400 Bad Request`；
- 正常响应会返回与当前请求上下文一致的 `X-Request-ID`。

请求处理期间可以从公共上下文读取请求 ID：

```python
from starlette_context import context
from starlette_context.header_keys import HeaderKeys


request_id = context[HeaderKeys.request_id]
```

公共上下文用于 `request_id`、`trace_id` 等技术元数据，不用于隐式传递当前用户、租户、权限或事务等业务依赖。上下文只能在请求处理周期内访问。

## 统一响应

普通 JSON API 使用统一响应结构。`code` 由三位 HTTP 状态码、三位服务编码和四位局部响应码组成，`APP_SERVICE_CODE` 用于配置当前服务的三位编码：

```env
APP_SERVICE_CODE=001
```

健康检测响应示例：

```json
{
  "code": "2000010000",
  "success": true,
  "message": "请求成功",
  "data": {
    "message": "ok"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

HTTP 状态码仍然表达请求的实际结果，不会因为使用统一响应而全部返回 `200`。`204 No Content`、文件下载、流式响应和 API 文档端点不使用统一 JSON 响应。`request_id` 与响应头 `X-Request-ID` 保持一致。

HTTP 接口通过 `ApiResponseFactory` 构造响应，业务用例只返回业务结果，不依赖 HTTP 响应模型：

```python
from app.interfaces.http.response.json import ApiResponse, ApiResponseFactory


async def example(responses: ApiResponseFactory) -> ApiResponse[dict[str, int]]:
    return responses.success(data={"value": 1})
```

## 数据库

### 支持的数据库

- PostgreSQL：`postgresql` 或 `pgsql`
- MySQL：`mysql`
- SQLite：`sqlite`

PostgreSQL 和 MySQL 使用异步连接池，SQLite 使用异步驱动。当前项目尚未集成数据库迁移工具，也不会在启动时自动创建数据表。

### 配置方式

数据库环境变量使用以下结构：

```text
DB_DEFAULT=默认连接名
DB_CONNECTIONS__连接名__配置项=配置值
```

例如配置一个默认 PostgreSQL 连接：

```env
DB_DEFAULT=main

DB_CONNECTIONS__MAIN__DRIVER=postgresql
DB_CONNECTIONS__MAIN__HOST=127.0.0.1
DB_CONNECTIONS__MAIN__PORT=5432
DB_CONNECTIONS__MAIN__DATABASE=fast-api
DB_CONNECTIONS__MAIN__USERNAME=postgres
DB_CONNECTIONS__MAIN__PASSWORD=postgres
DB_CONNECTIONS__MAIN__POOL_SIZE=10
DB_CONNECTIONS__MAIN__MAX_OVERFLOW=20
```

增加一个 MySQL 命名连接：

```env
DB_CONNECTIONS__LEGACY__DRIVER=mysql
DB_CONNECTIONS__LEGACY__HOST=127.0.0.1
DB_CONNECTIONS__LEGACY__PORT=3306
DB_CONNECTIONS__LEGACY__DATABASE=legacy
DB_CONNECTIONS__LEGACY__USERNAME=root
DB_CONNECTIONS__LEGACY__PASSWORD=root
DB_CONNECTIONS__LEGACY__CHARSET=utf8mb4
```

增加一个 SQLite 命名连接：

```env
DB_CONNECTIONS__LOCAL__DRIVER=sqlite
DB_CONNECTIONS__LOCAL__DATABASE=data/database.sqlite
```

SQLite 相对路径基于项目的 `storage` 目录解析。上面的配置最终指向：

```text
storage/data/database.sqlite
```

也可以使用绝对路径或 `:memory:` 内存数据库。

### 使用默认数据库

通过 `container.databases.session()` 获取默认数据库会话：

```python
from fastapi import Request
from sqlalchemy import text

from app.bootstrap.container import ApplicationContainer


async def database_example(request: Request) -> dict[str, int]:
    container: ApplicationContainer = request.app.state.container

    async with container.databases.session() as session:
        result = await session.execute(text("SELECT 1"))

    return {"value": result.scalar_one()}
```

`session()` 本身不会自动提交写操作。需要事务时使用 `session.begin()`：

```python
async with container.databases.session() as session:
    async with session.begin():
        await session.execute(...)
```

### 使用命名数据库

将连接名传给 `session()`：

```python
async with container.databases.session("legacy") as session:
    result = await session.execute(...)
```

需要直接访问 SQLAlchemy Engine 时，可以使用：

```python
engine = await container.databases.get_engine()
legacy_engine = await container.databases.get_engine("legacy")
```

通常业务查询应优先使用 `session()`，不要在业务代码中自行关闭 Session 或 Engine；应用容器会统一管理 Engine 生命周期。

## 缓存

### 支持的缓存

- Redis：官方异步客户端 `redis.asyncio`
- Memcached：异步客户端 `memcachio`，当前配置要求提供 SASL 用户名和密码

项目没有提供 Memory 缓存。Redis 和 Memcached 对业务层暴露相同的 `CacheClient` 协议。

### 配置方式

缓存环境变量使用以下结构：

```text
CACHE_DEFAULT=默认连接名
CACHE_KEY_PREFIX=全局默认前缀
CACHE_CONNECTIONS__连接名__配置项=配置值
```

配置默认 Redis 连接：

```env
CACHE_DEFAULT=session
CACHE_KEY_PREFIX=fast-api-scaff:

CACHE_CONNECTIONS__SESSION__DRIVER=redis
CACHE_CONNECTIONS__SESSION__HOST=127.0.0.1
CACHE_CONNECTIONS__SESSION__PORT=6379
CACHE_CONNECTIONS__SESSION__DATABASE=0
CACHE_CONNECTIONS__SESSION__MAX_CONNECTIONS=10
```

配置带 SASL 认证的 Memcached 命名连接：

```env
CACHE_CONNECTIONS__PAGE__DRIVER=memcached
CACHE_CONNECTIONS__PAGE__HOST=127.0.0.1
CACHE_CONNECTIONS__PAGE__PORT=11211
CACHE_CONNECTIONS__PAGE__USERNAME=memcached
CACHE_CONNECTIONS__PAGE__PASSWORD=memcached
CACHE_CONNECTIONS__PAGE__MIN_CONNECTIONS=1
CACHE_CONNECTIONS__PAGE__MAX_CONNECTIONS=10
CACHE_CONNECTIONS__PAGE__KEY_PREFIX=page:
```

Redis 和 Memcached 共用以下连接池配置：

- `MAX_CONNECTIONS`：最大连接数，默认 `10`
- `CONNECT_TIMEOUT`：连接超时秒数，默认 `5.0`
- `READ_TIMEOUT`：读取超时秒数，默认 `5.0`

Memcached 额外支持：

- `MIN_CONNECTIONS`：最小连接数，默认 `1`
- `BLOCKING_TIMEOUT`：等待可用连接的超时秒数，默认 `5.0`

### key 前缀

`CACHE_KEY_PREFIX` 是所有缓存连接共享的默认前缀。连接没有配置自己的 `KEY_PREFIX` 时，会继承全局前缀：

```text
CACHE_KEY_PREFIX=fast-api-scaff:
业务 key=user:1
实际 key=fast-api-scaff:user:1
```

连接级 `KEY_PREFIX` 会完整覆盖全局配置，不会和全局前缀自动拼接：

```env
CACHE_KEY_PREFIX=fast-api-scaff:
CACHE_CONNECTIONS__PAGE__KEY_PREFIX=page:
```

此时 `PAGE` 连接中的 `user:1` 最终是 `page:user:1`。如果需要组合形式，应显式配置：

```env
CACHE_CONNECTIONS__PAGE__KEY_PREFIX=fast-api-scaff:page:
```

### 使用默认缓存

通过 `container.caches.get()` 获取默认缓存：

```python
from fastapi import Request

from app.bootstrap.container import ApplicationContainer
from app.infrastructure.cache.client import CacheClient


async def cache_example(request: Request) -> dict[str, object]:
    container: ApplicationContainer = request.app.state.container
    cache: CacheClient = await container.caches.get()

    await cache.set("user:1", b"xiaoyu", ttl=60)
    value = await cache.get("user:1")

    return {"value": value.decode() if value is not None else None}
```

缓存值统一使用 `bytes`。字符串需要在写入前编码，读取后解码：

```python
await cache.set("name", "xiaoyu".encode(), ttl=60)

value = await cache.get("name")
name = value.decode() if value is not None else None
```

`ttl` 的单位是秒，只能是正整数；传入 `None` 表示不过期。

### 使用命名缓存

将连接名传给 `container.caches.get()`：

```python
page_cache: CacheClient = await container.caches.get("page")
await page_cache.set("home", b"content", ttl=300)
```

其他缓存操作：

```python
exists = await cache.exists("user:1")
deleted = await cache.delete("user:1")
healthy = await cache.ping()
```

业务代码只依赖：

```python
from app.infrastructure.cache.client import CacheClient
```

不要在 Controller 或 Service 中直接导入 `RedisCache`、`MemcachedCache`，也不要自行实例化具体客户端。具体实现由缓存工厂根据连接配置选择，客户端生命周期由应用容器统一管理。

## 项目结构

```text
app/
├── bootstrap/              # 应用创建、容器装配和生命周期
├── config/                 # 原始配置和具体连接配置模型
├── infrastructure/
│   ├── database/           # 数据库资源、工厂和管理器
│   ├── cache/              # 缓存协议、工厂和管理器
│   │   └── backends/       # Redis、Memcached 等具体实现
│   └── resources/          # 通用延迟资源管理
├── interfaces/
│   └── http/               # HTTP 入站接口
│       ├── middleware/     # 中间件和请求上下文装配
│       ├── response/       # 统一响应模型和响应码
│       └── routes/         # 系统路由和应用路由注册
└── runtime/                # 项目运行路径
```

## 开发验证

运行测试：

```shell
uv run python -m pytest -q
```

运行 Ruff：

```shell
uv run ruff check app tests
uv run ruff format --check app tests
```

运行类型检查：

```shell
uv run ty check app tests
```

完整环境变量示例见 [`sample.env`](sample.env)。
