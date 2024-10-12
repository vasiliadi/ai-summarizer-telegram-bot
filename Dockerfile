ARG TG_API_TOKEN
ARG GEMINI_API_KEY
ARG REPLICATE_API_TOKEN
ARG DSN

FROM python:3.12-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TG_API_TOKEN=$TG_API_TOKEN
ENV GEMINI_API_KEY=$GEMINI_API_KEY
ENV REPLICATE_API_TOKEN=$REPLICATE_API_TOKEN
ENV DSN=$DSN
COPY . .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
RUN alembic upgrade head

FROM python:3.12-slim
ENV ENV=PROD
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/src .
RUN pip install --no-cache /wheels/*
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["python", "main.py"]
