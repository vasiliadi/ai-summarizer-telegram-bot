FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc AS builder
ENV ENV=BUILD \
    PATH="/app/.venv/bin:$PATH" \
    MODAL_BUILD_VALIDATION=ignore
ARG DSN
ARG MODAL_TOKEN_ID
ARG MODAL_TOKEN_SECRET
WORKDIR /app
COPY . .
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /bin/
RUN uv sync \
    --frozen \
    --only-group build \
    --no-cache \
    --no-managed-python
RUN python scripts/db.py \
    && alembic upgrade head \
    && modal deploy scripts/cron.py

FROM python:3.14-alpine@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc
ENV ENV=PROD \
    PYTHONUNBUFFERED=1 \
    DENO_V8_FLAGS="--max-old-space-size=256" \
    PATH="/app/.venv/bin:$PATH"
ENV SENTRY_ENVIRONMENT=${ENV} \
    LANGFUSE_TRACING_ENVIRONMENT=prod
WORKDIR /app
RUN apk add --no-cache ffmpeg deno
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /bin/
COPY pyproject.toml uv.lock LICENSE NOTICE ./
RUN uv sync \
    --frozen \
    --no-cache \
    --no-group dev \
    --no-group test \
    --no-group modal \
    --no-group build \
    --compile-bytecode \
    --no-managed-python
COPY --from=builder /app/src .
RUN adduser -D -u 1000 -s /sbin/nologin bot \
    && chown -R bot:bot /app
USER bot
ENTRYPOINT ["python", "main.py"]
