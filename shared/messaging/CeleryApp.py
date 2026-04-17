from celery import Celery

# TODO: read from env var config
celery_app = Celery("alphastreams", broker="redis://localhost:6379/0", backend="redis://localhost:6379/1")

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        'domains.analytics.tasks.NlpTasks.*': {'queue': 'nlp'},
        'domains.analytics.tasks.DerivativesTasks.*': {'queue': 'derivatives'},
        'domains.analytics.tasks.AlertTasks.*': {'queue': 'alerts'},
        'domains.analytics.tasks.MLTasks.*': {'queue': 'ml'},
    }
)
