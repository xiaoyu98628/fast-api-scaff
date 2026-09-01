# fast-api-scaff

面向 Python 3.14+ 的 FastAPI 模块化单体脚手架。项目以限界上下文组织业务，以 Domain/Application/Infrastructure 分层保护依赖方向，并让 HTTP、Console 等宿主复用同一套应用用例、配置和资源生命周期。

## 已实现能力

- FastAPI HTTP API、OpenAPI 与统一 JSON 响应；
- Typer Console，一次性命令共享应用容器；
- 用户限界上下文 CRUD 示例；
- MySQL、PostgreSQL、SQLite 异步 SQLAlchemy；
- Repository、Mapper、Unit of Work 与 Alembic migration；
- Redis、Memcached、Memory 字节级 KV 缓存；
- 普通与流式 HTTP 出站请求、独立连接池、阶段超时和结构化日志；
- JSON/Text 结构化日志、request ID、访问日志和数据库查询日志；
- 架构依赖测试、pytest、Ruff 与 ty 检查。

当前不包含认证/授权、常驻 Scheduler/Worker、领域事件/Outbox/Saga、跨数据库原子事务、Redis 高级数据结构、缓存自动降级或通用 HTTP 自动重试。它们需要按实际业务边界设计，不能把规划项当作现有功能。

## 五分钟启动

安装依赖并复制配置：

```bash
uv sync --extra dev
cp sample.env .env
```

首次运行建议把 `.env` 中 main 数据库和默认缓存改为 SQLite + Memory。切换 main 的 driver 时，必须先删除原 MySQL 的 `HOST`、`PORT`、`USERNAME`、`PASSWORD`、连接池等字段；连接配置禁止携带当前驱动不支持的额外字段。

```dotenv
TZ=Asia/Shanghai

DB_DEFAULT=main
DB_CONNECTIONS__MAIN__DRIVER=sqlite
DB_CONNECTIONS__MAIN__DATABASE=data/database.sqlite
DB_CONNECTIONS__MAIN__ECHO=false
DB_CONNECTIONS__MAIN__SLOW_QUERY_MS=500

CACHE_DEFAULT=local
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300
CACHE_CONNECTIONS__LOCAL__DRIVER=memory
CACHE_CONNECTIONS__LOCAL__KEY_PREFIX=local
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
  -d '{"username":"alice","email":"alice@example.com","display_name":"Alice"}'
curl 'http://127.0.0.1:8000/api/v1/users?offset=0&limit=20'
```

`/health` 不主动访问数据库或远程缓存。用户接口成功才表示 `main` 数据库配置、迁移和实际查询链路可用。

## Console

```bash
uv run python -m app.interfaces.console --help
uv run python -m app.interfaces.console app info
uv run python -m app.interfaces.console users create \
  --username alice \
  --email alice@example.com \
  --display-name Alice
uv run python -m app.interfaces.console users list --offset 0 --limit 20
```

命令结果写 stdout，日志和错误写 stderr；退出码 0/1/2 分别表示成功、运行失败和用法错误。

## Docker

```bash
docker compose up --build
```

当前 `compose.yml` 只启动应用，不提供 MySQL、PostgreSQL、Redis 或 Memcached。容器内 `127.0.0.1` 指向容器自身；请使用 SQLite + Memory，或配置容器可访问的外部服务地址。Compose 使用 Uvicorn reload，仅适合本地开发。

生产镜像以 UID/GID 1000 的非 root 用户运行。镜像中的应用代码和虚拟环境由 root 持有，运行用户只对 `storage/data`、`storage/logs` 和自己的 home 目录拥有写权限。Compose 会把项目目录挂载到 `/app`；若使用 SQLite 或其他本地文件存储，请确保宿主机对应目录允许该用户写入。需要适配其他运行平台时，可通过 `APP_UID`、`APP_GID` 构建参数覆盖镜像用户。

## 文档

- [完整手册导航](docs/index.md)
- [快速开始](docs/getting-started.md)
- [配置参考](docs/configuration.md)
- [HTTP 接口](docs/http.md)
- [Console 命令](docs/console.md)
- [数据库](docs/database.md)
- [缓存](docs/cache.md)
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

修改公开配置、入口、依赖、目录或调用方式时，必须同步 README、专题文档和 `sample.env`；文档只能描述已经实现并验证的能力。
