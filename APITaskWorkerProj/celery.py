"""
Celery application configuration.

This module is imported by taskapi_project/__init__.py so that the Celery
app is available as soon as Django loads. Celery Beat uses this app to
schedule and dispatch periodic tasks.
"""

import os
from celery import Celery

# Tell Celery which Django settings module to use
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "APITaskWorkerProj.settings")

app = Celery("APITaskWorkerProj")

# Read all CELERY_* settings from Django's settings.py
# namespace="CELERY" means every setting key must start with CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py files inside every INSTALLED_APP
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Utility task — prints the request object. Used to verify Celery works."""
    print(f"Request: {self.request!r}")
