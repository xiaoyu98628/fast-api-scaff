# fast-api-scaff

基于 FastAPI 的 Python 3.14+ 后端脚手架。项目通过应用容器统一管理数据库和缓存等应用级资源，在启动阶段检查确定性的配置错误，并将外部服务连接延迟到第一次实际操作。

## 环境要求

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- Docker 与 Docker Compose（仅使用容器启动时需要）

## 安装与启动

安装开发依赖：

```shell
uv sync --extra dev
```

复制环境变量示例并按本地环境修改：

```shell
cp sample.env .env
```

应用名称、版本、运行环境、调试模式与服务编码通过以下环境变量配置：

```env
APP_NAME=fast-api-scaff
APP_VERSION=3.0.0
APP_ENV=local
APP_DEBUG=false
APP_SERVICE_CODE=001
```

应用不维护独立的时区配置，业务时间、数据库 `DATETIME`、HTTP、Console 和日志统一继承 Python 进程所在操作系统或容器的本地时区。直接在宿主机启动时应先正确配置操作系统时区；需要临时指定时区时，必须在 Python 进程启动前导出标准 `TZ` 环境变量。Compose 会读取 `.env` 中的 `TZ`，Docker 镜像默认使用 `Asia/Shanghai`：

```env
TZ=Asia/Shanghai
```

业务时间使用本地墙上时间并以不带偏移的 `DATETIME` 持久化。HTTP 和 Console 保持该本地时间表示，日志额外携带运行环境的 UTC 偏移，方便定位事件发生时刻。

例如，运行环境为 `Asia/Shanghai` 时创建的数据保持一致：

```text
数据库：2026-08-30 18:42:20
HTTP：  2026-08-30T18:42:20
Console：2026-08-30T18:42:20
日志：  2026-08-30T18:42:20+08:00
```

本地时间是持久化协议的一部分。数据库产生业务数据后，不应直接修改服务器或容器时区；确需修改时，必须同步迁移已有时间字段，避免新旧数据使用不同的墙上时间语义。开发机、CI、服务器和容器应配置为相同的时区。

Docker 容器内的 Uvicorn 固定监听 `0.0.0.0:8000`。Compose 使用 `APP_PORT` 配置宿主机发布端口，默认将宿主机的 `8000` 端口映射到容器的 `8000` 端口：

```env
APP_PORT=8000
```

启动开发服务：

```shell
uv run uvicorn app.main:app --reload
```

## Console

项目提供模块化 Console 入口，用于从 HTTP 之外执行一次性应用操作。Console 与 FastAPI 共享配置加载、日志配置、`ApplicationContainer` 和资源生命周期；每次命令都会创建并启动容器，并在命令成功或失败后关闭已经创建的数据库和缓存资源。模块入口不绑定项目名称，也不要求项目安装为 Python 包。

查看应用及已配置的资源连接：

```shell
uv run python -m app.interfaces.console app info
```

通过现有用户应用服务创建和查询用户：

```shell
uv run python -m app.interfaces.console users create \
  --username admin \
  --email admin@example.com \
  --display-name Administrator

uv run python -m app.interfaces.console users list --offset 0 --limit 20
```

用户命令直接调用 `ApplicationContainer.users.service`，不依赖 FastAPI、HTTP Controller 或 HTTP 响应结构。命令结果使用 JSON 输出，业务时间沿用运行环境的本地墙上时间；业务或领域校验失败时使用退出码 `2`。数据库迁移继续使用 Alembic 原生命令，不由 Console 重复包装。

公共 `ApplicationRuntime` 只管理容器的启动和关闭，不包含 HTTP、Console、Worker 或 Scheduler 的宿主逻辑。未来的队列 Worker 和定时任务入口可以复用该生命周期，但应继续作为独立进程和独立入站接口实现。

## 日志

