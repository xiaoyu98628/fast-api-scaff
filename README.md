# fast-api-scaff

面向 Python 3.14+ 的 FastAPI 模块化单体脚手架。项目以限界上下文组织业务，以 Domain/Application/Infrastructure 分层保护依赖方向，并让 HTTP、Console 等宿主复用同一套应用用例、配置和资源生命周期。

## 已实现能力

- FastAPI HTTP API、OpenAPI 与统一 JSON 响应；
- Typer Console，一次性命令共享应用容器；
- 用户限界上下文 CRUD、状态修改与密码重置示例，密码哈希和验证在线程中执行并共享并发限制；
- 简单数据库会话认证：登录、当前用户、退出，随机 Bearer Token 只保存摘要；
- MySQL、PostgreSQL、SQLite 异步 SQLAlchemy；
- Repository、Mapper、Unit of Work 与 Alembic migration；
- Redis、Memcached 字节级 KV 缓存；
- Milvus（本地 Lite/远程）、Chroma（本地持久化/远程）和 Elasticsearch 统一异步向量存储；
- 普通与流式 HTTP 出站请求、独立连接池、阶段超时、池压力诊断和结构化日志；
- Redis Streams、Kafka、RabbitMQ 队列适配器和独立 Worker；
- QueueJob 动态解析与分发、投递内重试、SQL 失败存储及 Console 重放；
- JSON/Text 结构化日志、HTTP request ID、Console command ID、Worker 任务关联、访问日志和数据库查询日志；
- 架构依赖测试、pytest、Ruff、ty 与 GitHub Actions 质量检查；
- CI 使用临时 MySQL/PostgreSQL 服务验证 Alembic upgrade、downgrade 和再次 upgrade。

当前不包含角色/权限体系、刷新令牌、常驻 Scheduler、领域事件/Outbox/Saga、跨数据库原子事务、Redis 高级数据结构、缓存自动降级或通用 HTTP 自动重试。它们需要按实际业务边界设计，不能把规划项当作现有功能。用户 CRUD 仍是公开示例，`GET /api/v1/auth/me` 演示登录校验。

## 五分钟启动

安装依赖并复制配置：

```bash
uv sync --extra dev
cp sample.env .env
```

首次运行建议把 `.env` 中 main 数据库改为 SQLite，并让本地与部署环境都使用 Redis 缓存。切换 main 的 driver 时，必须先删除原 MySQL 的 `HOST`、`PORT`、`USERNAME`、`PASSWORD`、连接池等字段；连接配置禁止携带当前驱动不支持的额外字段。

```dotenv
TZ=Asia/Shanghai

DB_DEFAULT=main
DB_CONNECTIONS__MAIN__DRIVER=sqlite
DB_CONNECTIONS__MAIN__DATABASE=data/database.sqlite
DB_CONNECTIONS__MAIN__ECHO=false
DB_CONNECTIONS__MAIN__SLOW_QUERY_MS=500

CACHE_DEFAULT=session
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300
CACHE_CONNECTIONS__SESSION__DRIVER=redis
CACHE_CONNECTIONS__SESSION__HOST=127.0.0.1
CACHE_CONNECTIONS__SESSION__PORT=6379
CACHE_CONNECTIONS__SESSION__DATABASE=0
CACHE_CONNECTIONS__SESSION__KEY_PREFIX=session
```

执行迁移并启动：

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run uvicorn app.main:app --reload
```

验证：

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"password123"}'
curl 'http://127.0.0.1:8000/api/v1/users?page=1&limit=20'
```

CORS 预检由跨域中间件直接处理，不生成 Request ID 或应用访问日志；普通请求的错误响应同样按来源执行 CORS 规则。

`/health` 不主动访问数据库或远程缓存。用户接口成功才表示 `main` 数据库配置、迁移和实际查询链路可用。

## Console

```bash
uv run python -m app.console --help
uv run python -m app.console app info
uv run python -m app.console users create \
  --username alice \
  --email alice@example.com
uv run python -m app.console users list --page 1 --limit 20
```

`users create` 会交互式读取并确认密码，输入不回显。每次 Console 调用通过与 HTTP 相同的生成器创建 32 位 UUID4 十六进制 `command_id`，并自动作为当前 `correlation_id` 附加到调用链日志和新发布的队列消息；命令结果写 stdout，日志和错误写 stderr，结果 JSON 不额外包裹该 ID。退出码 0/1/2 分别表示成功、运行失败和用法错误。

## 登录示例

