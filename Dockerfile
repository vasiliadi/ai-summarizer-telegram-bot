FROM python:3.14-slim AS builder
ENV ENV=BUILD \
    PYTHONDONTWRITEBYTECODE=1
ARG DSN
ARG MODAL_TOKEN_ID
ARG MODAL_TOKEN_SECRET
WORKDIR /app
COPY . .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
RUN uv pip install --no-cache --system -r requirements-build.txt
RUN python scripts/db.py \
    && alembic upgrade head \
    && modal deploy scripts/cron.py

FROM python:3.14-alpine
ENV ENV=PROD \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
ENV SENTRY_ENVIRONMENT=${ENV}
WORKDIR /app
RUN apk add --no-cache ffmpeg deno
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync \
    --frozen \
    --no-dev \
    --compile-bytecode \
    --no-managed-python \
    && rm -f pyproject.toml uv.lock
COPY --from=builder /app/src .
RUN adduser -D -u 1000 -s /sbin/nologin bot \
    && chown -R bot:bot /app
USER bot
ENTRYPOINT ["python", "main.py"]
