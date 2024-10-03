FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements-dev.txt
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg git \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
# ENTRYPOINT ["python", "main.py"]