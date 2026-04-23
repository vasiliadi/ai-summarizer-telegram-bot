from typing import cast

import modal

image = modal.Image.debian_slim(python_version="3.14").uv_pip_install("redis")
secrets = modal.Secret.from_name("resetlimit-secrets")

app = modal.App(name="ResetLimit", image=image, secrets=[secrets])

with image.imports():
    import os

    import redis as redis_lib


@app.function(
    schedule=modal.Cron("0 0 * * *", timezone="America/Los_Angeles"),  # PST8PDT
    retries=modal.Retries(max_retries=3),
)
def clear_limit() -> int:
    """Delete all per-user daily limit keys (RPD:*) from Redis."""
    daily_limit_key = "RPD"
    rate_limiter_url = f"{os.environ['REDIS_URL']}/0"
    client = redis_lib.StrictRedis.from_url(url=rate_limiter_url, decode_responses=True)

    batch: list[str] = []
    deleted = 0
    for key in client.scan_iter(match=f"{daily_limit_key}:*", count=500):
        batch.append(key)
        if len(batch) >= 500:  # noqa: PLR2004
            deleted += cast("int", client.unlink(*batch))
            batch.clear()
    if batch:
        deleted += cast("int", client.unlink(*batch))
    return deleted