应用使用 Python 标准库 `logging` 输出单行结构化日志，支持 `json` 和 `text` 两种格式。默认使用 JSON 并只启用 stdout，不创建或写入日志文件，适合由 Docker、Kubernetes 或宿主日志系统统一采集：

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_ACCESS_ENABLED=true
LOG_ACCESS_EXCLUDE_ROUTES=["/health"]
LOG_ACTIVE_HANDLERS=["stdout"]
LOG_HANDLERS__STDOUT__DRIVER=stream
LOG_HANDLERS__STDOUT__STREAM=stdout
```

`LOG_LEVEL` 支持 `DEBUG`、`INFO`、`WARNING`、`ERROR` 和 `CRITICAL`。`LOG_FORMAT` 支持 `json` 和 `text`，并统一应用于当前启用的 Handler；`text` 使用单行 `key=value` 格式，字符串和嵌套字段使用 JSON 编码，异常堆栈中的换行也会被转义。`LOG_ACTIVE_HANDLERS` 使用 JSON 数组指定启用的 Handler；每个 Handler 在 `LOG_HANDLERS__名称` 下配置驱动。当前内置 `stream` 驱动，`stream` 可以是 `stdout` 或 `stderr`。日志驱动只决定日志输出目标，Formatter 和请求上下文 Filter 由日志 Core 统一配置，Driver 不能覆盖。后续可以在默认映射上扩展文件等输出驱动；配置未注册的驱动会在应用启动时失败。

`LOG_FORMAT=text` 的输出示例：

```text
timestamp="2026-08-27T23:30:12.123+08:00" level="INFO" logger="app.interfaces.http.access" service="fast-api-scaff" environment="local" service_version="3.0.0" message="HTTP request completed" request_id="550e8400-e29b-41d4-a716-446655440000" event="http.request.completed" details={"method":"GET","route":"/items/{item_id}","status_code":200,"duration_ms":1.25}
```

项目模块通过标准库获取 logger，不直接创建 Handler：

```python
import logging


logger = logging.getLogger(__name__)

logger.info("任务执行完成")
```

需要稳定检索和统计的日志使用对应模块定义的 `StrEnum` 事件，并将结构化字段放在 `details` 中。HTTP 与数据库分别维护自己的事件枚举，避免形成包含所有业务事件的全局枚举：

```python
from app.infrastructure.logging.record import log_extra
from app.interfaces.http.logging import HttpLogEvent


logger.info(
    "HTTP request completed",
    extra=log_extra(
        HttpLogEvent.REQUEST_COMPLETED,
        method="GET",
        status_code=200,
    ),
)
```

`log_extra()` 只负责将模块事件和结构化字段包装成标准库 `logging` 的 `extra`，不会选择日志级别、调用 Logger 或改变 Handler。

HTTP 访问日志记录请求方法、匹配到的路由模板、状态码、耗时和客户端地址，不记录包含动态参数的原始路径、请求头、Cookie、请求体和查询参数。成功的 `/health` 请求默认不记录，失败的健康检查仍然记录；可以通过 `LOG_ACCESS_EXCLUDE_ROUTES` 调整排除的路由模板。请求日志在进入 Handler 时固化当前 `request_id`，后续即使改用异步 Handler 也不会依赖已经退出的请求上下文。客户端携带非法 `X-Request-ID` 时，请求会在访问日志中间件之前被拒绝，并产生一条 `http.request.invalid_request_id` WARNING 日志。该日志不包含原始 Header、请求路径或 `request_id`。

应用生命周期记录 `application.starting`、`application.started`、`application.start_failed`、`application.stopping`、`application.stopped` 和 `application.stop_failed` 事件。服务名称、环境和版本由统一 Formatter 写入每条日志。

数据库日志记录 Engine 资源创建和关闭、查询异常与慢查询。连接配置中的 `echo=true` 表示通过应用统一日志记录普通 SQL，不再启用 SQLAlchemy 原生 echo；`slow_query_ms` 配置慢查询阈值，单位为毫秒，设为 `0` 时禁用慢查询日志：

```env
DB_CONNECTIONS__MAIN__ECHO=false
DB_CONNECTIONS__MAIN__SLOW_QUERY_MS=500
```

应用日志不会主动记录 SQL 参数或数据库原始错误消息，SQLAlchemy Engine 也固定启用参数隐藏。`echo=false` 时，慢查询和失败查询只记录 SQL 操作类型、语句指纹、错误类型和安全错误码，不记录 SQL 原文；`echo=true` 时才记录参数化 SQL 语句。数据库驱动自身的错误消息不受应用完全控制，因此日志不能作为绝对脱敏边界，业务代码仍应使用参数化查询，也不应把密码、令牌或其他敏感值拼接进 SQL 字符串。

通过 Compose 启动带热重载的开发服务：

```shell
docker compose up --build
```

## 应用容器

数据库、缓存管理器和各业务上下文都保存在 `ApplicationContainer` 中。每个业务上下文负责组装并公开自己的应用服务，避免将所有业务服务的构建细节集中到顶层组合根。FastAPI 生命周期启动时会创建容器，并将其保存到 `app.state.container`；应用关闭时，容器会统一释放已经创建的数据库和缓存资源。

Controller 可以通过 `Request` 获取容器：

```python
from fastapi import Request

from app.bootstrap.container import ApplicationContainer


async def example(request: Request) -> dict[str, object]:
    container: ApplicationContainer = request.app.state.container
    user_service = container.users.service
    return {
        "databases": container.databases.connection_names,
        "caches": container.caches.connection_names,
        "user_service": type(user_service).__name__,
    }
