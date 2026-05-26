# fast-api-scaff

基于 FastAPI 的 **DDD** 后端脚手架：配置管理、数据库基础设施、领域分层、Alembic 迁移。

> **当前状态：早期脚手架（v0.1.0）** — 配置、数据库连接、统一 API 响应与路由分包骨架已就绪；领域用例、全局异常处理、中间件等待完善。

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.14+ |
| Web | FastAPI + Uvicorn |
| 配置 | pydantic-settings |
| ORM | SQLAlchemy 2.x（asyncio） |
| 数据库驱动 | aiomysql / aiosqlite / asyncpg |
| 包管理 | [uv](https://docs.astral.sh/uv/) |

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
uv sync

# 复制环境变量
cp .env.sample .env
```

### 2. 启动服务

```bash
uv run python -m app.main
# 或
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) 验证服务。

## 目录结构（DDD）

```
fast-api-scaff/
├── config/                          # 配置
├── app/
│   ├── main.py                      # 应用入口
│   ├── domain/                      # 领域层：枚举、实体、仓储接口
│   ├── application/                 # 应用层：用例（待扩展）
│   ├── interfaces/http/             # 接口层
│   │   ├── routers/                 # /api/v1/... 路由分包
│   │   ├── middleware/              # 中间件注册
│   │   ├── schemas/                 # 请求/响应 DTO
│   │   └── response/                # JsonResponse + 响应码表
│   └── infrastructure/
│       ├── database/                # 连接管理
│       └── persistence/             # ORM Base / Model / registry
└── database/                        # Alembic 迁移
```

依赖方向：`interfaces → application → domain`；`infrastructure` 实现 domain 接口，ORM 位于 `persistence/models/`。

## 配置说明

环境变量模板见 [`.env.sample`](.env.sample)，主要命名空间：

| 前缀 | 模块 | 说明 |
|------|------|------|
| `APP_` | `config/app.py` | 应用名称、环境、调试、端口、**服务码**（`APP_SERVICE_CODE`，三位数字） |
| `DB_` | `config/database.py` | 默认连接名、连接池、各命名连接参数（不含 URL） |

代码中读取配置：

```python
from config.config import config

configure = config()
configure.app.name
configure.database.connection
```

各域配置通过 `config/settings.py` 中的 `BASE_SETTINGS_CONFIG` 共享公共项，再在 `app.py` / `database.py` 中展开并设置各自的 `env_prefix`：

```python
from pydantic_settings import SettingsConfigDict
from config.settings import BASE_SETTINGS_CONFIG

model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="APP_")
```

## 开发约定

项目根目录 [`.cursor/rules/`](.cursor/rules/) 中有 Cursor 规则，供 AI 与团队统一遵循：

| 规则文件 | 内容 |
|----------|------|
| `python.mdc` | Python 3.14+ 语法、显式导入、`__init__.py` 不做 re-export |
| `scaffold.mdc` | 本脚手架的分层、配置模式、当前进度 |

核心原则摘要：

- 新建包目录必须有空的 `__init__.py`，禁止 re-export
- 从定义所在模块显式导入，例如 `from config.database import DatabaseConfig`
- 配置公共项放 `config/settings.py`，聚合放 `config/config.py`
- 包内模块用 `python -m` 运行，避免 `python config/xxx.py` 导致包名冲突

## 数据库连接

设计思想参考 Laravel `Illuminate\Database`：配置层只定义 `connections`，URL 在 Connector 中组装。

```
config/database.py → connections / configuration(name)
                 → Connector.make_url() → ConnectionFactory → Connection
```

连接名与驱动解耦，例如 `mysql`、`pgsql`、`sqlite` 为连接名，同驱动可配置多个连接。

```python
from app.infrastructure.database.db import DB

async with DB.connection() as session:        # 默认连接
    ...

async with DB.connection("sqlite") as session:
    ...
```

### 迁移（Alembic）

在项目根目录执行：

```bash
# 创建迁移
alembic -c database/alembic.ini revision --autogenerate -m "add_xxx_table"

# 应用到最新
alembic -c database/alembic.ini upgrade head

# 当前版本
alembic -c database/alembic.ini current

# 历史
alembic -c database/alembic.ini history

# 回滚一步
alembic -c database/alembic.ini downgrade -1

# 回滚到指定 revision
alembic -c database/alembic.ini downgrade <revision_id>

# 回滚到最初
alembic -c database/alembic.ini downgrade base
```

`database/migrations/env.py` 通过 `sync_url()` 读取连接，与 `config/database.py` 保持一致。Model 基类就绪后，在 `registry.py` 导入 Model 即可使用 `--autogenerate`。

### 持久化 Model

ORM 属于基础设施，放在 `infrastructure/persistence/models/`：

```python
from app.domain.user.enums import UserStatus
from app.infrastructure.database.orm.base import Base

class User(Base):
    __table_name__ = "users"
    ...
```

在 `persistence/registry.py` 导入后，Alembic `--autogenerate` 可检测变更。

## 日志

基建只负责 `configure_logging()` 注册；各层使用标准库 `logging.getLogger(...)`。

