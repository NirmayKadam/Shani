import os
from celery import Celery

CeleryApp = Celery(
    "AlphaStreams",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "domains.ingestion.application.tasks.IngestionTasks",
        "domains.analytics.application.tasks.MLTasks",
    ],
)

CeleryApp.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "domains.ingestion.application.tasks.IngestionTasks.*": {"queue": "ingestion"},
        "domains.analytics.application.tasks.*": {"queue": "analytics"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

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

celery_app = CeleryApp
