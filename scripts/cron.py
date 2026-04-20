import modal

image = modal.Image.debian_slim(python_version="3.14").uv_pip_install("rush[redis]")
secrets = modal.Secret.from_name("resetlimit-secrets")

app = modal.App(name="ResetLimit", image=image, secrets=[secrets])

with image.imports():
    import os
    from typing import TYPE_CHECKING

    from rush import quota, throttle
    from rush.limiters import periodic
    from rush.stores import redis as redis_store

    if TYPE_CHECKING:
        from rush.result import RateLimitResult


@app.function(
    schedule=modal.Cron("0 0 * * *", timezone="America/Los_Angeles"),  # PST8PDT
    retries=modal.Retries(max_retries=3),
)
def clear_limit() -> "RateLimitResult":
    """Clear the per-day rate limit key in Redis."""
    # Duplicated from config.py
    redis_url = os.environ["REDIS_URL"]
    rate_limiter_url = f"{redis_url}/0"
    daily_limit = 20
    daily_limit_key = "RPD"

    per_day_limit = throttle.Throttle(
        limiter=periodic.PeriodicLimiter(
            store=redis_store.RedisStore(
                url=rate_limiter_url,
                client=redis_store.redis.StrictRedis.from_url(
                    url=rate_limiter_url,
                    decode_responses=True,
                ),
            ),
        ),
        rate=quota.Quota.per_day(
            count=daily_limit,
        ),
    )
    # End duplication
    return per_day_limit.clear(daily_limit_key)