会话表迁移已由维护者手动生成。执行迁移、创建用户后，再调用：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}'
```

将响应 `data.access_token` 放入 `Authorization: Bearer <token>`，即可访问 `GET /api/v1/auth/me`；`POST /api/v1/auth/logout` 删除该会话并返回 204。会话默认有效期为 3600 秒，可通过 `AUTH_SESSION_TTL_SECONDS` 配置。

用户名不存在、格式错误、密码错误或账户禁用时统一返回 401 和“用户名或密码错误”。对于无法取得用户哈希的请求，密码组件仍执行固定占位哈希校验，避免直接暴露账户是否存在。

认证使用独立的 `user_sessions` 表，签发时间和过期时间采用与用户资料一致的本地无时区 `datetime`，用户表不增加角色或认证版本字段。用户聚合使用从 1 开始递增的内部 `version` 执行乐观并发控制，陈旧写入返回 409，不把版本暴露到 HTTP DTO。当前工作区的迁移脚本由维护者手工同步，运行或部署前必须确保 `users.version` 已按非空整数、默认值 1 完成迁移和历史数据回填。每次成功登录会清理已过期会话；密码重置保留已有会话，禁用期间会话不可用，再启用后未过期会话仍可使用。详细契约见[认证](docs/authentication.md)。

## Docker

```bash
docker compose up --build
# 只启动 HTTP 应用
docker compose up --build service
```

默认命令同时启动 HTTP 应用和独立 Worker；指定 `service` 时只启动 HTTP 应用。Compose 不提供 MySQL、PostgreSQL、Redis、Kafka、RabbitMQ、Memcached、Milvus、Chroma Server 或 Elasticsearch。容器内 `127.0.0.1` 指向容器自身；应用可以使用 SQLite、Milvus Lite 或 Chroma 本地持久化，但缓存必须配置容器可访问的 Redis 或 Memcached，队列 Worker 必须配置容器可访问的 Redis、Kafka 或 RabbitMQ 地址。Compose 使用 Uvicorn reload，仅适合本地开发。

Worker 复用应用镜像、`.env` 和网络且不暴露端口。镜像本身不声明健康检查，Compose 只为 HTTP 服务配置 `/health` 检测。脚手架内置登录成功日志 Job；Worker 根据消息携带的类路径动态加载并执行它，不扫描业务目录，也不需要在组合根注册。

生产镜像以 UID/GID 1000 的非 root 用户运行。镜像中的应用代码和虚拟环境由 root 持有，运行用户只对 `storage/data`、`storage/logs` 和自己的 home 目录拥有写权限。Compose 会把项目目录挂载到 `/app`；若使用 SQLite、Milvus Lite 或 Chroma 本地持久化，请确保宿主机对应目录允许该用户写入。本地向量模式只用于单进程开发和小规模数据，不要让 HTTP 多 worker、HTTP 与 Worker 或多个容器共享同一路径。需要适配其他运行平台时，可通过 `APP_UID`、`APP_GID` 构建参数覆盖镜像用户。

## 文档

- [完整手册导航](docs/index.md)
- [快速开始](docs/getting-started.md)
- [配置参考](docs/configuration.md)
- [HTTP 接口](docs/http.md)
- [认证](docs/authentication.md)
- [Console 命令](docs/console.md)
- [队列](docs/queue.md)
- [独立 Worker](docs/worker.md)
- [数据库](docs/database.md)
- [缓存](docs/cache.md)
- [向量存储](docs/vector.md)
- [HTTP 出站请求](docs/outbound-http.md)
- [日志](docs/logging.md)
- [架构说明](docs/architecture.md)
- [开发与质量](docs/development.md)
- [故障排查](docs/troubleshooting.md)

配置时以 [`sample.env`](sample.env) 为可复制模板，以[配置参考](docs/configuration.md)解释字段、默认值和校验时机。

## 开发验证

```bash
uv run python -m pytest -q
uv run ruff check app tests database
uv run ruff format --check app tests database
uv run ty check app tests database
git diff --check
```

GitHub Actions 还会在 MySQL 和 PostgreSQL 上执行迁移往返验证。HTTPX2/httpcore2 由 `uv.lock` 固定到当前已验证版本；升级时必须运行出站 HTTP 取消测试和全量质量检查。

修改公开配置、入口、依赖、目录或调用方式时，必须同步 README、专题文档和 `sample.env`；文档只能描述已经实现并验证的能力。

## 队列与独立 Worker

```bash
uv run python -m app.worker --help
uv run python -m app.worker
# 只在需要隔离连接或逻辑队列时显式覆盖
uv run python -m app.worker --connection redis --queue reports --concurrency 4
docker compose up --build worker
```

内置 `LoginSucceededJob` 由登录接口尽力投递到默认连接配置的默认队列（`sample.env` 为 `default`），消息以 `user_id` 参数标识登录用户，不包含用户名、密码或 Token；HTTP request ID 由运行时上下文自动作为 correlation ID 写入消息。Worker 收到后调用它的 `handle(context)` 记录固定文案和结构化用户 ID，并在发布后续任务时自动继承该 correlation ID。每条消息获得不可变 `JobExecutionContext`，其中既有当前配置和正在运行的 `ApplicationContainer`，也有任务、队列和关联元数据；Job 可以像 Console operation 一样选择已装配的应用服务以及数据库、缓存、HTTP、队列和向量能力。业务 Job 应优先调用应用服务，不把容器继续传入 Application/Domain。新增任务无需注册、扫描目录或修改组合根。HTTP 与 Console 负责发布，独立 Worker 通过 Redis、Kafka 或 RabbitMQ 消费。

失败任务固定使用 SQL 存储，需配置 QUEUE_FAILED__DATABASE 并执行对应 Alembic migration。外部适配器目前由模拟客户端测试覆盖，未进行真实 Redis/Kafka/RabbitMQ 服务集成验证。重试是投递内重试，不包含持久延迟调度或 exactly-once 保证。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
