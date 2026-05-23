# fast-api-scaff

基于 FastAPI 的后端脚手架，目标提供配置管理、应用生命周期、数据库基础设施、统一响应等常用能力。

> **当前状态：早期脚手架（v0.1.0）** — 配置层与应用入口已就绪，数据库运行时、API 分包、中间件等待完善。

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

## 目录结构

```
fast-api-scaff/
├── paths.py                 # 项目路径常量
├── config/                  # 配置层
│   ├── settings.py          # BASE_SETTINGS_CONFIG（各域公共 SettingsConfigDict）
│   ├── app.py               # 应用配置（APP_ 前缀）
│   ├── database.py          # 数据库配置（DB_ 前缀）
│   └── config.py            # 配置聚合 + config() 工厂
├── app/
│   ├── main.py              # FastAPI 入口
│   └── infrastructure/
│       └── database/        # manager / connection / connectors / db
├── storage/logs/            # 日志
├── .env.sample              # 环境变量模板
└── pyproject.toml
```

## 配置说明

环境变量模板见 [`.env.sample`](.env.sample)，主要命名空间：

| 前缀 | 模块 | 说明 |
|------|------|------|
| `APP_` | `config/app.py` | 应用名称、环境、调试、端口 |
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
uv run alembic -c database/alembic.ini current
uv run alembic -c database/alembic.ini revision --autogenerate -m "add_xxx_table"
uv run alembic -c database/alembic.ini upgrade head
```

`database/migrations/env.py` 通过 `sync_url()` 读取连接，与 `config/database.py` 保持一致。Model 基类就绪后，在 `env.py` 中设置 `target_metadata` 方可使用 `--autogenerate`。

## 待办（Roadmap）

- [x] 数据库连接层（DatabaseManager / Connectors / DB Facade）
- [x] `lifespan` disconnect
- [ ] ORM Model 基类
- [ ] API 路由分包（`app/api/`）
- [ ] 统一响应格式与异常处理
- [ ] 中间件（日志、CORS 等）
- [ ] 测试与 CI

## 开发工具

```bash
# 代码格式化
uv run black .
uv run ruff check .
```

可选开发依赖：`uv sync --extra dev`