```

同一业务上下文增加应用服务时，只需调整该上下文的组合模块和容器，不需要修改顶层组合根。新增完整业务上下文时，仍需在 `ApplicationContainer` 中显式连接一次。业务代码应通过容器中的管理器获取资源，不要自行创建数据库 Engine、Redis 客户端或 Memcached 客户端。

## 延迟加载行为

数据库和缓存都不会在应用启动阶段连接外部服务。

| 阶段 | 数据库 | 缓存 |
|------|--------|------|
| 应用启动 | 读取原始配置，不校验具体连接 | 校验默认连接、命名空间和所有连接配置 |
| 第一次获取资源 | 校验指定连接并创建 Engine | 创建内存客户端或远程驱动客户端，不建立网络连接 |
| 第一次执行命令 | 建立数据库连接 | 连接 Redis 或 Memcached |
| 应用关闭 | 释放已创建的 Engine | 关闭已创建的客户端和连接池 |

因此，缓存的 driver 拼写错误、参数缺失或默认连接不存在会阻止应用启动，而 Redis、Memcached 暂时不可达不会阻止启动。数据库仍在第一次获取对应资源时校验连接配置。配置修改后需要重启服务，使应用重新读取配置快照。

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

## 编码查询参数

应用会处理查询字符串中名为 `f` 的编码参数。该参数采用 JSON、URL 编码和 Base64 组合格式，仅用于兼容查询参数封装协议，不提供加密、防篡改或敏感信息保护能力。

解码结果是 JSON 对象时，它会替换原始查询字符串供后续中间件和 Controller 读取；原始对象还会保存在 `request.state.decoded_f_params`，以保留无法直接表示为普通查询参数的嵌套结构。解码失败或结果不是 JSON 对象时，请求保持不变。由于解码成功会替换整个查询字符串，调用方不应同时传递 `f` 和其他独立查询参数。

需要生成兼容格式时，通过公共编码函数构造参数，并交给 HTTP 客户端处理查询字符串转义：

```python
from app.interfaces.http.middleware.query_param_decode import encode_query_param


encoded = encode_query_param({"name": "张三", "page": 2})
response = await client.get("/search", params={"f": encoded})
```

解码后的普通字段会进入查询参数，可以继续使用 FastAPI 的参数注入：

```python
from fastapi import APIRouter


router = APIRouter()


@router.get("/search")
async def search(name: str, page: int = 1) -> dict[str, object]:
    return {"name": name, "page": page}
```

需要动态读取参数或获取同名列表参数时，可以使用 `request.query_params`：

```python
from fastapi import Request


@router.get("/search")
async def search(request: Request) -> dict[str, object]:
    return {
        "name": request.query_params.get("name"),
        "tags": request.query_params.getlist("tags"),
    }
```

查询字符串不能完整表示嵌套对象，因此中间件还会把完整解码结果保存到 `request.state.decoded_f_params`。建议通过公共键名读取，并处理没有合法 `f` 参数的情况：

```python
from fastapi import Request

from app.interfaces.http.middleware.query_param_decode import DECODED_F_STATE_KEY


@router.get("/search")
async def search(request: Request) -> dict[str, object] | None:
    decoded = getattr(request.state, DECODED_F_STATE_KEY, None)
    if decoded is None:
        return None

    return decoded
```

只有 `f` 成功解码为 JSON 对象时才会写入 `decoded_f_params`。解码失败时不会创建该状态，原始查询字符串和 `f` 参数保持不变。

## HTTP 路由组织

业务 HTTP Controller 位于 `app.interfaces.http.controllers`。`controllers/router.py` 聚合 `/api` 下的版本化接口，`controllers/v1/router.py` 聚合 `/api/v1` 下的业务接口。`routes/register.py` 负责将业务 Router 注册到 FastAPI 应用，并直接注册不属于业务上下文的 `/health` 宿主探活接口。

## 用户管理

`app.contexts.user` 是用户限界上下文，负责用户资料的创建、查询、更新、禁用和删除。当前上下文不包含密码、登录、Token、角色或权限；认证与授权能力不应直接堆叠到用户资料聚合中。

用户上下文采用分层 DDD 结构：

- `domain` 定义用户聚合、值对象、领域规则和 Repository 契约，不依赖 FastAPI 或 SQLAlchemy；
- `application` 通过应用服务和 Unit of Work 契约编排用例；
- `infrastructure.persistence` 使用 SQLAlchemy 实现 Repository、Data Mapper 和 Unit of Work；
- `app.interfaces.http.controllers.v1.users` 负责请求模型、统一响应和业务异常到 HTTP 的转换；
- `app.bootstrap` 是组合根，负责将具体 Unit of Work 注入用户应用服务。

用户管理提供以下接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/users` | 创建用户 |
| `GET` | `/api/v1/users/{user_id}` | 查询用户 |
| `GET` | `/api/v1/users?offset=0&limit=20` | 分页查询用户 |
| `PUT` | `/api/v1/users/{user_id}` | 完整更新用户资料和状态 |
| `DELETE` | `/api/v1/users/{user_id}` | 删除用户，成功时返回 `204 No Content` |

