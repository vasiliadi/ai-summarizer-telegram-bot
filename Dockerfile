FROM python:3.12-slim AS builder
ENV ENV=BUILD
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG DSN
ARG MODAL_TOKEN_ID
ARG MODAL_TOKEN_SECRET
WORKDIR /app
COPY . .
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    uv pip install --no-cache --system -r requirements-build.txt \
    && python db.py \
    && alembic upgrade head \
    && modal token set --token-id ${MODAL_TOKEN_ID} --token-secret ${MODAL_TOKEN_SECRET} \
    && modal deploy cron/cron.py

FROM python:3.12-slim
ENV ENV=PROD
ENV SENTRY_ENVIRONMENT=${ENV}
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
WORKDIR /app
COPY --from=builder /app/src .
COPY --from=builder /app/entrypoint.sh .
RUN chmod +x entrypoint.sh
RUN apt-get update && apt-get install --no-install-recommends -y \
    ffmpeg \
    chromium-driver \
    xvfb \
    curl \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.local/bin:${PATH}"
RUN --mount=from=builder,source=/app/pyproject.toml,target=pyproject.toml \
    --mount=from=builder,source=/app/poetry.lock,target=poetry.lock \
    poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-root --no-cache --only main
RUN useradd -r -m -u 1000 bot --shell /bin/false \
    && chown -R bot:bot /app \
    && chown -R bot:bot /usr/local/lib/python3.12/site-packages/seleniumbase
USER bot
ENTRYPOINT ["./entrypoint.sh"]
