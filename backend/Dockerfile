# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY app ./app

RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt \
    && uv pip install --system --no-cache-dir -r requirements.txt \
    && uv pip install --system --no-cache-dir --no-deps .

FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations

RUN mkdir -p /app/var/storage && chown -R appuser:appuser /app/var

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
