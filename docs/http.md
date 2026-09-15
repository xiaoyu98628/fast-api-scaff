# HTTP 接口

HTTP 宿主是 FastAPI 应用，负责协议解析、请求上下文、统一响应和异常映射。业务规则位于限界上下文，不应写进路由函数或中间件。

## 1. 启动与在线文档

```bash
uv run uvicorn app.main:app --reload
```

默认地址：

- API：`http://127.0.0.1:8000`
- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`
- 健康检查：`GET /health`

生产环境不要直接沿用 `--reload`。监听地址、端口、worker 数和代理头处理应由部署方案明确配置。

## 2. 当前路由

| 方法 | 路径 | 成功状态 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 200 | 基础应用健康检查 |
| `GET` | `/api/v1/streams/events` | 200 | 有限 SSE 事件流，可模拟指定消息位置的处理失败 |
| `POST` | `/api/v1/auth/login` | 200 | 用户名密码登录，返回随机会话 Token；连续失败可返回 429 |
| `GET` | `/api/v1/auth/me` | 200 | 校验 Bearer 会话并返回当前用户 |
| `POST` | `/api/v1/auth/logout` | 204 | 幂等删除当前会话 |
| `POST` | `/api/v1/users` | 201 | 创建用户 |
| `GET` | `/api/v1/users` | 200 | 分页查询用户 |
| `GET` | `/api/v1/users/{user_id}` | 200 | 查询单个用户 |
| `PUT` | `/api/v1/users/{user_id}` | 200 | 完整更新用户基本信息 |
| `PATCH` | `/api/v1/users/{user_id}/status` | 200 | 修改用户状态 |
| `PUT` | `/api/v1/users/{user_id}/password` | 204 | 管理员重置用户密码 |
| `DELETE` | `/api/v1/users/{user_id}` | 204 | 物理删除用户 |

创建用户和重置密码时必须提供密码，应用只持久化密码哈希，任何响应都不返回密码或哈希。用户示例包含简单会话登录，但不包含用户自行修改密码、角色、权限、软删除或审计历史。`PUT /users/{user_id}` 是可编辑用户基本信息的完整更新，必须提供 `username` 和 `email`，不是部分更新，也不接受密码或状态。状态修改与密码重置是独立用例；所有聚合更新都使用内部版本执行乐观并发控制，陈旧写入返回 409，版本不出现在公开 DTO 中。所有用户 CRUD 仍为公开示例，只有 `/auth/me` 演示登录校验；不能将密码重置示例视为受保护的管理员入口。

登录请求使用 JSON `username/password`，成功返回统一响应中的 `data.access_token`、`data.token_type` 和 `data.expires_in`。用户名不存在、格式无效、密码错误或账户禁用在未锁定时都返回 401 和认证局部码 `1101`；启用限制时，文案说明还可尝试的次数，`data.remaining_attempts` 提供相同的机器可读整数。响应带 `WWW-Authenticate: Bearer`；无法取得用户哈希时仍执行固定占位校验。同一规范化用户名达到 Redis 失败阈值后返回 429 和认证局部码 `1102`，动态文案、`data.retry_after_seconds` 与 `Retry-After` 给出剩余锁定秒数，锁定期内不访问数据库或执行密码哈希。`/auth/me` 与 `/auth/logout` 从 `Authorization: Bearer <token>` 提取凭据，不读取 Cookie 或查询参数中的 Token。登录、当前用户成功响应、认证 401 和登录 429 都带 `Cache-Control: no-store`。退出成功返回空的 204；格式合法但不存在或已过期的 Token 也可幂等退出。详见[认证](authentication.md)。

## 3. 完整调用示例

创建：

```bash
curl -i -X POST http://127.0.0.1:8000/api/v1/users \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: 4c287283-5ef1-43ee-a749-f6d95eced597' \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "password123"
  }'
```

查询列表：

```bash
curl 'http://127.0.0.1:8000/api/v1/users?page=1&limit=20'
```

`page` 从 1 开始，默认 1；`limit` 范围为 1–1000，默认 20。列表响应的 `data` 包含 `items` 和 `meta`；`meta` 包含 `page`、`limit`、`total` 和 `total_pages`，没有数据时 `total_pages` 为 0。分页名称和范围属于接口协议；进入应用层后，适配器会转换为 `offset/limit`。

查询、更新和删除：

```bash
curl http://127.0.0.1:8000/api/v1/users/USER_UUID

