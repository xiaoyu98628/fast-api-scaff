FROM python:3.14-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv -i https://mirrors.aliyun.com/pypi/simple/

COPY pyproject.toml uv.lock README.md ./

# 创建虚拟环境并安装生产依赖
# --frozen: 严格按照 uv.lock 文件安装
# --no-dev: 不安装开发依赖
# --no-install-project: 不安装项目本身，只安装依赖
RUN uv sync --frozen --no-dev --no-install-project

COPY --exclude=.venv . .

FROM python:3.14-slim AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

ENV CONTAINER_PACKAGE_URL=mirrors.aliyun.com
RUN sed -i "s|deb.debian.org|${CONTAINER_PACKAGE_URL}|g" /etc/apt/sources.list.d/debian.sources

# 修改时区
ENV TZ=Asia/Shanghai
RUN apt-get update \
    && DEBIAN_FRONTEND="noninteractive" apt-get install -y --no-install-recommends tzdata curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app

# 设置环境变量：
# 确保 Python 输出直接打印到标准输出，方便查看容器日志
# 禁止生成 .pyc 字节码文件
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /app /app

RUN mkdir -p /app/storage/data /app/storage/logs \
    && chown -R app:app /app/storage/data /app/storage/logs

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s \
    --timeout=3s \
    --start-period=10s \
    --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
