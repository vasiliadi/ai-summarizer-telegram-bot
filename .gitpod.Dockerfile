FROM python:3.11-slim
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg git \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
RUN echo '%gitpod ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/gitpod \
 && addgroup -g 33333 gitpod && adduser -u 33333 -G gitpod -h /home/gitpod -s /bin/bash -D gitpod
USER gitpod
WORKDIR /app
COPY . .
RUN pip install -r requirements-dev.txt
# ENTRYPOINT ["python", "main.py"]