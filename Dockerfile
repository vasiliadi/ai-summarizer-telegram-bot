FROM python:3.13-slim AS builder
ENV ENV=BUILD
ARG DSN
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY . .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt
RUN pip install --no-cache-dir -r requirements-build.txt \
    && python db.py \
    && alembic upgrade head

FROM python:3.13-slim
ENV ENV=PROD
ENV SENTRY_ENVIRONMENT=${ENV}
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/src .
RUN pip install --no-cache-dir /wheels/*
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["python", "main.py"]
