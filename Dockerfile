FROM python:3.12-slim AS builder
ENV ENV=BUILD
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

FROM python:3.12-alpine
ENV ENV=PROD
ENV PYTHONUNBUFFERED=1 \
    SENTRY_ENVIRONMENT=${ENV} \
    PATH="/root/.local/bin:${PATH}"
WORKDIR /app
RUN apk add --no-cache ffmpeg
COPY pyproject.toml poetry.lock ./
ADD https://install.python-poetry.org install-poetry.py
RUN python install-poetry.py \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-root --no-cache --only main \
    && rm -f pyproject.toml poetry.lock install-poetry.py
COPY /src .
RUN adduser -D -u 1000 -s /sbin/nologin bot \
    && chown -R bot:bot /app
USER bot
ENTRYPOINT ["python", "main.py"]
