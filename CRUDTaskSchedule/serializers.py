"""
Serializers for Project and Task.

ProjectSerializer uses a nested TaskSerializer so that a single POST/PUT
to /api/projects/ can create or replace child tasks in one request.

DRF does NOT auto-handle nested writes, so we override create() and update()
explicitly — the docstrings explain the strategy used for each.
"""

from rest_framework import serializers
from .models import Project, Task


class TaskSerializer(serializers.ModelSerializer):
    """
    Flat serializer for Task.

    Used stand-alone by TaskViewSet AND as a nested serializer inside
    ProjectSerializer.  When nested, the 'project' field is excluded
    because the parent already owns that relationship.
    """

    class Meta:
        model = Task
        fields = [
            "id",
            "project",
            "title",
            "is_done",
            "priority",
            "created_at",
            "updated_at",
        ]
        # project is set automatically by the ViewSet (from URL kwargs)
        # when tasks are created stand-alone via /api/tasks/
        read_only_fields = ["id", "created_at", "updated_at"]


class TaskNestedSerializer(serializers.ModelSerializer):
    """
    Minimal Task serializer used inside ProjectSerializer.
    'project' is excluded — it's implied by the parent.
    """

    class Meta:
        model = Task
        fields = ["id", "title", "is_done", "priority", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProjectSerializer(serializers.ModelSerializer):
    """
    Full Project serializer with nested tasks.

    Read  → each project returns its tasks inline.
    Write → tasks list is optional; if provided, tasks are created/replaced.

    Nested write strategy on UPDATE:
        Replace — existing tasks are soft-deleted, new ones created.
        Omit the 'tasks' key entirely to leave existing tasks untouched.
    """

    tasks = TaskNestedSerializer(many=True, required=False)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "created_at",
            "updated_at",
            "tasks",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # -- Nested CREATE -------------------------------------------------------

    def create(self, validated_data):
        """
        Pop nested tasks, create the project, then bulk-create tasks.
        validated_data arrives clean — DRF ran field validation already.
        """
        tasks_data = validated_data.pop("tasks", [])
        project = Project.objects.create(**validated_data)
        for task_data in tasks_data:
            Task.objects.create(project=project, **task_data)
        return project

    # -- Nested UPDATE -------------------------------------------------------

    def update(self, instance, validated_data):
        """
        Update scalar fields.
        If 'tasks' key is present → soft-delete old tasks, create new ones.
        If 'tasks' key is absent (PATCH without it) → leave tasks alone.
        """
        tasks_data = validated_data.pop("tasks", None)

        # Update scalar fields on the instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tasks_data is not None:
            # Replace strategy: soft-delete every current task, recreate from payload
            for task in instance.tasks.all():
                task.delete()  # soft delete
            for task_data in tasks_data:
                Task.objects.create(project=instance, **task_data)

        return instance
