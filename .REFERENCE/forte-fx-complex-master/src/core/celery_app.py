from celery import Celery

from src.core.config import redis_settings

celery_app = Celery(
    "contracts_service",
    broker=redis_settings.CELERY_BROKER_URL,
    backend=redis_settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    worker_pool="prefork",            # processes (safe for Tesseract)
    worker_concurrency=5,             # = number of OCR slots (engines)
    worker_prefetch_multiplier=1,     # fairness; no head-of-line blocking
    worker_max_tasks_per_child=50,    # recycle to avoid leaks
    worker_max_memory_per_child=800000,  # ~800 MB in KB; kill+respawn if exceeded
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=1500,
    task_time_limit=1800,
    broker_transport_options={"visibility_timeout": 3600},
)

celery_app.conf.task_routes = {"src.contracts.tasks.*": {"queue": "contracts"}}
celery_app.autodiscover_tasks(["src.contracts"])