用户名会去除首尾空白并转换为小写，只能包含 3 到 32 位小写字母、数字或下划线；邮箱会去除首尾空白并转换为小写。用户名和邮箱都具有唯一约束。用户状态当前支持 `active` 和 `disabled`。

用户写操作使用 Unit of Work 管理事务，应用服务不会自行创建或关闭数据库 Engine。删除当前采用物理删除；如果业务需要审计、恢复或数据保留策略，应先明确新的领域规则，再引入软删除。

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

HTTP Controller 通过 `JsonResponse` 的静态方法构造普通 JSON 响应，业务用例只返回业务结果，不依赖 HTTP 响应模型：

```python
from app.interfaces.http.shared.response.json import JsonResponse


async def example() -> JsonResponse[dict[str, int]]:
    return JsonResponse.success(data={"value": 1})
```

`JsonResponse` 是响应体模型，不会自行修改 FastAPI 路由的 HTTP 状态码。返回 `201 Created`、`202 Accepted` 等非 `200` 成功响应时，路由和响应体必须复用同一个成功码定义：

```python
from fastapi import APIRouter

from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.json import JsonResponse


router = APIRouter()


@router.post(
    "/items",
    status_code=SuccessCode.CREATED.status_code,
    response_model=JsonResponse[dict[str, int]],
)
async def create_item() -> JsonResponse[dict[str, int]]:
    return JsonResponse.success(
        data={"id": 1},
        code=SuccessCode.CREATED,
    )
```

这样实际 HTTP 状态和响应体中的完整响应码都会使用 `201`。如果只向 `JsonResponse.success()` 传入 `SuccessCode.CREATED`，而没有设置路由的 `status_code`，FastAPI 仍会返回默认的 `200 OK`。

应用创建时使用 `APP_SERVICE_CODE` 初始化进程级响应码构造器。同一 Python 进程只能对应一个服务编码，Controller 不需要注入响应工厂。SSE、`204 No Content`、文件下载和其他流式响应不使用 `JsonResponse`。

### 异常处理

应用在 HTTP 边界统一注册异常处理器，并将普通 JSON API 的异常转换为 `JsonResponse.error()`：

- 请求参数校验失败使用 `VALIDATION_ERROR` 和 `422`；
- 路由不存在使用 `ROUTE_NOT_FOUND` 和 `404`；
- 请求方法不支持使用 `METHOD_NOT_ALLOWED` 和 `405`；
- 其他 FastAPI、Starlette HTTP 异常保留实际 HTTP 状态码，并使用对应的通用错误码；
- 未知异常统一返回 `INTERNAL_ERROR` 和 `500`，不会向客户端暴露原始异常消息和内部数据。

参数校验错误的 `data` 只包含错误类型、字段位置和错误消息，不回显请求输入或 Pydantic 校验上下文。异常响应会继续经过 CORS 和请求 ID 中间件，`request_id` 与响应头 `X-Request-ID` 保持一致。客户端传入非法 `X-Request-ID` 时，请求会在上下文建立前被拒绝，因此该 `400` 响应不包含 `request_id`。

Controller 或其他 HTTP 接口适配器需要主动返回明确错误码时，可以抛出 `HttpError`：

```python
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.shared.response.codes.error_code import ErrorCode


raise HttpError(
    ErrorCode.RESOURCE_NOT_FOUND,
    data={"resource": "user"},
)
```

`HttpError` 属于 HTTP 接口层，不应由业务用例直接依赖。业务层应定义表达业务事实的异常，再由 Controller 转换为 `HttpError`，或者在对应的 HTTP 模块中为该业务异常注册专用处理器。生产模式下，未知异常会在请求上下文内记录一份带 `request_id` 的堆栈，并在统一 `500` 响应成功发送后停止继续向 Uvicorn 抛出；响应已经开始的流式异常仍会继续抛出。`APP_DEBUG=true` 时，未知异常保留 Starlette 的调试响应，可能包含内部异常详情，仅用于本地开发。

## 数据库

### 支持的数据库

