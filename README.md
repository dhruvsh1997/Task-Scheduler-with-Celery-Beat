# Task Manager API

A Django REST Framework API with soft-delete, nested serializers, and automated cleanup via **Celery Beat**.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture at a Glance](#2-architecture-at-a-glance)
3. [Prerequisites](#3-prerequisites)
4. [Installation](#4-installation)
5. [Running the Project](#5-running-the-project)
6. [API Reference](#6-api-reference)
7. [What is Celery?](#7-what-is-celery)
8. [What is Celery Beat?](#8-what-is-celery-beat)
9. [How Celery Beat is Configured Here](#9-how-celery-beat-is-configured-here)
10. [Running Celery & Celery Beat](#10-running-celery--celery-beat)
11. [The Soft-Delete Lifecycle](#11-the-soft-delete-lifecycle)
12. [Management Command: cleanup_deleted](#12-management-command-cleanup_deleted)
13. [Project Structure](#13-project-structure)
14. [Common Issues & FAQ](#14-common-issues--faq)

---

## 1. Project Overview

This API manages **Projects** and **Tasks**:

- A **Project** groups related tasks together.
- A **Task** belongs to exactly one Project and has a title, priority (`low` / `med` / `high`), and a `is_done` flag.

Key features:

| Feature | How it works |
|---|---|
| Full CRUD | DRF ModelViewSet + Router auto-generates all endpoints |
| Nested writes | POST a project **with** its tasks in one request |
| Soft delete | Records are flagged `is_deleted=True` instead of removed |
| 24-hour undo window | Deleted items appear in a "trash" endpoint for 24 h |
| Automated hard delete | Celery Beat runs every night at 02:00 UTC and permanently removes expired items |

---

## 2. Architecture at a Glance

```
HTTP Request
    │
    ▼
DRF Router (/api/projects/, /api/tasks/)
    │
    ▼
ViewSet (ProjectViewSet / TaskViewSet)
    │         │
    │         └─ @action endpoints: /trash/, /restore/, /hard-delete/
    ▼
Serializer (validates & converts JSON ↔ Python)
    │
    ▼
Model (Project / Task — both extend SoftDeleteModel)
    │
    ▼
Database (SQLite in dev, Postgres recommended for prod)

                    ┌─────────────────────────────┐
                    │  Celery Beat (scheduler)     │
                    │  fires at 02:00 UTC daily    │
                    └──────────────┬──────────────┘
                                   │ enqueues task
                    ┌──────────────▼──────────────┐
                    │  Redis (message broker)      │
                    └──────────────┬──────────────┘
                                   │ delivers task
                    ┌──────────────▼──────────────┐
                    │  Celery Worker               │
                    │  runs cleanup_deleted_task() │
                    │  → calls management command  │
                    │  → hard-deletes expired rows │
                    └─────────────────────────────┘
```

---

## 3. Prerequisites

You need the following installed on your machine **before** starting:

### Python 3.10+
```bash
python --version   # should print 3.10 or higher
```

### Redis
Redis is the **message broker** — it's the middleman between Celery Beat (which schedules jobs) and Celery workers (which run them). Think of it as a post office: Beat drops a letter in, the worker picks it up.

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis   # start Redis in the background
```

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl enable --now redis-server
```

**Windows:**
Redis doesn't have official Windows support. Use either:
- [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) (recommended) and follow the Ubuntu steps above, or
- [Docker](https://www.docker.com/): `docker run -d -p 6379:6379 redis:alpine`

**Verify Redis is running:**
```bash
redis-cli ping   # should print PONG
```

---

## 4. Installation

```bash
# 1. Clone / download the project
cd taskapi_project

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate      # macOS/Linux
# venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Open .env and set SECRET_KEY to any long random string.
# REDIS_URL defaults to redis://localhost:6379/0 — change if your Redis is elsewhere.

# 5. Apply database migrations
#    This creates all tables INCLUDING django_celery_beat's schedule tables.
python manage.py migrate

# 6. (Optional but recommended) Create a superuser for the admin panel
python manage.py createsuperuser
```

---

## 5. Running the Project

You need **three separate terminal windows** for the full experience:

### Terminal 1 — Django development server
```bash
source venv/bin/activate
python manage.py runserver
```
API is now at: http://localhost:8000/api/

### Terminal 2 — Celery worker
```bash
source venv/bin/activate
celery -A APITaskWorkerProj worker --loglevel=info
```

### Terminal 3 — Celery Beat (scheduler)
```bash
source venv/bin/activate
celery -A APITaskWorkerProj beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

> **Why three terminals?** Django serves HTTP requests. The Celery worker runs background tasks. Celery Beat is a clock that tells the worker *when* to run scheduled tasks. They are separate processes and must all be running for the full stack to work.

---

## 6. API Reference

Base URL: `http://localhost:8000/api/`

> **Tip:** Visit any URL in your browser — DRF's browsable API lets you read and POST/PUT/DELETE directly without Postman.

### Projects

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/api/projects/` | List all active projects (with nested tasks) |
| `POST` | `/api/projects/` | Create a project (optionally with tasks) |
| `GET` | `/api/projects/{id}/` | Retrieve one project |
| `PUT` | `/api/projects/{id}/` | Full update |
| `PATCH` | `/api/projects/{id}/` | Partial update |
| `DELETE` | `/api/projects/{id}/` | **Soft delete** (recoverable for 24 h) |
| `GET` | `/api/projects/trash/` | List soft-deleted projects still in window |
| `POST` | `/api/projects/{id}/restore/` | Restore a soft-deleted project |
| `DELETE` | `/api/projects/{id}/hard-delete/` | Permanent delete (no undo) |

### Tasks

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/api/tasks/` | List all active tasks (`?project=<id>` to filter) |
| `POST` | `/api/tasks/` | Create a task |
| `GET` | `/api/tasks/{id}/` | Retrieve one task |
| `PUT` | `/api/tasks/{id}/` | Full update |
| `PATCH` | `/api/tasks/{id}/` | Partial update (great for toggling `is_done`) |
| `DELETE` | `/api/tasks/{id}/` | Soft delete |
| `GET` | `/api/tasks/trash/` | Trash bin |
| `POST` | `/api/tasks/{id}/restore/` | Restore |
| `DELETE` | `/api/tasks/{id}/hard-delete/` | Permanent delete |

### Example: Create a project with tasks

```bash
curl -X POST http://localhost:8000/api/projects/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Website Redesign",
    "description": "Q3 rebrand",
    "tasks": [
      {"title": "Write copy", "priority": "high"},
      {"title": "Design mockups", "priority": "med"}
    ]
  }'
```

### Example: Toggle a task done

```bash
curl -X PATCH http://localhost:8000/api/tasks/1/ \
  -H "Content-Type: application/json" \
  -d '{"is_done": true}'
```

---

## 7. What is Celery?

**Celery** is a task queue library for Python. It lets you run code *outside* the normal HTTP request-response cycle — either immediately in the background, or on a schedule.

### Why do you need it?

Imagine a user clicks "Delete" and your view needs to:
1. Soft-delete the record immediately (fast — done in the view).
2. Hard-delete it 24 hours later (can't block the HTTP response for 24 hours!).

That second step needs to happen *later*, without the user waiting. That's exactly what Celery solves.

### The three pieces

```
[ Your Django code ]
    │  "run this task"
    ▼
[ Broker (Redis) ]      ← a queue that stores pending tasks
    │  "here's a task"
    ▼
[ Celery Worker ]       ← a separate process that picks up and runs tasks
```

- **Broker** = Redis (the middleman / message queue).
- **Worker** = a Python process running `celery worker`. It reads tasks from the broker and executes them.
- **Task** = a Python function decorated with `@shared_task`.

---

## 8. What is Celery Beat?

**Celery Beat** is Celery's built-in **scheduler**. It's like a cron job manager that runs inside Python.

Without Beat, Celery only runs tasks when your application explicitly calls them (e.g. after a user action). Beat adds the ability to say *"run this task every day at 2 AM"* — without any cron tab, without any external tool.

### How it works

```
Celery Beat process
    │
    │  reads schedule from DB (django-celery-beat)
    │  "cleanup_deleted_task is due at 02:00 UTC"
    │
    ▼
Places the task onto the Redis queue
    │
    ▼
Celery Worker picks it up and runs it
```

**Beat is not the worker** — it only *schedules* (puts tasks on the queue). The worker is a separate process that actually *runs* them. This is why you need both running.

### django-celery-beat

The standard Celery Beat stores its schedule in a local file (`celerybeat-schedule`), which means you can't edit it without restarting everything.

`django-celery-beat` is a package that stores the schedule in **Django's database** instead. This gives you:

- An admin panel at `/admin/` where you can **add, edit, or disable scheduled tasks without touching code**.
- The schedule persists across restarts.
- Works great in multi-server deployments.

---

## 9. How Celery Beat is Configured Here

### Step 1 — `taskapi_project/celery.py`

This file creates the Celery application and tells it to read settings from Django:

```python
app = Celery("taskapi_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()   # finds tasks.py in every INSTALLED_APP
```

### Step 2 — `taskapi_project/__init__.py`

```python
from .celery import app as celery_app
__all__ = ("celery_app",)
```

This line ensures the Celery app is loaded as soon as Django starts. Without it, `@shared_task` decorators in your app won't register correctly.

### Step 3 — `settings.py` — Celery settings

```python
CELERY_BROKER_URL = "redis://localhost:6379/0"   # where tasks queue up
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_BEAT_SCHEDULE = {
    "cleanup-soft-deleted-daily": {
        "task": "tasks.tasks.cleanup_deleted_task",
        "schedule": crontab(hour=2, minute=0),   # 02:00 UTC every day
    },
}
```

### Step 4 — `tasks/tasks.py` — the actual task

```python
@shared_task(name="tasks.tasks.cleanup_deleted_task", bind=True, max_retries=3)
def cleanup_deleted_task(self):
    call_command("cleanup_deleted")
```

The task simply calls the management command. This way the cleanup logic can also be triggered manually via CLI.

### Step 5 — `django_celery_beat` in `INSTALLED_APPS`

Adding `django_celery_beat` to `INSTALLED_APPS` and running `migrate` creates the tables that store the schedule in the database.

---

## 10. Running Celery & Celery Beat

### Starting everything (development)

**You need three terminal windows running simultaneously.**

```
Terminal 1                    Terminal 2                    Terminal 3
────────────────────────      ────────────────────────      ────────────────────────────────
python manage.py runserver    celery -A taskapi_project     celery -A taskapi_project beat
                              worker --loglevel=info        --loglevel=info \
                                                            --scheduler django_celery_beat\
                                                            .schedulers:DatabaseScheduler
```

### Verifying the worker is running

After starting the worker (Terminal 2), you should see output like:

```
[tasks]
  . tasks.tasks.cleanup_deleted_task

[2024-01-15 10:00:00,000: INFO/MainProcess] Connected to redis://localhost:6379/0
[2024-01-15 10:00:00,001: INFO/MainProcess] celery@yourmachine ready.
```

### Verifying Beat is running

After starting Beat (Terminal 3), you should see:

```
beat: Starting...
beat: Scheduler: Sending due task cleanup-soft-deleted-daily (tasks.tasks.cleanup_deleted_task)
```
(It won't fire until 02:00 UTC, but you should see "Starting..." without errors.)

### Testing the task manually (without waiting for 02:00)

Open a Django shell and fire the task immediately:

```bash
python manage.py shell
```
```python
from tasks.tasks import cleanup_deleted_task
cleanup_deleted_task.delay()   # .delay() sends it to the Celery worker
```

Or trigger it synchronously (no worker needed, runs in-process):
```python
cleanup_deleted_task.apply()
```

### Changing the schedule at runtime (no code change needed)

1. Go to `http://localhost:8000/admin/`
2. Navigate to **Periodic Tasks** (under Django Celery Beat).
3. Find `cleanup-soft-deleted-daily` and edit the crontab — change the hour, minute, etc.
4. Save. Beat picks up the change automatically on its next tick (≤ 5 seconds).

### Running in production (Linux with systemd)

In production you'd create systemd service files instead of running commands manually. Example unit file for the worker:

```ini
# /etc/systemd/system/celery-worker.service
[Unit]
Description=Celery Worker
After=network.target redis.service

[Service]
User=www-data
WorkingDirectory=/var/www/taskapi_project
ExecStart=/var/www/taskapi_project/venv/bin/celery -A taskapi_project worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

Create a similar file for Beat (`celery-beat.service`) replacing the `ExecStart` with the Beat command.

---

## 11. The Soft-Delete Lifecycle

```
User clicks "Delete"
        │
        ▼
  DELETE /api/projects/5/
        │
        ▼
  obj.is_deleted = True
  obj.deleted_at = now()          ← row still in DB, just hidden
        │
        ├── Within 24 hours ──────────────────────────────────────────┐
        │                                                              │
        │   GET /api/projects/trash/    → item appears here           │
        │   POST /api/projects/5/restore/ → item comes back           │
        │                                                              │
        └── After 24 hours ────────────────────────────────────────────┘
                │
                ▼
        Celery Beat fires at 02:00 UTC
                │
                ▼
        cleanup_deleted_task() runs
                │
                ▼
        obj.delete(hard=True) → super().delete() → row gone from DB
```

The `SoftDeleteModel.objects` manager filters out deleted rows automatically, so your normal `Project.objects.all()` calls never see them. The `all_objects` manager is the escape hatch for trash/restore views.

---

## 12. Management Command: cleanup_deleted

The command can be run manually at any time:

```bash
# See what would be deleted without actually deleting
python manage.py cleanup_deleted --dry-run

# Actually delete expired items
python manage.py cleanup_deleted
```

Output example:
```
Hard-deleted 3 expired task(s).
Hard-deleted 1 expired project(s).
Cleanup complete. Removed 3 task(s) and 1 project(s).
```

---

## 13. Project Structure

```
taskapi_project/
│
├── taskapi_project/              # Django project package
│   ├── __init__.py               # imports Celery app (required!)
│   ├── celery.py                 # Celery app configuration
│   ├── settings.py               # all settings incl. CELERY_BEAT_SCHEDULE
│   ├── urls.py                   # root URL conf + router registration
│   └── wsgi.py
│
├── tasks/                        # the only Django app
│   ├── models.py                 # SoftDeleteModel, Project, Task
│   ├── serializers.py            # ProjectSerializer (nested), TaskSerializer
│   ├── views.py                  # ProjectViewSet, TaskViewSet
│   ├── tasks.py                  # Celery task: cleanup_deleted_task
│   ├── admin.py                  # admin config with soft-delete awareness
│   ├── apps.py
│   └── management/
│       └── commands/
│           └── cleanup_deleted.py   # python manage.py cleanup_deleted
│
├── manage.py
├── requirements.txt
├── .env.example                  # copy to .env and fill in values
└── README.md
```

---

## 14. Common Issues & FAQ

### `redis.exceptions.ConnectionError`
Redis is not running. Start it:
```bash
brew services start redis       # macOS
sudo systemctl start redis      # Linux
```

### `ModuleNotFoundError: No module named 'celery'`
Your virtual environment isn't activated or dependencies aren't installed:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Beat starts but tasks never run
Make sure the **worker** is also running (Terminal 2). Beat only *schedules* — the worker *executes*. Both must be running.

### `django.db.utils.OperationalError: no such table: django_celery_beat_periodictask`
You haven't run migrations yet:
```bash
python manage.py migrate
```

### I want to test the cleanup without waiting until 02:00
Either run the management command directly:
```bash
python manage.py cleanup_deleted
```
Or fire the Celery task from the shell:
```python
from tasks.tasks import cleanup_deleted_task
cleanup_deleted_task.apply()   # runs synchronously, no worker needed
```

### How do I change the cleanup schedule?
**Option A — Code:** Edit `CELERY_BEAT_SCHEDULE` in `settings.py` and restart Beat.

**Option B — Admin (no restart):** Go to `/admin/` → Periodic Tasks → edit the entry → Save.

### What's the difference between `crontab` and an integer schedule?
```python
# Run at exactly 02:00 UTC every day
"schedule": crontab(hour=2, minute=0)

# Run every 86400 seconds (24 hours from last run, not wall-clock midnight)
"schedule": 86400
```
Use `crontab` when timing matters (e.g. "run at night"). Use an integer for "run every N seconds".
