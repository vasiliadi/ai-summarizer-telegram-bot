FROM python:3.12-slim AS builder
ENV ENV=BUILD
ARG DSN
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY . .
RUN pip wheel --wheel-dir /app/wheels -r requirements.txt
RUN pip install --no-cache-dir -r requirements-build.txt \
    && python db.py \
    && alembic upgrade head

FROM python:3.12-slim
ENV ENV=PROD
ENV SENTRY_ENVIRONMENT=${ENV}
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/src .
RUN pip install --no-cache-dir /wheels/*
RUN apk update && apk add --no-cache bash \
        alsa-lib \
        at-spi2-atk \
        atk \
        cairo \
        cups-libs \
        dbus-libs \
        eudev-libs \
        expat \
        flac \
        gdk-pixbuf \
        glib \
        libgcc \
        libjpeg-turbo \
        libpng \
        libwebp \
        libx11 \
        libxcomposite \
        libxdamage \
        libxext \
        libxfixes \
        tzdata \
        libexif \
        udev \
        xvfb \
        zlib-dev \
        chromium \
        chromium-chromedriver
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["python", "main.py"]
