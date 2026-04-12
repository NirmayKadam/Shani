# app/celery_app.py — Single source of truth for Celery
#
# All docker-compose workers reference:  celery -A app.celery_app
# Celery auto-discovers the `app` attribute in this module.

import os
from celery import Celery
from celery.schedules import crontab

CeleryApp = Celery(
    "AlphaStreams",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    include=[
        "app.domain.ingestion.tasks",
    ],
)

CeleryApp.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="Asia/Kolkata",
    enable_utc=True,

    # Queue routing — each worker listens on its own queue
    task_routes={
        "app.domain.ingestion.tasks.*":   {"queue": "ingestion"},
    },

    # Sensible defaults
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

# ── Celery Beat Schedule ────────────────────────────────────────
CeleryApp.conf.beat_schedule = {
    "poll_news_headlines": {
        "task": "ingestion.poll_news",
        "schedule": float(os.getenv("NEWS_POLL_INTERVAL_SECONDS", "120")),
    },
    "poll_market_prices": {
        "task": "ingestion.poll_prices",
        "schedule": float(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "15")),
    },
    "poll_option_chains": {
        "task": "ingestion.poll_options",
        "schedule": float(os.getenv("OPTIONS_POLL_INTERVAL_SECONDS", "30")),
    },
}

# Celery CLI looks for an attribute named `app` or `celery`
app = CeleryApp
