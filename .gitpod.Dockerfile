FROM python:3.11-slim
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg git \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -l -u 33333 -G sudo -md /home/gitpod -s /bin/bash -p gitpod gitpod
USER gitpod
WORKDIR /app
COPY . .
RUN pip install -r requirements-dev.txt
# ENTRYPOINT ["python", "main.py"]