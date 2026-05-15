"""
Celery tasks for the tasks app.

Why a separate tasks.py?
    Celery's autodiscover_tasks() scans every installed app for a file
    named tasks.py and registers whatever it finds there.  This is the
    standard convention — don't rename it.

cleanup_deleted_task
    Called by Celery Beat on schedule (see CELERY_BEAT_SCHEDULE in settings).
    Delegates the actual deletion logic to the cleanup_deleted management
    command so the same logic can be triggered from the CLI too.

    Flow:
        Celery Beat (scheduler) fires at 02:00 UTC every day
            → enqueues cleanup_deleted_task on the default queue
                → a Celery worker picks it up
                    → calls management command
                        → hard-deletes items whose deleted_at > 24 h ago
"""

from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)


@shared_task(name="tasks.tasks.cleanup_deleted_task", bind=True, max_retries=3)
def cleanup_deleted_task(self):
    """
    Periodic task: hard-delete Projects and Tasks that were soft-deleted
    more than 24 hours ago.

    bind=True     → gives us access to self (the task instance) for retries.
    max_retries=3 → Celery will retry up to 3 times on unexpected exceptions.
    """
    try:
        logger.info("cleanup_deleted_task: starting scheduled cleanup")
        call_command("cleanup_deleted")
        logger.info("cleanup_deleted_task: completed successfully")
    except Exception as exc:
        logger.error("cleanup_deleted_task: failed — %s", exc)
        # Exponential back-off: 60 s, 120 s, 240 s
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
