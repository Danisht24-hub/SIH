from celery_app import app
from config import load_settings
from scheduler import run_cycle


@app.task(name="tasks.collect_cycle")
def collect_cycle() -> dict:
    settings = load_settings()
    total = run_cycle(settings, [1, 7, 15, 30, 45])
    return {"status": "success", "observations": total}
