```markdown
# ⚡ Dev Standup Bot

> An asynchronous, multi-tenant developer standup engine built with Django REST Framework, Celery, Redis, and PostgreSQL. Automates daily standup aggregation, timezone-aware deadline scheduling, and webhook dispatches to Discord and Slack with exponential backoff fault tolerance.

---

## 🏗️ System Architecture

The application decouples HTTP request handling, periodic deadline evaluation, and external webhook I/O across three isolated layers using a fan-out Celery architecture.

```text
                                  +-----------------------+
                                  |   Celery Beat (1m)    |
                                  |  Scheduler Heartbeat  |
                                  +-----------+-----------+
                                              |
                                              | Evaluates due teams (Timezone-aware)
                                              v
+------------------+             +-----------------------+
|  Team Members    |  POST /api  |   Redis Broker Queue  |
|  (HTTP Client)   +------------>|  [celery: default]    |
+------------------+             +-----------+-----------+
                                              |
                       +----------------------+----------------------+
                       | Fans out tasks                              |
                       v                                             v
        +----------------------------+                +----------------------------+
        |   Celery Worker Cluster    |                |   PostgreSQL Database      |
        | - compile_team_digest_task |<-------------->| - Row Locking (FOR UPDATE) |
        | - dispatch_webhook_task    |   Transacts    | - Idempotent Submissions   |
        +--------------+-------------+                +----------------------------+
                       |
                       | Non-blocking external HTTP I/O
                       | (Exponential Backoff + Jitter)
                       v
         +--------------------------+
         |  Chat Provider Webhooks  |
         |  - Discord (Rich Embeds) |
         |  - Slack (Block Kit)     |
         +--------------------------+

```

### Core Architecture Patterns

1. **Timezone-Aware Fan-Out Scheduling:** Instead of batch-processing all teams in a single blocking loop, Celery Beat runs a periodic heartbeat (`check_and_compile_due_teams_task`) every 60 seconds. Teams due for compilation trigger isolated `compile_team_digest_task` jobs onto the queue, preventing one slow team or webhook failure from cascading to others.
2. **Database Atomicity & Concurrency Control:** Standup submissions use `select_for_update()` inside `transaction.atomic()` blocks. Concurrent submissions for the same team member on the same calendar day update the existing record idempotently without duplicate rows.
3. **Non-Blocking External I/O:** Third-party webhook deliveries run completely out-of-band via `dispatch_digest_webhook_task` and `dispatch_late_entry_webhook_task`. Webhook endpoints that time out or rate-limit retry with randomized exponential backoff up to 5 times.
4. **Dynamic Missing Submitter Snapshots:** When compilation executes, any active team member without an entry is recorded in the digest's `missing_members_snapshot`. If that member submits late via the API, the system updates the snapshot and asynchronously fires a dedicated "Late Standup" alert to the team channel.

---

## 🛠️ Tech Stack

* **Core Framework:** Python 3.12+, Django 5.x, Django REST Framework (DRF)
* **Task Queue & Caching:** Celery, Redis (RESP2 / RESP3 compatible)
* **Database:** PostgreSQL (with SQLite support for local rapid dev)
* **Package Management:** `uv` (Astral)
* **Integrations:** Discord Webhooks (Rich Embeds), Slack Incoming Webhooks (Block Kit)
* **Configuration:** `python-dotenv`

---

## 📁 Project Structure

```text
devstandup/
├── config/                     # Project configuration namespace
│   ├── __init__.py             # Exposes Celery app instance
│   ├── celery.py               # Celery app broker/backend configuration
│   ├── settings.py             # Global settings & Beat periodic schedules
│   ├── urls.py                 # Root URL router
│   └── wsgi.py
│
├── apps/
│   ├── teams/                  # Multi-tenant management
│   │   ├── models.py           # Team (timezones, schedules), TeamMember
│   │   └── admin.py
│   │
│   └── standups/               # Standup bot domain logic
│       ├── models.py           # StandupEntry, StandupDigest
│       ├── tasks.py            # Celery worker tasks (fan-out, webhook retries)
│       ├── views.py            # DRF ViewSets & submission API endpoints
│       ├── serializers.py      # Entry & digest validation
│       ├── services/
│       │   ├── compilation.py  # Standup aggregation & missing snapshot logic
│       │   └── webhook_dispatcher.py # Slack Block Kit & Discord Embed builder
│       └── tests/              # 20+ automated unit & task integration tests
│
├── scripts/                    # End-to-end verification utilities
│   ├── smoke_discord.py        # Live Discord digest & late entry test
│   └── smoke_api.py            # Automated REST API client test
│
├── pyproject.toml              # Dependencies locked via uv
├── uv.lock
├── .env.example
└── manage.py

```

---

## 📊 Database Schema Highlights

```text
+-------------------+       1:N       +----------------------+
|    teams_team     |----------------<|   teams_teammember   |
+-------------------+                 +----------------------+
| id (PK)           |                 | id (PK)              |
| name              |                 | team_id (FK)         |
| timezone (IANA)   |                 | user_id (FK)         |
| standup_time      |                 | display_name         |
| webhook_url       |                 | is_active            |
| webhook_format    |                 +----------+-----------+
+---------+---------+                            |
          | 1:N                                  | 1:N
          v                                      v