- PostgreSQL：`postgresql` 或 `pgsql`
- MySQL：`mysql`
- SQLite：`sqlite`

PostgreSQL 和 MySQL 使用异步连接池，SQLite 使用异步驱动。main 数据库使用 Alembic 管理结构迁移，应用启动时不会自动执行迁移或创建数据表。

### 配置方式

数据库环境变量使用以下结构：

```text
DB_DEFAULT=默认连接名
DB_CONNECTIONS__连接名__配置项=配置值
```

数据库应用配置与所有内置驱动的字段模型集中定义在 `app.config.database`。`connections/resolver.py` 负责解析默认或命名连接并调用 Provider；Provider 只负责校验原始连接配置并将其转换为 `DatabaseEngineSpec`。Engine 和 Session 工厂仍由公共资源工厂统一创建，业务侧继续通过 `DatabaseManager` 获取资源。

例如配置一个默认 PostgreSQL 连接：

```env
DB_DEFAULT=main

DB_CONNECTIONS__MAIN__DRIVER=postgresql
DB_CONNECTIONS__MAIN__HOST=127.0.0.1
DB_CONNECTIONS__MAIN__PORT=5432
DB_CONNECTIONS__MAIN__DATABASE=fast-api
DB_CONNECTIONS__MAIN__USERNAME=postgres
DB_CONNECTIONS__MAIN__PASSWORD=postgres
DB_CONNECTIONS__MAIN__ECHO=false
DB_CONNECTIONS__MAIN__POOL_SIZE=10
DB_CONNECTIONS__MAIN__MAX_OVERFLOW=20
DB_CONNECTIONS__MAIN__POOL_PRE_PING=true
DB_CONNECTIONS__MAIN__POOL_RECYCLE=3600
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

所有数据库连接都支持 `ECHO`，默认为 `false`。数据库表使用模型声明的固定名称；需要隔离不同服务的数据结构时，应使用独立数据库或数据库 Schema。

PostgreSQL 和 MySQL 额外支持以下连接池配置：

- `POOL_SIZE`：连接池常驻连接数，默认 `10`；
- `MAX_OVERFLOW`：连接池允许临时增加的连接数，默认 `20`；
- `POOL_PRE_PING`：取出连接前是否检查连接有效性，默认 `true`；
- `POOL_RECYCLE`：连接回收间隔秒数，默认 `3600`，设置为 `-1` 表示不按时间回收。

每个连接只能配置当前驱动声明的字段，未知字段会被拒绝，避免配置项拼写错误后静默使用默认值。

### 扩展数据库驱动

每种数据库驱动由独立 Provider 负责配置校验和 `DatabaseEngineSpec` 构建，内置 Provider 通过 `DEFAULT_DATABASE_PROVIDERS` 显式注册。自定义 Provider 实现 `DatabaseProvider` 协议并返回 `DatabaseResourceDefinition`，然后创建扩展 Registry：

```python
from functools import partial

from app.bootstrap.app import create_app
from app.bootstrap.build import build_application_container
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS

providers = DEFAULT_DATABASE_PROVIDERS.extended(CustomDatabaseProvider())
manager = DatabaseManager(settings.database, providers=providers)

app = create_app(
    settings,
    container_builder=partial(
        build_application_container,
        database_providers=providers,
    ),
)
```

扩展 Registry 不会修改全局默认 Registry。一个 Provider 可以注册多个 driver 别名；新增驱动不需要修改 `DatabaseManager`、通用资源工厂或中央配置联合类型。直接使用 Manager 时传入 `providers`，通过 FastAPI 应用使用时则通过自定义 `container_builder` 将 Registry 传入组合根。

### 数据库迁移

main 数据库的 Alembic 配置和迁移脚本位于 `database/main`。迁移环境通过 `connection_name=main` 明确读取 `DB_CONNECTIONS__MAIN__*`，不依赖 `DB_DEFAULT`，也不会把数据库 URL 或密码保存在 Alembic 配置文件中。

查看当前版本：

```shell
uv run alembic -c database/main/alembic.ini current
```

根据已经由迁移环境加载、并继承 `MainBase` 的 ORM 模型生成迁移候选：

```shell
uv run alembic -c database/main/alembic.ini revision --autogenerate -m "create todos table"
```

自动生成的迁移使用模型声明的固定表名。提交迁移前仍应检查 `upgrade()` 和 `downgrade()` 是否准确表达预期结构变化，尤其是表或字段重命名、数据迁移等 Alembic 无法可靠推断的操作。升级到最新版本：

```shell
uv run alembic -c database/main/alembic.ini upgrade head
```

回退一个版本：

```shell
uv run alembic -c database/main/alembic.ini downgrade -1
```

main 数据库 ORM 模型继承实际定义模块中的 `MainBase`，并通过 SQLAlchemy 标准的 `__tablename__` 声明表名：

```python
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class ExampleModel(MainBase):
    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(primary_key=True)
