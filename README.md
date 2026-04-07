# fast-api-scaff

轻量 FastAPI 脚手架，包含配置管理、中间件、统一响应结构和 Docker 启动示例。

## 快速开始（本地）

```bash
cp .env.sample .env
uv sync
uv run uvicorn public.main:app --host 0.0.0.0 --port 8001 --reload
```

访问：
- `http://127.0.0.1:8001/health`
- `http://127.0.0.1:8001/api/v1/test/health`
- `http://127.0.0.1:8001/api/v1/test/db-health`
- `http://127.0.0.1:8001/api/v1/test/redis-health`

## 使用 Docker

```bash
cp .env.sample .env
docker compose up --build -d
docker compose logs -f api
```

停止服务：

```bash
docker compose down
```

说明：
- 宿主机端口取 `.env` 里的 `APP_PORT`（默认 `8001`）
- 容器内部固定监听 `8000`

## 常用配置

`.env` 里重点关注：
- `APP_ENV`：环境标识（如 `dev/test/pre/prod`）
- `APP_PORT`：宿主机暴露端口
- `DB_HOST/DB_PORT/DB_DATABASE/DB_USERNAME/DB_PASSWORD`：数据库连接
- `REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD`：Redis 连接

## 目录结构

```text
app/                 业务代码（API、中间件、模型、工具）
config/              应用配置
database/migration/  Alembic 迁移配置
public/main.py       FastAPI 入口
docker-compose.yml   Docker 编排
Dockerfile           Docker 镜像构建
```