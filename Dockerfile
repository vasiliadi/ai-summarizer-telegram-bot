FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=BUILD
ARG DSN
ARG MODAL_TOKEN_ID
ARG MODAL_TOKEN_SECRET
WORKDIR /app
COPY requirements-build.txt .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
RUN uv pip install --no-cache --system -r requirements-build.txt
COPY . .
RUN python db.py \
    && alembic upgrade head \
    && modal deploy cron/cron.py

FROM python:3.12-slim
ENV ENV=PROD
ENV PYTHONUNBUFFERED=1 \
    SENTRY_ENVIRONMENT=${ENV} \
    DISPLAY=:99 \
    PATH="/root/.local/bin:${PATH}"
WORKDIR /app
RUN apt-get update && apt-get install --no-install-recommends -y \
    ffmpeg \
    chromium-driver \
    xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml poetry.lock ./
ADD https://install.python-poetry.org install-poetry.py
RUN python install-poetry.py \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-root --no-cache --only main \
    && rm -f pyproject.toml poetry.lock install-poetry.py
COPY --from=builder /app/src .
COPY --from=builder /app/entrypoint.sh .
RUN chmod +x entrypoint.sh \
    && useradd -r -m -u 1000 bot --shell /bin/false \
    && chown -R bot:bot /app \
    && chown -R bot:bot /usr/local/lib/python3.12/site-packages/seleniumbase
USER bot
ENTRYPOINT ["./entrypoint.sh"]
