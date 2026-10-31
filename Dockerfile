# Deploy steps for compose.yaml, run as a container so secrets arrive at run time, never as build
# ARGs. A build with no target skips this stage; .github/workflows/deploy.yml runs the same steps.
# Managed Python like the bot: a python:*-slim image ships a new patch later than uv can install it.
FROM debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4 AS migrate
ENV ENV=BUILD \
    PATH="/app/.venv/bin:$PATH" \
    MODAL_BUILD_VALIDATION=ignore \
    UV_PYTHON_INSTALL_DIR=/opt/python
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /bin/
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync \
    --frozen \
    --only-group build \
    --no-cache \
    --managed-python
# migrations/env.py imports src.models; alembic.ini puts . and src on sys.path.
COPY alembic.ini ./
COPY migrations/ migrations/
COPY src/ src/
COPY scripts/__init__.py scripts/db.py scripts/cron.py scripts/
CMD ["sh", "-c", "python scripts/db.py && alembic upgrade head && modal deploy scripts/cron.py"]

FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS base

FROM base AS deps
# uv's python-build-standalone interpreter is faster than the Docker Hub build.
ENV UV_PYTHON_INSTALL_DIR=/opt/python
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /bin/
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

# The bot: must stay the last stage, which a build with no target produces.
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
COPY LICENSE NOTICE src/ ./
USER bot
ENTRYPOINT ["python", "main.py"]
