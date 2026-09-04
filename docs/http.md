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
| `POST` | `/api/v1/users` | 201 | 创建用户 |
| `GET` | `/api/v1/users` | 200 | 分页查询用户 |
| `GET` | `/api/v1/users/{user_id}` | 200 | 查询单个用户 |
| `PUT` | `/api/v1/users/{user_id}` | 200 | 完整更新用户基本信息 |
| `PATCH` | `/api/v1/users/{user_id}/status` | 200 | 修改用户状态 |
| `DELETE` | `/api/v1/users/{user_id}` | 204 | 物理删除用户 |

创建用户时必须提供密码，应用只持久化密码哈希，任何响应都不返回密码或哈希。用户示例尚不包含登录、密码修改、权限、软删除或审计历史。`PUT` 是可编辑用户基本信息的完整更新，必须提供 `username` 和 `email`，不是部分更新，也不接受密码或状态。状态修改是独立用例。

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

curl -i -X DELETE http://127.0.0.1:8000/api/v1/users/USER_UUID
```

删除成功返回 204 且没有响应体。不要尝试按普通统一 JSON 响应解析 204。

## 4. 输入约束

创建和更新请求拒绝未声明字段：

| 字段 | 约束 |
| --- | --- |
| `username` | 3–32 字符，并继续接受领域层格式校验 |
| `email` | 最长 254 字符，并继续接受领域层格式校验 |
| `password` | 仅用于创建，8–128 字符；按原值哈希，不进行 trim 或大小写转换 |
| `status` | 仅用于状态修改接口，必须是领域定义的用户状态 |

Pydantic 的结构校验负责 JSON 类型、长度、缺失字段和额外字段；领域对象负责业务不变量。两者不是重复：HTTP schema 是协议边界，领域校验保证 Console 或未来 Scheduler 等其他入口也不能绕过规则。明文密码只在请求和创建命令中短暂存在，进入聚合前由应用层端口调用基础设施哈希实现；DTO、响应和日志不应携带明文或哈希。

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
| 422 | `1005` | 用户资料违反领域规则 |

请求结构校验返回 422，并在 `data` 中提供 `type`、`location`、`message`。未知异常统一返回通用 500 文案，异常细节只进入服务端日志，避免泄露内部实现。

用户路由会在 OpenAPI 中显式声明 404、409 和 422 错误响应；这些响应与运行时一样使用统一 JSON 结构，生成客户端时不应再按 FastAPI 默认的 `HTTPValidationError` 解析 422。

## 6. Request ID

请求上下文中间件处理 `X-Request-ID`：

- 调用方可提供合法 ID；没有时由插件生成；
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

解码成功时，原查询字符串会被解码结果替换，而不是与普通参数合并。解码失败时中间件保持原查询不变，下游通常会因缺少或非法参数按自身规则处理。`f` 只是传输兼容能力，不是加密，也不能用于隐藏敏感信息。

## 8. CORS

CORS 只约束浏览器跨域访问，不是服务端鉴权。默认允许任意来源、方法和请求头，但不允许携带凭据。

生产配置示例：

```dotenv
CORS_ALLOW_ORIGINS=["https://app.example.com"]
CORS_ALLOW_METHODS=["GET","POST","PUT","DELETE"]
CORS_ALLOW_HEADERS=["Content-Type","Authorization","X-Request-ID"]
CORS_ALLOW_CREDENTIALS=true
CORS_EXPOSE_HEADERS=["X-Request-ID"]
CORS_MAX_AGE=600
```

允许凭据时来源不能包含 `*`。即使 CORS 配置正确，非浏览器调用方仍能访问接口，所以真正的访问控制必须由认证与授权实现；当前脚手架未实现它们。

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
- 409 只用于已明确识别的用户名/邮箱唯一约束；未知数据库完整性错误不应被错误包装成“已存在”。
- 请求 ID 用于关联诊断，不是用户 ID、幂等键或安全凭据。
- CORS 不是认证。
- `f` 是编码而非加密。

数据库相关错误见[数据库](database.md)，请求日志见[日志](logging.md)，综合症状见[故障排查](troubleshooting.md)。
