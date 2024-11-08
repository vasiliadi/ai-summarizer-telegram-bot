FROM python:3.12-slim AS builder
ENV ENV=BUILD
ARG DSN
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY . .
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /app/wheels -r requirements.txt
RUN pip install --no-cache-dir -r requirements-build.txt \
    && python db.py \
    && alembic upgrade head

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
    ffmpeg=7:* \
    chromium-driver=130.* \
    xvfb=2:* \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r -u 1000 bot --shell /bin/false \
    && chown -R bot:bot /app \
    && chown -R bot:bot /usr/local/lib/python3.12/site-packages/seleniumbase
USER bot
ENTRYPOINT ["./entrypoint.sh"]
