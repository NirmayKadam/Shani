"""
File Overview: Celery application configuration for background tasks and periodic polling.

All Functions/Classes:
- celery_app (instance): Configures task routes, broker/backend, and periodic beat schedule. Data: Redis -> Task Queues.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
import os

from celery import Celery

celery_app = Celery(
    "AlphaStreams",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "domains.ingestion.application.tasks.ingestion_tasks",
        "domains.ingestion.application.tasks.market_tasks",
        "domains.analytics.application.tasks.ml_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "domains.ingestion.application.tasks.ingestion_tasks.*": {"queue": "ingestion"},
        "domains.ingestion.application.tasks.market_tasks.*": {"queue": "ingestion"},
        "domains.analytics.application.tasks.*": {"queue": "analytics"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    "poll_news_headlines": {
        "task": "ingestion.poll_news",
        "schedule": float(os.getenv("NEWS_POLL_INTERVAL_SECONDS", "120")),
    },
    "poll_market_prices": {
        "task": "ingestion.poll_prices",
        "schedule": float(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "15")),
    },
    "poll_option_chains": {
        "task": "ingestion.fetch_and_publish_options",
        "schedule": float(os.getenv("OPTIONS_POLL_INTERVAL_SECONDS", "30")),
    },
}

celery_app = celery_app
