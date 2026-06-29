from celery import Celery
from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "AlphaStreams",
    broker=settings.RedisUrl,
    backend=settings.RedisUrl,
    include=[
        "domains.ingestion.tasks.ingestion_tasks",
        "domains.ingestion.tasks.market_tasks",
        "domains.analytics.tasks.ml_tasks",
        "domains.analytics.tasks.alert_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "ingestion.*": {"queue": "ingestion"},
        "analytics.*": {"queue": "analytics"},
        "domains.ingestion.tasks.*": {"queue": "ingestion"},
        "domains.analytics.tasks.*": {"queue": "analytics"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    "poll_news_headlines": {
        "task": "ingestion.poll_news",
        "schedule": float(settings.NewsPollIntervalSeconds),
    },
    "poll_market_prices": {
        "task": "ingestion.poll_prices",
        "schedule": float(settings.PricePollIntervalSeconds),
    },
    "poll_option_chains": {
        "task": "ingestion.poll_options",
        "schedule": float(settings.OptionsPollIntervalSeconds),
    },
}