```

实际表名与 `__tablename__` 一致。索引、联合索引、唯一约束和检查约束应在模型的 `__table_args__` 中显式定义；主键、外键等未显式命名的约束使用 ORM Metadata 的统一命名约定。新增 main 数据库 ORM 模型时，还必须将模型类加入 `database.main.model_registry` 的 `_MAIN_DATABASE_MODELS`，确保模型已经注册到 `MainBase.metadata`；Alembic 的 `env.py` 不直接导入业务 Model。

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
- Memcached：异步客户端 `memcachio`，SASL 认证可选
- Memory：用于单元测试和单进程本地开发

三种后端对业务层暴露相同的字节级 `CacheClient` 协议。Memory 不跨进程共享，也不会在远程缓存故障时自动接管，因此不能作为生产环境的透明降级方案。

### 配置方式

缓存环境变量使用以下结构：

```text
CACHE_DEFAULT=默认连接名
CACHE_NAMESPACE=应用级命名空间
CACHE_DEFAULT_TTL=默认过期秒数
CACHE_CONNECTIONS__连接名__配置项=配置值
```

缓存应用配置与所有内置驱动的字段模型集中定义在 `app.config.cache`；Provider 只负责校验原始连接配置并创建对应后端。

配置默认 Redis 连接：

```env
CACHE_DEFAULT=session
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300

CACHE_CONNECTIONS__SESSION__DRIVER=redis
CACHE_CONNECTIONS__SESSION__HOST=127.0.0.1
CACHE_CONNECTIONS__SESSION__PORT=6379
CACHE_CONNECTIONS__SESSION__DATABASE=0
CACHE_CONNECTIONS__SESSION__KEY_PREFIX=session
CACHE_CONNECTIONS__SESSION__MAX_CONNECTIONS=10
CACHE_CONNECTIONS__SESSION__SSL=false
```

Redis 还支持可选的 `USERNAME`、`PASSWORD` 认证配置。

配置 Memcached 命名连接：

```env
CACHE_CONNECTIONS__PAGE__DRIVER=memcached
CACHE_CONNECTIONS__PAGE__HOST=127.0.0.1
CACHE_CONNECTIONS__PAGE__PORT=11211
CACHE_CONNECTIONS__PAGE__MIN_CONNECTIONS=1
CACHE_CONNECTIONS__PAGE__MAX_CONNECTIONS=10
CACHE_CONNECTIONS__PAGE__KEY_PREFIX=page
CACHE_CONNECTIONS__PAGE__SSL=false
```

Memcached 的 `USERNAME` 和 `PASSWORD` 必须同时配置或同时省略。需要 SASL 时增加：

```env
CACHE_CONNECTIONS__PAGE__USERNAME=memcached
CACHE_CONNECTIONS__PAGE__PASSWORD=memcached
```

Redis 和 Memcached 都支持以下配置：

- `MAX_CONNECTIONS`：最大连接数，默认 `10`
- `CONNECT_TIMEOUT`：连接超时秒数，默认 `5.0`
- `READ_TIMEOUT`：读取超时秒数，默认 `5.0`
- `SSL`：是否启用 TLS，默认 `false`

Memcached 额外支持：

- `MIN_CONNECTIONS`：最小连接数，默认 `1`
- `BLOCKING_TIMEOUT`：等待可用连接的超时秒数，默认 `5.0`

Memory 连接只需要 driver 和可选的用途前缀：

```env
CACHE_CONNECTIONS__LOCAL__DRIVER=memory
CACHE_CONNECTIONS__LOCAL__KEY_PREFIX=local
```

存在任意缓存连接时，`CACHE_NAMESPACE` 不能为空。默认连接必须出现在 `CACHE_CONNECTIONS` 中，所有连接配置都会在应用生命周期启动时校验；创建 Redis 或 Memcached 客户端不会立即连接网络。

每个缓存连接只能配置当前驱动声明的字段，未知字段会被拒绝，避免 `SSL`、连接池等配置项拼写错误后静默使用默认值。

### 扩展缓存驱动

每种驱动由独立 Provider 负责配置校验，并组装由 Connection 和 Storage 构成的 `CacheResource`。Connection 管理原生客户端的健康检查和关闭，Storage 只实现数据操作。内置 Provider 通过 `DEFAULT_CACHE_PROVIDERS` 显式注册。自定义 Provider 实现 `CacheProvider` 协议并返回 `CacheResourceDefinition`，然后创建扩展 Registry：

```python
from functools import partial