curl -X PUT http://127.0.0.1:8000/api/v1/users/USER_UUID \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "alice",
    "email": "alice@example.com"
  }'

curl -X PATCH http://127.0.0.1:8000/api/v1/users/USER_UUID/status \
  -H 'Content-Type: application/json' \
  -d '{
    "status": "disabled"
  }'

curl -i -X PUT http://127.0.0.1:8000/api/v1/users/USER_UUID/password \
  -H 'Content-Type: application/json' \
  -d '{
    "password": "replacement-password"
  }'

curl -i -X DELETE http://127.0.0.1:8000/api/v1/users/USER_UUID
```

管理员重置密码和删除用户成功时返回 204 且没有响应体。不要尝试按普通统一 JSON 响应解析 204。

## 4. 输入约束

创建和更新请求拒绝未声明字段：

| 字段 | 约束 |
| --- | --- |
| `username` | 3–32 字符，并继续接受领域层格式校验 |
| `email` | 最长 254 字符，并继续接受领域层格式校验 |
| `password` | 用于创建和管理员重置密码，8–128 字符；按原值哈希，不进行 trim 或大小写转换 |
| `status` | 仅用于状态修改接口，必须是领域定义的用户状态 |

Pydantic 的结构校验负责 JSON 类型、长度、缺失字段和额外字段；领域对象负责业务不变量。两者不是重复：HTTP schema 是协议边界，领域校验保证 Console 或未来 Scheduler 等其他入口也不能绕过规则。明文密码只在请求和创建/重置命令中短暂存在，进入聚合前由应用层端口调用基础设施哈希实现；DTO、响应和日志不应携带明文或哈希。

## 5. 统一 JSON 响应

除 204 等无内容响应外，普通 JSON API 使用：

```json
{
  "code": "2000010000",
  "success": true,
  "message": "请求成功",
  "data": {},
  "request_id": "4c287283-5ef1-43ee-a749-f6d95eced597"
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `code` | 三位 HTTP status + 三位 `APP_SERVICE_CODE` + 四位局部业务码 |
| `success` | 业务响应是否成功 |
| `message` | 面向调用方的稳定消息 |
| `data` | 业务数据或校验详情，可为 `null` |
| `request_id` | 当前请求 ID；无请求上下文时可省略 |

HTTP status 仍是协议层判断成功、失败和重试策略的首要依据，`code` 用于细分业务结果。客户端不要只看 `success` 而忽略 HTTP status。

用户上下文主要错误：

| HTTP | 业务尾码 | 场景 |
| --- | --- | --- |
| 404 | `1001` | 用户不存在 |
| 409 | `1002` | 用户名冲突 |
| 409 | `1003` | 邮箱冲突 |
| 409 | `1004` | 用户已被并发修改 |
| 422 | `1005` | 用户资料违反领域规则 |

创建和更新用户时，用户名与邮箱先去除首尾空白并转换为小写，再执行 HTTP 长度校验，长度限制作用于规范化后的值；领域层继续负责最终业务合法性检查，与 Console 用例保持一致。密码保留原始字符，不进行去空白或大小写转换。

请求结构校验返回 422，并在 `data` 中提供 `type`、`location`、`message`。未知异常统一返回通用 500 文案，异常细节只进入服务端日志，避免泄露内部实现。

用户路由会在 OpenAPI 中显式声明 404、409 和 422 错误响应；这些响应与运行时一样使用统一 JSON 结构，生成客户端时不应再按 FastAPI 默认的 `HTTPValidationError` 解析 422。

## 6. Request ID

除 CORS 预检外，请求上下文中间件处理 `X-Request-ID`：

- 调用方可提供合法 ID；没有时由插件生成；
- 自动生成使用与 Console 共用的 Runtime 生成器，格式为 32 位 UUID4 十六进制字符串；
- ID 出现在统一响应和结构化日志中；
- 非法 ID 会在进入业务前返回 400 并记录警告；
- 排查问题时应以 request ID 串联访问日志和业务日志。

业务服务不应依赖 HTTP request 对象获取 ID。若某个应用用例确实需要关联标识，应定义与协议无关的调用上下文并由入口适配。

## 7. 编码查询参数 `f`

中间件支持把 `f` 参数解码成普通查询参数。协议是：JSON 紧凑序列化 → URL 编码 → Base64 → 去掉末尾 padding。

Python 生成示例：

```python
from app.interfaces.http.middleware.query_param_decode import encode_query_param

encoded = encode_query_param({"page": 1, "limit": 20})
print(encoded)
```

调用：

```bash
curl "http://127.0.0.1:8000/api/v1/users?f=ENCODED_VALUE"
```

解码成功时，原查询字符串会被解码结果替换，而不是与普通参数合并。解码失败时中间件保持原查询不变，下游通常会因缺少或非法参数按自身规则处理。解码使用独立的请求 scope，只替换下游读取的查询字符串和请求 state，不改变 ASGI scope 中的完整请求路径。`f` 只是传输兼容能力，不是加密，也不能用于隐藏敏感信息。

## 8. CORS

CORS 只约束浏览器跨域访问，不是服务端鉴权。默认允许任意来源、方法和请求头，但不允许携带凭据。

生产配置示例：

```dotenv
CORS_ALLOW_ORIGINS=["https://app.example.com"]
CORS_ALLOW_METHODS=["GET","POST","PUT","PATCH","DELETE"]
CORS_ALLOW_HEADERS=["Content-Type","Authorization","X-Request-ID"]
CORS_ALLOW_CREDENTIALS=true
CORS_EXPOSE_HEADERS=["X-Request-ID"]
CORS_MAX_AGE=600
```

应用中间件从外到内依次为 CORS、Request ID、访问日志（启用时）、异常捕获、查询解码。非法 Request ID 的 400 和业务链路的错误响应也会经过 CORS；只有允许的来源才能读取跨域响应。带有 `Origin` 和 `Access-Control-Request-Method` 的 OPTIONS 预检由 CORS 直接处理，不进入请求上下文或应用访问日志，也不生成 Request ID。

允许凭据时来源不能包含 `*`。即使 CORS 配置正确，非浏览器调用方仍能访问接口。当前认证只保护 `/auth/me`，没有角色或权限体系，CORS 不能代替访问控制。

## 9. Controller 的职责边界

Controller 应只负责：

1. 声明 HTTP 路由、状态码和 schema；
2. 把请求对象转换为 application command/query；
3. 调用容器提供的应用服务；
4. 把 DTO 转为响应 schema；
5. 把已知边界异常映射为 `HttpError`。

不应负责：

- 直接使用 SQLAlchemy Session、ORM Model 或具体 Repository；
- 直接连接 Redis/Memcached；
- 修改聚合私有字段；
- 在 HTTP 层重新实现业务规则；
- 捕获所有 `Exception` 并伪装成业务错误；
- 把驱动异常文本直接返回客户端。

这样同一应用用例才能被 HTTP 和 Console 复用，而不会让业务依赖 FastAPI。

## 10. 新增 Controller 的步骤

1. 先在对应限界上下文实现领域行为和应用用例；
2. 在 `app/interfaces/http/controllers/` 下新增明确版本和上下文目录；
3. 定义请求/响应 schema，设置 `extra="forbid"` 等边界约束；
4. 从 HTTP dependency 获取容器公开的应用服务；
5. 为已知应用/领域异常建立穷尽映射，未知异常应暴露为开发错误或进入统一 500；
6. 将子路由显式注册到版本路由；
7. 增加 controller、错误映射和端到端测试；
8. 若公开 API 发生变化，同步更新本手册和 OpenAPI 预期。

不要把某个上下文的异常塞进全局通用错误表。上下文错误码和映射应留在该 controller 附近，公共 HTTP 错误只承载真正跨上下文的协议语义。

## 11. 常见误区

- `/health` 成功不表示数据库已迁移或 Redis 可用。
- 204 没有 JSON 响应体。
- `PUT` 不是 `PATCH`，缺字段会返回 422。
- 409 用于已明确识别的用户名/邮箱唯一约束或用户版本冲突；未知数据库完整性错误不应被错误包装成“已存在”。
- 请求 ID 用于关联诊断，不是用户 ID、幂等键或安全凭据。
- CORS 不是认证。
- `f` 是编码而非加密。

数据库相关错误见[数据库](database.md)，请求日志见[日志](logging.md)，综合症状见[故障排查](troubleshooting.md)。


## 12. 统一 SSE 响应

SSE 通过 Controller 异步生成器逐条发送事件。`SseResponse` 继承 FastAPI 的 `ServerSentEvent`，表示单条事件；整个 HTTP 流使用路由装饰器中的 `response_class=EventSourceResponse`。项目提供统一工厂与依赖注入，并注册 `GET /api/v1/streams/events` 演示有限事件流和可控处理失败。

SSE 流建立前的参数校验错误在 `streams/openapi.py` 中通过 `content.application/json` 声明内联 Schema，路由直接引用该声明。这样保留 JSON 422 的文档类型，无需修改 FastAPI 的 OpenAPI 生成入口；测试校验内联错误结构与统一 JSON 模型一致。

响应目录按类型与构造职责组织，所有 `__init__.py` 保持空文件：

```text
shared/response/
├── json.py              # JsonResponse
├── sse.py               # SseResponse
├── factories/
│   ├── json.py          # JsonResponseFactory
│   └── sse.py           # SseResponseFactory
└── codes/               # 共用响应码契约与构造器
```

JSON 工厂的导入路径由 `app.interfaces.http.shared.response.factory` 调整为 `app.interfaces.http.shared.response.factories.json`；JSON 载荷与 `JsonResponseFactoryDependency` 调用不变。SSE 工厂定义于 `app.interfaces.http.shared.response.factories.sse`。两个工厂均由 HTTP 宿主装配，共享当前应用的 `ResponseCodeBuilder`，不进入 Application 层。

流内异常边界位于 `app.interfaces.http.exceptions.sse`，负责把业务生成器在响应开始后抛出的异常转换为终止事件；它不参与事件构造或 SSE 传输。

在自己的 Controller 中声明并注册路由，例如：

```python
from collections.abc import AsyncGenerator, AsyncIterator

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse

from app.interfaces.http.dependencies.response import SseResponseFactoryDependency
from app.interfaces.http.exceptions.sse import handle_sse_exceptions
from app.interfaces.http.shared.response.factories.sse import SseResponseFactory
from app.interfaces.http.shared.response.sse import SseResponse

router = APIRouter()


@router.get("/stream", response_class=EventSourceResponse)
async def stream(responses: SseResponseFactoryDependency) -> AsyncIterator[SseResponse]:
    """演示发送两条数据并通知客户端完成。"""

    async for event in handle_sse_exceptions(_generate_events(responses), responses):
        yield event


async def _generate_events(responses: SseResponseFactory) -> AsyncGenerator[SseResponse]:
    """生成具体业务事件。"""

    yield responses.success({"content": "第一段"}, id="1")
    yield responses.success({"content": "第二段"}, id="2")
    yield responses.done()
```

统一调用规则：

| 调用 | 事件与载荷 |
| --- | --- |
| `success(data, *, event="message", id=None, retry=None)` | 直接把业务数据写入 SSE `data`，不附加成功码、文案或统一 JSON 外壳；`None` 编码为 JSON `null` |
| `error(code=ErrorCode.INTERNAL_ERROR, *, message=None, data=None)` | 固定 `business_error` 事件；4xx 可携带公开文案和数据，5xx 强制使用通用错误码与默认文案并省略数据 |
| `done()` | 固定 `done` 事件，载荷为 `{}` |

`success` 的 `event` 不能为空或使用保留名称 `business_error`、`done`；事件名、ID 和 retry 同时遵守原生 SSE 字段校验。业务数据必须可以序列化为 JSON；`retry` 单位为毫秒。ID 只是事件标识，不自动提供断点续传。

已知业务失败使用共用或上下文错误码，例如在生成器的已知错误分支中：

```python
from app.interfaces.http.shared.response.codes.error_code import ErrorCode

# 放在异步生成器的已知失败分支中。
yield responses.error(ErrorCode.RESOURCE_NOT_FOUND, message="任务不存在")
return
```

服务编码为 `001` 时，上述错误的实际事件格式为：

```text
event: business_error
data: {"code":"4040010102","message":"任务不存在"}

```

4xx 的 `message` 未显式提供时使用错误码默认文案，显式空字符串会保留。5xx 始终转换为通用内部错误，不透传调用方文案和数据。只接受 4xx/5xx 错误码。十位码前三位表示错误对应的状态分类，不改变已经发送的 HTTP 状态；不要把它解释为连接返回了 HTTP 404。

正常完成时发送 `done` 并结束生成器；失败时发送 `business_error` 并结束生成器，不再发送 `done`。工厂只构造事件，不自动终止流或捕获异常；Controller 通过 `app.interfaces.http.exceptions.sse.handle_sse_exceptions` 包装业务生成器，将其抛出的 `HttpError` 和未知异常转换为安全的终止事件。客户端收到任一终止事件后应关闭连接，避免自动重连。鉴权和可提前执行的检查应放在依赖中，在发送响应头前走现有 JSON 错误映射；客户端断开产生的取消继续传播。

Request ID 通过现有 `X-Request-ID` 响应头关联，不自动注入事件载荷。实际业务流应通过 `try/finally` 或异步上下文管理器释放订阅和上游资源，取消异常应继续传播；不要让数据库事务占用整个长连接。Application 层提供业务数据，HTTP Controller 负责转换为 SSE 事件。


### 12.1 事件流接口

`GET /api/v1/streams/events` 为公开的有限事件流接口，不访问数据库、缓存或其他外部服务。Controller 位于 `app/interfaces/http/controllers/v1/streams/router.py`，查询参数模型 `EventStreamParams` 位于同目录的 `schemas.py`。

| 查询参数 | 默认值 | 约束与用途 |
| --- | --- | --- |
| `count` | `5` | 整数，范围 1–20，计划发送的消息数 |
| `fail_at` | 不设置 | 可选整数，范围 1–count，在该序号模拟处理失败；这是演示参数，不是真实业务错误条件 |

首条消息立即发送，后续每秒一条，20 条正常消息约需 19 秒，实际耗时受调度和客户端接收速度影响。每条 `message` 的 `data` 包含 `sequence` 和 `content`，SSE `id` 等于序号字符串。正常完成发送 `done`；指定 `fail_at` 时，该位置模拟服务端处理失败，由 SSE 异常边界发送脱敏的 `business_error` 并结束，不发送该条消息或 `done`。例如 `count=5&fail_at=3` 会先发送两条消息，再发送通用错误。

```bash
# 正常发送 3 条消息后完成
curl -N 'http://127.0.0.1:8000/api/v1/streams/events?count=3'

# 发送两条消息后模拟失败
curl -N 'http://127.0.0.1:8000/api/v1/streams/events?count=5&fail_at=3'

# 首条即模拟失败，连接仍为 HTTP 200
curl -i -N 'http://127.0.0.1:8000/api/v1/streams/events?fail_at=1'

# 参数越界，在流开始前返回统一 JSON 422
curl -i 'http://127.0.0.1:8000/api/v1/streams/events?count=2&fail_at=3'
```

模拟失败复用 `ErrorCode.INTERNAL_ERROR`；服务编码为 `001`、`fail_at=3` 时事件为：

```text
event: business_error
data: {"code":"5000010101","message":"网络开小差了，请稍后重试"}

```

非法整数、超出范围、`fail_at > count` 或未知查询参数均返回 HTTP 422 的统一 JSON 载荷；模拟失败则属于已开始的 SSE 流，HTTP 状态仍为 200。OpenAPI 分别声明这两种媒体类型。该接口不支持断点续传，重新请求从序号 1 开始；客户端应在收到 `done` 或 `business_error` 时关闭连接。客户端断开时取消继续传播，路由不会继续等待并生成后续消息。
