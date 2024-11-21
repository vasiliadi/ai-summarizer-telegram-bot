FROM python:3.12-slim AS builder
ENV ENV=BUILD
ARG DSN
ARG MODAL_TOKEN_ID
ARG MODAL_TOKEN_SECRET
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY . .
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /app/wheels -r requirements.txt
RUN pip install --no-cache-dir -r requirements-build.txt \
    && python db.py \
    && alembic upgrade head
RUN modal token set --token-id ${MODAL_TOKEN_ID} --token-secret ${MODAL_TOKEN_SECRET} \
    && modal deploy cron/cron.py

FROM python:3.12-slim
ENV ENV=PROD
ENV SENTRY_ENVIRONMENT=${ENV}
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/src .
COPY --from=builder /app/entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh
RUN pip install --upgrade pip \
    && pip install --no-cache-dir /wheels/*
RUN apt-get update && apt-get install --no-install-recommends -y \
    ffmpeg \
    chromium-driver \
    xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r -m -u 1000 bot --shell /bin/false \
    && chown -R bot:bot /app \
    && chown -R bot:bot /usr/local/lib/python3.12/site-packages/seleniumbase
USER bot
ENTRYPOINT ["./entrypoint.sh"]
