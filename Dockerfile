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

ENV CONTAINER_PACKAGE_URL=mirrors.aliyun.com
RUN sed -i "s|deb.debian.org|${CONTAINER_PACKAGE_URL}|g" /etc/apt/sources.list.d/debian.sources

# 修改时区
ENV TZ=Asia/Shanghai
RUN apt-get update \
    && DEBIAN_FRONTEND="noninteractive" apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置环境变量：
# 确保 Python 输出直接打印到标准输出，方便查看容器日志
# 禁止生成 .pyc 字节码文件
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /app /app

EXPOSE 8000
