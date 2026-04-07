FROM python:3.14-rc-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

FROM python:3.14-rc-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}"
WORKDIR /app

COPY --from=builder /app /app

EXPOSE 8000
