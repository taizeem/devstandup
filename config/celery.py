import os
from celery import Celery

# Set standard Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "devstandup.settings")

app = Celery("devstandup")

# Read configuration from Django settings using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps (looks for tasks.py)
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")