from app.bootstrap.app import create_app
from app.bootstrap.build import build_application_container
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS

providers = DEFAULT_CACHE_PROVIDERS.extended(CustomCacheProvider())
manager = CacheManager(settings.cache, providers=providers)

app = create_app(
    settings,
    container_builder=partial(
        build_application_container,
        cache_providers=providers,
    ),
)
```

扩展 Registry 不会修改全局默认 Registry。新增驱动不需要修改 `CacheManager`、内置 Provider 或配置联合类型；直接使用 Manager 时传入 `providers`，通过 FastAPI 应用使用时则通过自定义 `container_builder` 将 Registry 传入组合根。项目不使用装饰器或模块导入副作用自动注册驱动。

### Redis 数据类型扩展边界

本次缓存重构没有改变业务侧的普通 KV 使用方式。`container.caches.get()` 仍然返回公共 `CacheClient`，已有的 `get()`、`set()`、`delete()` 和 `exists()` 调用保持不变。重构新增的是 Connection、Storage 和 Resource 之间的职责边界，使 Redis 可以在不修改 Memcached、Memory 公共协议的情况下扩展自身数据类型。

当前已经实现的 Redis 能力只有 String/KV：

- `RedisCacheConnection` 创建并关闭原生 Redis 客户端，负责连接健康检查；
- `RedisStringStorage` 实现 String 的 `get`、`set`、`delete` 和 `exists`；
- `RedisStorage.strings` 聚合 String Storage；
- `RedisStorage` 将 String 操作继续适配为公共 KV 能力，因此业务代码不需要因本次重构而修改。

Hash、List、Set 和 Sorted Set **尚未实现，也没有出现在当前公共 API 中**。后续实际增加这些能力时，应分别放在 `storages/redis` 下：

```text
storages/redis/
├── base.py                 # 已实现：Redis Storage 公共客户端能力
├── string.py               # 已实现：String/KV
├── storage.py              # 已实现：Redis Storage 聚合入口
├── hash.py                 # 待实现：Hash
├── list.py                 # 待实现：List
├── set.py                  # 待实现：Set
└── sorted_set.py           # 待实现：Sorted Set
```

这些 Redis Storage 应共享同一个 `RedisCacheConnection`，统一复用连接池和生命周期。新增类型不应向 `KeyValueStorage` 或公共 `CacheClient` 强行加入 Redis 专属方法；实现完成后应通过独立的 Redis 客户端门面或 Manager 专用入口向确实依赖 Redis 语义的业务代码提供。

### key 规则

最终 key 按以下规则组合：

```text
{CACHE_NAMESPACE}:{连接 KEY_PREFIX}:{业务 key}
```

例如：

```text
namespace=fast-api-scaff
key_prefix=session
业务 key=user:1
最终 key=fast-api-scaff:session:user:1
```

为了让同一个业务 key 能在 Redis 和 Memcached 间迁移，公共客户端统一执行较严格的可移植规则：key 不能为空，不能包含空白或控制字符，最终 UTF-8 长度不能超过 250 字节。namespace 和连接前缀不能以冒号开头或结尾。

### TTL 规则

不传 `ttl` 时使用 `CACHE_DEFAULT_TTL`：

```python
await cache.set("user:1", b"xiaoyu")
```

传入正整数可以覆盖默认值。需要明确写入永不过期的值时使用 `NO_EXPIRATION`，不使用含义模糊的 `None`：

```python
from app.infrastructure.cache.contracts.client import NO_EXPIRATION

await cache.set("temporary", b"value", ttl=60)
await cache.set("permanent", b"value", ttl=NO_EXPIRATION)
```

未配置 `CACHE_DEFAULT_TTL` 时默认值也是 300 秒。不受默认 TTL 影响的永久写入必须显式使用 `NO_EXPIRATION`。

公共 API 中的 TTL 始终表示相对秒数。Memcached 协议会将超过 30 天的 expiry 解释为 Unix 时间戳，后端会自动完成转换，避免它与 Redis 的行为不一致。

### 业务使用

通过 `container.caches.get()` 获取默认缓存：

```python
from fastapi import Request

from app.bootstrap.container import ApplicationContainer
from app.infrastructure.cache.contracts.client import CacheClient


async def cache_example(request: Request) -> dict[str, object]:
    container: ApplicationContainer = request.app.state.container
    cache: CacheClient = await container.caches.get()

    await cache.set("user:1", b"xiaoyu", ttl=60)
    value = await cache.get("user:1")

    return {"value": value.decode() if value is not None else None}