+-------------------+       1:N       +----------------------+
|  standups_digest  |----------------<|    standups_entry    |
+-------------------+                 +----------------------+
| id (PK)           |                 | id (PK)              |
| team_id (FK)      |                 | team_id (FK)         |
| digest_date       |                 | member_id (FK)       |
| is_compiled       |                 | digest_id (FK, Null) |
| missing_snapshot  |                 | yesterday / today    |
+-------------------+                 | blockers / is_late   |
                                      +----------------------+

```

* **Constraints:** Unique index on `(member_id, standup_date)` guarantees idempotency per member per workday.
* **Snapshotting:** `missing_members_snapshot` stores serialized JSON of absent members at compile-time to maintain historical audit accuracy even if team rosters change later.

---

## 🚀 Getting Started

### 1. Prerequisites

* Python 3.12+
* [`uv`](https://github.com/astral-sh/uv) package manager
* Redis (local service or Docker)

### 2. Installation

Clone the repository and install dependencies with `uv`:

```bash
git clone [https://github.com/](https://github.com/)taizeem/devstandup.git
cd devstandup
uv sync

```

### 3. Environment Configuration

Copy the sample environment file and configure your credentials:

```bash
cp .env.example .env

```

Edit `.env`:

```ini
DJANGO_SECRET_KEY=dev-insecure-secret-key-change-in-prod
DJANGO_DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration (0 for SQLite, 1 for PostgreSQL)
USE_POSTGRES=0
DB_NAME=devstandup_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Celery Broker & Backend
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CELERY_ALWAYS_EAGER=False

# Live Webhook Testing (Optional)
DISCORD_WEBHOOK_URL=[https://discord.com/api/webhooks/your-webhook-id/your-webhook-token](https://discord.com/api/webhooks/your-webhook-id/your-webhook-token)

```

### 4. Database Migrations

```bash
uv run python manage.py migrate

```

---

## 🖥️ Running the Application

For a full local development setup, run the following processes in separate terminal sessions:

### Terminal 1: Redis Server

```bash
# If using Docker:
docker run --name standup-redis -p 6379:6379 -d redis:alpine

# Or using native Windows/Linux Redis service:
redis-server

```

### Terminal 2: Celery Worker

```bash
# Windows (solo pool required):
uv run celery -A config worker --loglevel=INFO -P solo

# Linux / macOS:
uv run celery -A config worker --loglevel=INFO

```

### Terminal 3: Celery Beat Scheduler

```bash
uv run celery -A config beat --loglevel=INFO

```

### Terminal 4: Django REST API

```bash
uv run python manage.py runserver

```

---

## 📡 REST API Reference

### 1. Submit Daily Standup

* **Endpoint:** `POST /api/v1/standups/submit/<team_id>/`
* **Auth:** Required (HTTP Basic or Session)
* **Behavior:** Idempotent update-or-create based on calling user and target team's local calendar day.

**Request Payload:**

```json
{
  "yesterday": "Implemented exponential backoff logic for Celery tasks.",
  "today": "Writing integration tests for Discord embeds.",
  "blockers": "None"
}

```

**Response (`201 Created` or `200 OK`):**

```json
{
  "id": 14,
  "team": 2,
  "team_name": "Core Backend Team",
  "member": 5,
  "member_name": "Dave (Infra)",
  "standup_date": "2026-10-07",
  "yesterday": "Implemented exponential backoff logic for Celery tasks.",
  "today": "Writing integration tests for Discord embeds.",
  "blockers": "None",
  "is_late": false,
  "submitted_at": "2026-10-07T09:42:15.112Z",
  "updated_at": "2026-10-07T09:42:15.112Z"
}

```

---

### 2. Standup Entry History

* **Endpoint:** `GET /api/v1/standups/history/`
* **Filters:** `?team_id=2&is_late=true&start_date=2026-10-01&end_date=2026-10-07`

---

### 3. Manually Trigger Digest Compilation

* **Endpoint:** `POST /api/v1/standups/compile/<team_id>/`
* **Response:** Returns `202 Accepted` with background `task_id`.

```json
{
  "message": "Compilation task enqueued",
  "task_id": "7c9e01b2-c0e8-4221-a489-cf775d7b56f2"
}

```

---

## 🧪 Automated Testing & Verification

### Run Automated Unit & Task Tests

The test suite utilizes Django's test runner configured with `CELERY_TASK_ALWAYS_EAGER=True` to validate models, serialization, row locking, and Celery retries deterministically without an active Redis broker:

```bash
uv run python manage.py test -v 2

```

### Run Live End-to-End Smoke Tests

Verify real-world webhook rendering directly against Discord or test endpoints:

```bash
# Tests complete database seed, compilation digest, and late submission embed
uv run python test_api_client.py

# Tests authenticated REST API submissions, validation errors, and updates
uv run python test_discord_flow.py

```

---

## 🛡️ Resilience & Fault Tolerance

| Scenario | System Mitigation |
| --- | --- |
| **Simultaneous Submissions** | Managed via `select_for_update()` inside `transaction.atomic()`, preventing write races on the same member entry. |
| **Webhook 5xx / Rate Limits** | `autoretry_for=(WebhookDispatchError,)` with exponential backoff (`retry_backoff=True`), jitter, and a 10-minute cap. |
| **Worker Restarts / Memory Leaks** | Workers are state-free; failed tasks are tracked with `CELERY_TASK_TRACK_STARTED` and bounded by `CELERY_TASK_TIME_LIMIT`. |
| **Timezone Boundary Edge Cases** | Evaluation runs against team-specific IANA timezones (e.g. `America/New_York`, `Asia/Kolkata`) rather than server host time. |

---

## 📄 License

This project is licensed under the MIT License.

```

```