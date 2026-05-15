"""
Management command: cleanup_deleted

Hard-deletes Projects and Tasks that have been soft-deleted for more than
24 hours.

Usage
-----
    python manage.py cleanup_deleted              # live run
    python manage.py cleanup_deleted --dry-run    # preview only, no changes

This command is called automatically by the Celery Beat periodic task
(tasks.tasks.cleanup_deleted_task) every day at 02:00 UTC.
It can also be run manually at any time.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from tasks.models import Project, Task


RECOVERY_WINDOW = timedelta(hours=24)


class Command(BaseCommand):
    help = "Hard-delete Projects and Tasks soft-deleted more than 24 hours ago."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without actually deleting anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = timezone.now() - RECOVERY_WINDOW

        # --- Tasks ----------------------------------------------------------
        expired_tasks = Task.all_objects.filter(
            is_deleted=True,
            deleted_at__lt=cutoff,
        )
        task_count = expired_tasks.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would hard-delete {task_count} task(s) "
                    f"soft-deleted before {cutoff.isoformat()}."
                )
            )
        else:
            for task in expired_tasks:
                task.delete(hard=True)
            self.stdout.write(
                self.style.SUCCESS(f"Hard-deleted {task_count} expired task(s).")
            )

        # --- Projects -------------------------------------------------------
        # Delete projects AFTER their tasks to avoid FK issues
        expired_projects = Project.all_objects.filter(
            is_deleted=True,
            deleted_at__lt=cutoff,
        )
        project_count = expired_projects.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would hard-delete {project_count} project(s) "
                    f"soft-deleted before {cutoff.isoformat()}."
                )
            )
        else:
            for project in expired_projects:
                project.delete(hard=True)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Hard-deleted {project_count} expired project(s)."
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("Dry run complete. No data was modified.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cleanup complete. "
                    f"Removed {task_count} task(s) and {project_count} project(s)."
                )
            )
