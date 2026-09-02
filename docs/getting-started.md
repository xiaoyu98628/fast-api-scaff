# 快速开始

本章的目标是让你得到一个可迁移、可启动、可调用的环境，而不是只看到 `/health` 返回成功。推荐第一次运行使用 SQLite + Memory；它不依赖外部服务，同时会覆盖用户示例真正依赖的数据库路径。

## 1. 环境要求

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- Git
- 可选：Docker 与 Docker Compose
- 使用 MySQL、PostgreSQL、Redis 或 Memcached 时，需要对应服务可访问

安装项目依赖：

```bash
uv sync --extra dev
```

复制配置模板：

```bash
cp sample.env .env
```

`.env` 在进程启动时读取并缓存。修改后应重启 HTTP 或重新执行 Console 命令，不能期待运行中的进程自动刷新配置。

## 2. 路径一：SQLite + Memory（推荐首次使用）

将 `.env` 中数据库与缓存部分调整为下面的最小配置。其他应用、日志和 CORS 配置可继续使用 `sample.env` 的值。

如果 `.env` 原来使用 `sample.env` 的 MySQL main 示例，先删除全部 `DB_CONNECTIONS__MAIN__...` 行，再写入下面的 SQLite main 配置。不能只把 `DRIVER` 改成 `sqlite` 而保留 `HOST`、`USERNAME`、连接池等字段，因为连接配置禁止当前驱动不支持的额外字段。

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

相对 SQLite 路径不是相对于当前终端目录，而是相对于项目的 `storage/` 目录解析。因此上面的实际文件是 `storage/data/database.sqlite`。

先执行迁移，再启动服务：

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run uvicorn app.main:app --reload
```

验证 HTTP：

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","display_name":"Alice"}'
curl 'http://127.0.0.1:8000/api/v1/users?page=1&limit=20'
```

验证 Console：

```bash
uv run python -m app.interfaces.console app info
uv run python -m app.interfaces.console users list
```

`/health` 只证明 HTTP 应用能够响应，并不主动连接数据库或远程缓存。用户接口和 `users` 命令成功，才说明 `main` 数据库配置、迁移和实际查询链路可用。

## 3. 路径二：本机 MySQL + Redis

`sample.env` 已提供多连接示例。用户上下文当前明确使用名为 `main` 的数据库连接，所以至少要保证 `DB_CONNECTIONS__MAIN__...` 是可用的。仅修改 `DB_DEFAULT` 不会把用户上下文切换到另一连接。

典型配置：

```dotenv
DB_DEFAULT=main
DB_CONNECTIONS__MAIN__DRIVER=mysql
DB_CONNECTIONS__MAIN__HOST=127.0.0.1
DB_CONNECTIONS__MAIN__PORT=3306
DB_CONNECTIONS__MAIN__DATABASE=fast_api_scaff
DB_CONNECTIONS__MAIN__USERNAME=root
DB_CONNECTIONS__MAIN__PASSWORD=root
DB_CONNECTIONS__MAIN__CHARSET=utf8mb4

CACHE_DEFAULT=session
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300
CACHE_CONNECTIONS__SESSION__DRIVER=redis
CACHE_CONNECTIONS__SESSION__HOST=127.0.0.1
CACHE_CONNECTIONS__SESSION__PORT=6379
CACHE_CONNECTIONS__SESSION__DATABASE=0
CACHE_CONNECTIONS__SESSION__KEY_PREFIX=session
```

在数据库服务中先创建空数据库 `fast_api_scaff`，再执行：

```bash
uv run alembic -c database/main/alembic.ini upgrade head
uv run uvicorn app.main:app --reload
```

启动不代表所有外部连接已验证：数据库在首次获取资源时创建，Redis 在首次 `get`、`set`、`ping` 等操作时建立连接。需要分别执行用户请求和缓存 `ping` 才能完成端到端验证。

## 4. 路径三：Docker Compose

```bash
docker compose up --build
```

当前 Compose 只定义应用容器，不会自动创建 MySQL、PostgreSQL、Redis 或 Memcached。你需要二选一：

1. 使用 SQLite + Memory 配置，让应用容器自包含运行；
2. 自行提供外部数据库/缓存，并把 `.env` 中的主机名改成容器可访问的地址。

容器内的 `127.0.0.1` 指向应用容器自身，不是宿主机，也不是另一个服务容器。连接宿主机服务时，macOS/Windows 通常使用 `host.docker.internal`；连接同一 Compose 网络中的服务时使用服务名。具体可达性仍需以你的部署网络为准。

Compose 启动命令带 `--reload`，适合本地开发，不是生产部署配置。

## 5. 首次运行的正确顺序

```text
安装依赖
  → 准备 .env
  → 创建数据库
  → alembic upgrade head
  → 启动 HTTP 或执行 Console
  → 调用真实业务入口
  → 检查日志和 request_id
```

迁移必须先于访问用户接口。脚手架不会在应用启动时自动建表；这能避免应用进程在生产环境擅自改变数据库结构。

## 6. 时间与时区检查

领域对象和数据库默认使用“本地无时区时间”（naive local datetime）。`TZ` 决定进程采用的本地时区，推荐在所有宿主和运维命令中保持一致：

```dotenv
TZ=Asia/Shanghai
```

注意：

- 时间值不携带 UTC offset，也不会自动转换为 UTC；
- 写入数据后更改 `TZ` 会改变新时间值的语义，已有数据不会自动迁移；
- HTTP、Console、迁移和未来其他宿主应使用相同 `TZ`；
- 跨时区业务若需要绝对时间，应明确设计 UTC 或带时区值，不要直接复用当前约定。

可以通过 `app info` 检查当前应用配置摘要，通过数据库查询对比新记录的 `created_at` 与本地时间。

## 7. 启动后的检查清单

- `uv run alembic -c database/main/alembic.ini current` 显示目标版本已经应用；
- `/health` 返回 200；
- 创建和查询用户成功；
- 重复用户名或邮箱返回 409，而不是 500；
- `X-Request-ID` 能出现在普通 JSON 响应和访问日志中；
- `users list` 的标准输出是 JSON，日志写到标准错误；
- 使用外部数据库或缓存时，实际执行一次读写或 `ping`；
- 应用停止时没有资源关闭异常。

下一步阅读[配置参考](configuration.md)。如果启动失败，直接跳到[故障排查](troubleshooting.md)。
