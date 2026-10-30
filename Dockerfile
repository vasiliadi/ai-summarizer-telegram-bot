# Deploy steps for compose.yaml, run as a container so secrets arrive at run time, never as build
# ARGs. Railway never builds this stage; .github/workflows/deploy.yml runs the same steps there.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS migrate
ENV ENV=BUILD \
    PATH="/app/.venv/bin:$PATH" \
    MODAL_BUILD_VALIDATION=ignore
WORKDIR /app
COPY . .
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc /uv /bin/
RUN uv sync \
    --frozen \
    --only-group build \
    --no-cache \
    --no-managed-python
CMD ["sh", "-c", "python scripts/db.py && alembic upgrade head && modal deploy scripts/cron.py"]

FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS base

FROM base AS deps
# uv's python-build-standalone interpreter is faster than the Docker Hub build.
ENV UV_PYTHON_INSTALL_DIR=/opt/python
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc /uv /bin/
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync \
    --frozen \
    --no-cache \
    --no-group dev \
    --no-group test \
    --no-group modal \
    --no-group build \
    --compile-bytecode \
    --managed-python

# The bot: must stay the last stage, which Railway builds when no target is set.
FROM base
ENV ENV=PROD \
    PYTHONUNBUFFERED=1 \
    DENO_V8_FLAGS="--max-old-space-size=256" \
    PATH="/app/.venv/bin:$PATH"
ENV SENTRY_ENVIRONMENT=${ENV} \
    LANGFUSE_TRACING_ENVIRONMENT=prod
WORKDIR /app
RUN apk add --no-cache ffmpeg deno
# The bot downloads into its CWD; everything it runs stays root-owned.
RUN adduser -D -u 1000 -s /sbin/nologin bot \
    && chown bot:bot /app
COPY --from=deps /opt/python /opt/python
COPY --from=deps /app/.venv /app/.venv
COPY LICENSE NOTICE ./
COPY src/ .
USER bot
ENTRYPOINT ["python", "main.py"]
