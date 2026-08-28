from celery import Celery

from volley_worker.config import get_settings

settings = get_settings()

celery_app = Celery("volley_worker", broker=settings.valkey_url, backend=settings.valkey_url)
celery_app.conf.update(
    task_acks_late=True,  # redelivered if the worker dies mid-task, not lost
    worker_prefetch_multiplier=1,  # don't hoard tasks other workers could run
    task_default_retry_delay=10,
    task_track_started=True,
    timezone="UTC",
)

celery_app.autodiscover_tasks(["volley_worker"])
