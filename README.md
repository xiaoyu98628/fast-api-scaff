# fast-api-scaff

轻量 FastAPI 脚手架，包含配置管理、中间件、统一响应结构和 Docker 启动示例。

## 快速开始（本地）

```bash
cp .env.sample .env
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

访问：

- `http://127.0.0.1:8001/health`
- `http://127.0.0.1:8001/api/v1/test/health`、`…/db-health`、`…/redis-health`（免鉴权）
- `POST http://127.0.0.1:8001/api/v1/auth/login`（免鉴权）
- 用户：`GET /api/v1/users?page=&page_size=` 分页列表；`POST/PATCH/DELETE …` 等 CRUD（需 `Authorization: Bearer <token>`）
- OpenAPI：`http://127.0.0.1:8001/docs`

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

## 常用配置

`.env` 里重点关注：

- `APP_ENV` / `APP_PORT` / `APP_DEBUG`
- `DB_*`：数据库；`DB_PREFIX` 默认 `m_`（与迁移表 `m_users` 一致）
- `REDIS_*`：Redis（登录 token 校验依赖 Redis）
- `JWT_*`：签发访问令牌；`SERVICE_CODE`：三位服务码（统一错误码）

## 目录结构

```text
app/
  api/               路由与 OpenAPI 白名单
  core/              统一响应(response)、错误(errors)
  enums/             枚举（用户状态、错误码等）
  middleware/
  models/            ORM 模型与 Base
  repositories/      数据访问
  schemas/           Pydantic 请求/响应体
  services/          业务服务（编排用例）
  infrastructure/  database.py、redis、logging
  utils/             JWT、密码、编解码、日志工具等
config/              应用配置（含 JWT、CORS、日志、SERVICE_CODE）
database/migration/  Alembic 迁移与 versions
storage/log/        运行日志（由 LOG_* 配置，已加入 .gitignore）
docker-compose.yml  Docker 编排
Dockerfile          Docker 镜像构建
```