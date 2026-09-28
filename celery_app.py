from celery import Celery
from config import load_settings

settings = load_settings()
redis_url = __import__("os").getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery("comparify", broker=redis_url, backend=redis_url)
app.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "collect-airfare-every-six-hours": {
            "task": "tasks.collect_cycle",
            "schedule": max(settings.scrape_interval_seconds, 3600),
        },
    },
)
