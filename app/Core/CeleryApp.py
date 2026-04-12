# app/CeleryApp.py  —  Single source of truth for Celery
#
# All docker-compose workers reference:  celery -A app.CeleryApp
# Celery auto-discovers the `app` attribute in this module.

import os
from celery import Celery

CeleryApp = Celery(
    "AlphaStreams",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    include=[
        "app.NewsSentiment.Tasks",
        "app.NewsSentiment.Tasks",
        "app.Derivatives.Tasks",
        "app.NewsSentiment.Tasks",
        "app.MLForecasting.Tasks",
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
        "app.NewsSentiment.Tasks.*":        {"queue": "ingestion"},
        "app.NewsSentiment.Tasks.*":    {"queue": "nlp"},
        "app.Derivatives.Tasks.*": {"queue": "derivatives"},
        "app.NewsSentiment.Tasks.*":        {"queue": "signals"},
        "app.MLForecasting.Tasks.*":      {"queue": "nlp"}, # Reusing NLP worker for ML inferences
    },

    # Sensible defaults
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

# ── Celery Beat Schedule ────────────────────────────────────
from celery.schedules import crontab
CeleryApp.conf.beat_schedule = {
    "run_news_ingestion": {
        "task": "ingestion.run_news_cycle",
        "schedule": float(os.getenv("NEWS_POLL_INTERVAL_SECONDS", "120")),
    },
    "run_tick_ingestion": {
        "task": "ingestion.run_tick_cycle",
        "schedule": float(os.getenv("TICK_POLL_INTERVAL_SECONDS", "60")),
    },
    # Run ML Model immediately after market closes (3:45 PM IST = 10:15 UTC internally, but tz is handled)
    "run_eod_ml_predictions": {
        "task": "ml.run_daily_predictions",
        "schedule": crontab(hour=15, minute=45, day_of_week="1-5"), # Mon-Fri
    },
}

# Celery CLI looks for an attribute named `app` or `celery`
app = CeleryApp
