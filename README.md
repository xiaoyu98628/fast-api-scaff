# fast-api-scaff

轻量 FastAPI 脚手架：分层结构、配置管理（Pydantic Settings）、中间件、统一响应与错误码、异步 SQLAlchemy + Alembic、Redis、JWT 示例，以及 Docker 启动示例。

## 环境要求

- Python **3.14+**（见 `pyproject.toml`）
- 包管理：**[uv](https://github.com/astral-sh/uv)**（`uv sync` / `uv run`）
- 本地联调：MySQL、Redis（或改用你自己的连接配置）

## 快速开始（本地）

```bash
cp .env.sample .env
# 按实际环境修改 .env 中的数据库、Redis、JWT 等

uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

等价方式（从配置读取端口与是否 reload）：

```bash
uv run python -m app.main
```

访问：

- 健康检查：`http://127.0.0.1:8001/health`
- 示例接口：`http://127.0.0.1:8001/api/v1/test/health`、`…/db-health`、`…/redis-health`
- OpenAPI 文档：`http://127.0.0.1:8001/docs`（Swagger）、`http://127.0.0.1:8001/redoc`

## 使用 Docker

```bash
cp .env.sample .env
docker compose up --build -d
docker compose logs -f service
```

停止服务：

```bash
docker compose down
```

说明：

- 宿主机端口取 `.env` 里的 `APP_PORT`（默认 `8001`）；映射到容器内 **8000**
- Compose 服务名为 **`service`**（见 `docker-compose.yml`）

## 数据库迁移（Alembic）

```bash
# 创建迁移文件
alembic -c database/alembic.ini revision --autogenerate -m "add_xxx_table"

# 应用迁移到数据库
alembic -c database/alembic.ini upgrade head

# 查看当前迁移版本
alembic -c database/alembic.ini current

# 查看所有迁移版本
alembic -c database/alembic.ini history

# 回滚到上一个版本
alembic -c database/alembic.ini downgrade -1

# 回滚到指定版本（revision 以 alembic history 为准）
alembic -c database/alembic.ini downgrade <revision_id>

# 回滚到初始版本
alembic -c database/alembic.ini downgrade base
```

## 常用配置（`.env`）

与 `.env.sample` 对应，按需调整：

| 变量 | 说明 |
|------|------|
| `APP_NAME` / `APP_ENV` / `APP_DEBUG` / `APP_PORT` | 应用名、环境、调试、端口 |
| `SERVICE_CODE` | 服务码（三位，参与统一错误码；登记见 `docs/service_code.md`） |
| `LOG_*` | 日志级别、格式、文件轮转等 |
| `DB_*` | 异步 MySQL（aiomysql）连接与连接池 |
| `REDIS_*` | Redis 连接 |
| `JWT_*` | 签发与校验访问令牌 |

聚合配置入口：`config/setting.py`（`get_setting()`）。

## 架构与约定（摘要）

调用链：**接口（`interfaces`）→ 应用（`application`）→ 基础设施（`infrastructure`）**。

- **Endpoint**：薄层，参数与 DTO；不写业务与事务细节。
- **Application**：用例编排；按需获取 DB Session；统一 `commit/rollback`。
- **Infrastructure**：DB / Redis 等实现；Repository 内不自行 `commit/rollback`。
- **错误**：业务用 `BizException`，系统/第三方用 `SystemException`；由统一异常中间件出口映射响应（详见 `.cursor/rules/` 下规范）。

新增 REST 模块时，典型顺序：`interfaces/api/v1/endpoints/*.py` → `interfaces/api/v1/router.py` → `interfaces/api/router.py`（版本前缀 `/api/v1/...`）。

## 文档目录

- **`docs/`**：仓库级补充说明（如 `docs/service_code.md` 服务码登记表）。
- **`.cursor/rules/`**：与本仓库配套的分层、错误码、枚举等约定（协作与 AI 辅助时优先对齐）。

## 目录结构

```text
app/
├── main.py                 FastAPI 应用工厂（推荐 ASGI 入口）
├── domain/                 领域实体与规则（按需扩展）
├── application/            用例与服务；业务枚举；按模块可含 errors.py
├── interfaces/             HTTP：api/v1/endpoints、schemas、middleware
├── infrastructure/         DB（engine/session/models/repositories）、Redis、日志
└── common/                 横切：响应、通用枚举、异常与工具
config/                     应用配置（子模块 + setting 聚合）
database/migrations/        Alembic 迁移脚本与 alembic.ini
docs/                       补充文档（登记表等）
docker-compose.yml          Docker 编排
Dockerfile                  多阶段构建（uv 安装依赖）
```

## 技术栈（核心依赖）

FastAPI、Uvicorn、Pydantic Settings、SQLAlchemy 2（async）、aiomysql、Alembic、Redis、PyJWT、bcrypt 等（完整列表见 `pyproject.toml`）。