```

缓存值统一使用 `bytes`。项目提供独立的 bytes、UTF-8 文本和 JSON codec，但不会在客户端中隐式序列化任意 Python 对象：

```python
from app.infrastructure.cache.codecs.json import JsonCacheCodec

await cache.set("user:1", JsonCacheCodec.encode({"name": "xiaoyu"}), ttl=60)

payload = await cache.get("user:1")
user = JsonCacheCodec.decode(payload) if payload is not None else None
```

将连接名传给 `container.caches.get()`：

```python
page_cache: CacheClient = await container.caches.get("page")
await page_cache.set("home", b"content", ttl=300)
```

其他缓存操作：

```python
exists = await cache.exists("user:1")
deleted = await cache.delete("user:1")
healthy = await container.caches.ping()
```

`ping()` 和关闭能力属于资源管理职责，不出现在业务 `CacheClient` 协议中。健康检查通过 `CacheManager.ping()` 执行，客户端由应用容器统一关闭。

Controller 或 Service 只依赖：

```python
from app.infrastructure.cache.contracts.client import CacheClient
```

不要直接导入 Redis、Memcached 或 Memory Connection、Storage，也不要自行实例化驱动客户端。底层异常会转换为 `CacheConnectionError` 或 `CacheOperationError`，但不会被静默吞掉；是否在缓存失败后回源，应由业务用例显式决定。

## 项目结构

```text
database/                       # 数据库迁移环境
└── main/                       # main 数据库配置、模型注册和版本脚本
    ├── model_registry.py       # main 数据库 ORM Model 显式注册入口
    └── migrations/             # Alembic 环境和版本脚本
app/
├── bootstrap/              # 应用创建、容器装配、公共 Runtime、生命周期和应用事件
├── config/                 # 应用、日志、数据库与缓存配置模型
├── contexts/               # 按限界上下文组织的业务代码
│   └── user/               # 用户限界上下文
│       ├── domain/         # 聚合、值对象、领域异常和 Repository 契约
│       ├── application/    # 用例 DTO、应用服务和 Unit of Work 契约
│       └── infrastructure/ # SQLAlchemy 持久化适配器
├── infrastructure/
│   ├── logging/            # 与业务框架无关的 Logging Core
│   │   ├── configure.py    # 组装 Formatter、Filter 和 Handler
│   │   ├── context.py      # 固化 request_id 的上下文 Filter
│   │   ├── formatter.py    # 统一 JSON 日志结构
│   │   ├── record.py       # 结构化 extra 构建辅助函数
│   │   ├── contracts/      # Handler Driver 构建契约
│   │   └── drivers/        # 输出目标实现与注册表
│   │       ├── registry.py # 默认 Driver 映射
│   │       └── stream.py   # stdout/stderr 输出
│   ├── database/           # 数据库管理器、资源工厂和公共规则
│   │   ├── connections/    # 命名连接解析与 EngineSpec 定义
│   │   ├── contracts/      # Database Provider 协议与资源定义
│   │   ├── providers/      # 驱动配置校验、EngineSpec 构建和显式注册
│   │   └── orm/            # 表前缀、Metadata、命名约定和分库声明基类
│   ├── cache/              # 缓存管理器、Provider Registry 和公共规则
│   │   ├── contracts/      # 客户端、Connection、Storage 与 Provider 协议
│   │   ├── clients/        # namespace、TTL 等客户端门面
│   │   ├── codecs/         # bytes、文本和 JSON 编解码器
│   │   ├── connections/    # 原生客户端创建、健康检查和关闭
│   │   ├── providers/      # 驱动配置校验、资源组装和显式注册
│   │   └── storages/       # Redis、Memcached、Memory 数据操作
│   │       └── redis/      # Redis String 实现和数据类型聚合入口
│   └── resources/          # 通用延迟资源管理
├── interfaces/
│   ├── console/            # 一次性命令行入站接口
│   │   ├── application.py  # Console 配置、日志和 Runtime 执行边界
│   │   └── commands/       # 命令分组和参数/输出适配
│   └── http/               # HTTP 入站接口
│       ├── controllers/    # 业务 Controller 和版本化 Router
│       ├── exceptions/     # HTTP 异常及异常处理器
│       ├── middleware/     # 中间件和请求上下文装配
│       ├── shared/         # HTTP 接口层共享能力
│       │   └── response/   # 统一响应模型和响应码
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
uv run ruff check app tests database
uv run ruff format --check app tests database
```

运行类型检查：

```shell
uv run ty check app tests database
```

完整环境变量示例见 [`sample.env`](sample.env)。未在示例中显式列出的可选配置使用代码中的默认值。
