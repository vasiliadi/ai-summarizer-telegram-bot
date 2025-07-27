import modal

image = modal.Image.from_registry("python:3.13-slim").pip_install("rush[redis]")
secrets = modal.Secret.from_name("resetlimit-secrets")

app = modal.App(name="ResetLimit", image=image, secrets=[secrets])

with image.imports():
    import os
    from rush import quota, throttle
    from rush.limiters import periodic
    from rush.stores import redis as redis_store
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from rush.result import RateLimitResult


@app.function(
    schedule=modal.Cron("0 0 * * *", timezone="America/Los_Angeles"),  # PST8PDT
    retries=modal.Retries(max_retries=3),
)
def clear_limit() -> "RateLimitResult":
    # Duplicated from config.py
    REDIS_URL = os.environ["REDIS_URL"]
    RATE_LIMITER_URL = f"{REDIS_URL}/0"
    DAILY_LIMIT = 1500
    DAILY_LIMIT_KEY = "RPD"

    per_day_limit = throttle.Throttle(
        limiter=periodic.PeriodicLimiter(
            store=redis_store.RedisStore(url=RATE_LIMITER_URL),
        ),
        rate=quota.Quota.per_day(
            count=DAILY_LIMIT,
        ),
    )
    # End duplication
    return per_day_limit.clear(DAILY_LIMIT_KEY)
