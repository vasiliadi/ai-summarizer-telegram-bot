FROM python:3.11-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

FROM python:3.11-slim
ENV ENV=PROD
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY . .
RUN pip install --no-cache /wheels/*
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["python", "main.py"]
