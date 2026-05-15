"""
Models for the Task Manager API.

Architecture
------------
SoftDeleteManager   — default manager: hides soft-deleted rows.
AllObjectsManager   — escape-hatch manager: shows everything (for trash/restore views).
SoftDeleteModel     — abstract base that both Project and Task inherit.
Project             — top-level grouping; has many Tasks (FK).
Task                — belongs to one Project.

Soft-delete lifecycle
---------------------
obj.delete()           → sets is_deleted=True, deleted_at=now  (reversible)
obj.restore()          → clears is_deleted, deleted_at
obj.delete(hard=True)  → calls super().delete() — permanent
obj.is_recoverable     → True if deleted_at is within the 24-hour window

Celery Beat runs cleanup_deleted_task() every day at 02:00 UTC, which calls
the cleanup_deleted management command to hard-delete anything past the window.
"""

from django.db import models
from django.utils import timezone
from datetime import timedelta


RECOVERY_WINDOW = timedelta(hours=24)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    """Default manager — only returns rows where is_deleted=False."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Bypass manager — returns ALL rows including soft-deleted ones."""

    def get_queryset(self):
        return super().get_queryset()


# ---------------------------------------------------------------------------
# Abstract base model
# ---------------------------------------------------------------------------

class SoftDeleteModel(models.Model):
    """
    Abstract base that gives every child model soft-delete behaviour.

    Fields added:
        is_deleted  — boolean flag, False by default
        deleted_at  — timestamp set when soft-deleted, None otherwise
        created_at  — auto timestamp on insert
        updated_at  — auto timestamp on every save
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Default manager hides deleted rows in normal queries
    objects = SoftDeleteManager()
    # Escape hatch: Project.all_objects.filter(is_deleted=True)
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    # -- Soft / hard delete --------------------------------------------------

    def delete(self, using=None, keep_parents=False, hard=False):
        """
        Soft delete by default.  Pass hard=True for a permanent delete.
        """
        if hard:
            super().delete(using=using, keep_parents=keep_parents)
        else:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=["is_deleted", "deleted_at"])

    # -- Restore -------------------------------------------------------------

    def restore(self):
        """Un-delete the object if still within the recovery window."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])

    # -- Recovery window check -----------------------------------------------

    @property
    def is_recoverable(self):
        """True while the item is still within the 24-hour undo window."""
        if not self.is_deleted or self.deleted_at is None:
            return False
        return timezone.now() - self.deleted_at <= RECOVERY_WINDOW


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class Project(SoftDeleteModel):
    """
    A container for related Tasks.

    GET /api/projects/          → all active projects (tasks nested)
    POST /api/projects/         → create project (optionally with tasks)
    DELETE /api/projects/{id}/  → soft delete
    POST /api/projects/{id}/restore/ → restore within 24 h
    DELETE /api/projects/{id}/hard-delete/ → permanent removal
    """

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Task(SoftDeleteModel):
    """
    A single to-do item that belongs to a Project.

    priority choices: low | med | high
    is_done: toggled by the client
    """

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("med", "Medium"),
        ("high", "High"),
    ]

    project = models.ForeignKey(
        Project,
        related_name="tasks",
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=200)
    is_done = models.BooleanField(default=False)
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="med",
    )

    class Meta:
        ordering = ["priority", "-created_at"]

    def __str__(self):
        return f"[{self.priority}] {self.title}"