- **路径**：`storage/logs/{app-slug}/`（由 `APP_NAME` 生成，非扁平）
- **文件**：`app.log`（业务，`app.*` 下 `getLogger(__name__)`）、`request.log`（单行访问日志）、`db.log`（SQL）、`exception.log`
- **级别**：`LOG_LEVEL` 控制 `app.log` 与控制台门槛（默认 `APP_DEBUG=true` → DEBUG，否则 INFO）
- **请求体**：默认不记录；需排查参数时设 `LOG_REQUEST_BODY=true`
- **请求上下文**：`infrastructure/context/request_scope.py`（trace、Request、headers、`set_scope_extra`）
- **trace_id**：`RequestScopeMiddleware` + `TraceIdFilter`；访问日志与 `JsonResponse` 均带出
- **轮转**：`LOG_DRIVER=single|daily|rotating`

常用 logger：`__name__`（应用）、`app.request`（HTTP）、`app.channel.exception`（领域异常）。

## 统一 API 响应

对外 JSON 结构由 `app/interfaces/http/response/json.py` 中的 `JsonResponse` 定义：

| 字段 | 说明 |
|------|------|
| `code` | 10 位字符串响应码（见下文） |
| `success` | 是否成功（模型字段 `is_success`） |
| `message` | 提示文案 |
| `data` | 业务数据，可为 `null` |
| `trace_id` | 链路 ID（`RequestScopeMiddleware` + ContextVar） |

### 10 位响应码

格式：`[HTTP 3位][服务码 3位][低位 4位]`

```
200 + 001 + 0000  →  "2000010000"   # 请求成功
404 + 001 + 0102  →  "4040010102"   # 数据不存在
```

- **低位 4 位**在码表中定义（`CodeDefinition.code`），同一 HTTP 段内可按模块分段（如 `1xxx` 用户、`2xxx` 订单）。
- **服务码**来自环境变量 `APP_SERVICE_CODE`（默认 `001`），多服务部署时每服务唯一。
- 完整码由 `CodedEnum.full_code()` 自动组装，无需单独 builder。

### 码表与基类

位于 `app/interfaces/http/response/code/`：

| 文件 | 说明 |
|------|------|
| `contract.py` | `CodeDefinition`（低位 + 文案 + HTTP 状态）、`CodedEnum` 基类 |
| `success_code.py` | `SuccessCode` — 通用成功码 |
| `error_code.py` | `ErrorCode` — 通用 API 错误码 |

新增码表：继承 `CodedEnum`，每个成员一行 `CodeDefinition`，不要在子类重复写 `code` / `message` / `status_code` property。

```python
from app.interfaces.http.support.response.json import JsonResponse
from app.interfaces.http.support.response.code.error_code import ErrorCode
from app.interfaces.http.support.response.code.success_code import SuccessCode

# 路由中直接返回
return JsonResponse.success(data={"id": 1})
return JsonResponse.success(data=user, code=SuccessCode.SUCCESS_CREATED)
return JsonResponse.error(code=ErrorCode.NOT_FOUND_ERROR, message="用户不存在")  # message 可覆盖默认文案
```

### 业务错误放哪

- **领域语义**（如「用户不存在」）：`domain/` 或 `application/` — 异常或 4 位业务码，不含 HTTP / 服务码。
- **对外 API 码表**：`interfaces/http/response/code/` — `SuccessCode`、`ErrorCode` 及按模块扩展的 `CodedEnum`。
- **映射**：全局 exception handler（待建）将领域异常转为 `ErrorCode` 或模块码表，再 `JsonResponse.error(...)`。

## HTTP 路由

```
/api/v1/users/...   ← api/v1/endpoints/user.py
/ws/v1/...          ← ws/v1/endpoints/（待扩展）
```

注册链：`main.py` → `routers/register.py` → `api/v1/router`（`/api` + `/v1`）、`ws/v1/router`（`/ws` + `/v1`）。

- 新 REST：在 `api/v1/endpoints/` 增加模块并在 `api/v1/router.py` 挂载。
- 新 WebSocket：在 `ws/v1/endpoints/` 增加模块并在 `ws/v1/router.py` 挂载。
- 路由保持薄，只转发到 application 并返回 `JsonResponse`（REST）。

## 待办（Roadmap）

- [x] 数据库连接层（DatabaseManager / Connectors / DB Facade）
- [x] `lifespan` disconnect
- [x] DDD 目录骨架 + 持久化 User ORM
- [x] 统一 API 响应（`JsonResponse` + `CodedEnum` + `SuccessCode` / `ErrorCode`）
- [x] HTTP 路由分包骨架（`/api/v1`）
- [ ] domain 实体 / 仓储接口
- [ ] application 用例
- [ ] 全局异常 handler（领域异常 → `JsonResponse.error`）
- [ ] 中间件（trace_id、CORS 等）
- [ ] 测试与 CI

## 开发工具

```bash
# 代码格式化
uv run black .
uv run ruff check .
```

可选开发依赖：`uv sync --extra dev`
