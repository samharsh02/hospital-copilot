# Hospital Copilot — Backend

AI-powered operational copilot for hospital management. Manages patients, beds, admissions, clinical workflows, escalation alerts, and real-time notifications — with Claude-powered decision support.

## Design philosophy

The system has two layers:

**Operational layer (always on):** Patient registration, bed/ward management, admissions, discharge tracking, and AI summaries from operational data. Works for reception, billing, ward clerks, matrons, and senior management with zero dependency on clinical staff entering data.

**Clinical layer (per-hospital opt-in):** Clinical event logging, vitals-based escalation rules, workflow checklists for nurses and doctors. Activated via `Hospital.clinical_module_enabled = True` in the admin. When on, it enriches the operational layer — AI summaries gain clinical context, escalations fire on vitals. When off, the operational layer runs clean.

This design ensures every hospital gets immediate value from day one, and clinical adoption becomes a choice rather than a prerequisite.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.1 + Django REST Framework 3.15 |
| ASGI server | Gunicorn + Uvicorn workers |
| Auth | JWT via `djangorestframework-simplejwt` (rotation + blacklist) |
| WebSocket | Django Channels 4 over Redis |
| Task queue | Celery 5 + Redis |
| AI | Anthropic API (Claude) |
| Database | PostgreSQL 15 |
| Cache / broker | Redis 7 |
| Reverse proxy | Nginx |
| Container runtime | Docker + Docker Compose v2 |

## Repository Layout

```
hospital-copilot/
├── apps/
│   ├── core/           # BaseMixin, SoftDeleteMixin, Hospital model (incl. clinical_module_enabled), exceptions
│   ├── users/          # User model, JWT auth endpoints
│   ├── patients/       # Patient, Ward, Bed, Admission — PII-encrypted
│   ├── workflows/      # WorkflowTemplate, WorkflowInstance, WorkflowStep (clinical module)
│   ├── events/         # Clinical event log (clinical module)
│   ├── escalations/    # Escalation rules + alerts (clinical module)
│   ├── intelligence/   # Claude-powered summaries — two-tier context
│   ├── integrations/   # External system connectors (planned)
│   └── communications/ # WebSocket notifications (planned)
├── config/
│   ├── settings/       # base / development / test / production
│   ├── celery.py
│   ├── urls.py
│   └── asgi.py
├── nginx/
│   └── nginx.conf
├── docs/
│   ├── TODO.md
│   ├── HLD.md
│   └── LLD.md
├── Dockerfile
├── docker-compose.yml
└── entrypoint.sh
```

## API Endpoints

All endpoints are prefixed with `/api/v1/`.

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register/` | Register a new user |
| POST | `/auth/login/` | Obtain JWT access + refresh tokens |
| POST | `/auth/logout/` | Blacklist refresh token |
| GET / PATCH | `/auth/me/` | Current user profile |

### Patients & Beds (operational layer)
| Method | Path | Description |
|--------|------|-------------|
| GET / POST | `/patients/` | List (hospital-scoped) / create (ADMIN+) |
| GET / PATCH / DELETE | `/patients/<id>/` | Detail / update (NURSE+) / soft-delete (ADMIN+) |
| POST | `/patients/<id>/admit/` | Admit patient to a bed |
| POST | `/patients/<id>/discharge/` | Discharge patient, free bed |
| GET | `/patients/<id>/admissions/` | Admission history |
| GET | `/patients/<id>/events/` | Clinical event timeline (clinical module) |
| GET | `/wards/` | List wards |
| GET | `/wards/<id>/beds/` | List beds in a ward |

### Workflows (clinical module)
| Method | Path | Description |
|--------|------|-------------|
| GET / POST | `/workflow-templates/` | List / create template (ADMIN+) |
| GET / PATCH / DELETE | `/workflow-templates/<id>/` | Detail / update / soft-delete (ADMIN+) |
| GET / POST | `/workflow-instances/` | List / start instance (NURSE+) |
| GET | `/workflow-instances/<id>/` | Detail with steps inline |
| POST | `/workflow-instances/<id>/steps/<n>/complete/` | Complete step (NURSE+) |
| POST | `/workflow-instances/<id>/cancel/` | Cancel instance (NURSE+) |

### Events (clinical module)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/events/` | Record clinical event (NURSE+) |
| GET | `/events/` | List events (hospital-scoped, filterable) |

### Escalations (clinical module)
| Method | Path | Description |
|--------|------|-------------|
| GET / POST | `/escalation-rules/` | List / create rule (ADMIN+) |
| GET / PATCH / DELETE | `/escalation-rules/<id>/` | Detail / update / soft-delete (ADMIN+) |
| GET | `/escalation-alerts/` | List alerts (hospital-scoped, filterable) |
| POST | `/escalation-alerts/<id>/acknowledge/` | Acknowledge alert (NURSE+) |
| POST | `/escalation-alerts/<id>/resolve/` | Resolve alert (DOCTOR+) |

### Intelligence (operational always, clinical context when module is on)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/intelligence/query/` | Submit AI query → `202 Accepted` with `request_id` (ADMIN+) |
| GET | `/intelligence/<id>/` | Poll status and result |
| GET | `/patients/<id>/intelligence/` | Past AI queries for this patient |

### Role hierarchy

`WARD_STAFF` < `NURSE` < `DOCTOR` < `ADMIN` < `SUPERADMIN`

All data is scoped to the user's hospital. SUPERADMIN bypasses hospital scoping.

## Local Development

### Prerequisites
- Python 3.11+
- Docker + Docker Compose v2

### Setup

```bash
git clone https://github.com/samharsh02/hospital-copilot.git
cd hospital-copilot

python -m venv .venv
source .venv/bin/activate
pip install -r requirements/base.txt -r requirements/development.txt

cp .env.docker.example .env
# Fill in SECRET_KEY, DB_PASSWORD, ANTHROPIC_API_KEY, FIELD_ENCRYPTION_KEY

docker compose up -d db redis
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The API will be available at `http://localhost:8000`.

### Running tests

```bash
.venv/bin/python -m pytest apps/ -v
```

274 tests across core, users, patients, workflows, events, and escalations — all using in-memory SQLite with `--no-migrations`.

## Docker Deployment

The full stack runs via Docker Compose (db, redis, api, celery, frontend, nginx).

```bash
cp .env.docker.example .env   # fill in values

docker compose up -d --build
docker compose exec api python manage.py createsuperuser
```

**Service URLs** (internal Docker network):

| Service | Address |
|---------|---------|
| API | `api:8000` |
| Database | `db:5432` |
| Redis | `redis:6379` |
| Frontend | `frontend:80` |

Nginx listens on port 80 and routes:
- `/api/*`, `/admin/*`, `/ws/*` → api container
- `/*` → frontend container

### Deploy a new version

```bash
git pull
docker compose build api celery
docker compose up -d --no-deps api celery
docker compose exec api python manage.py migrate --noinput
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `DB_PASSWORD` | Yes | PostgreSQL password |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `FIELD_ENCRYPTION_KEY` | Yes | Fernet key for PII field encryption |
| `DEBUG` | No | `False` in production |
| `ALLOWED_HOSTS` | No | Comma-separated hostnames |
| `LOG_LEVEL` | No | `INFO` |

Generate a Fernet key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

## Enabling the clinical module

The clinical module is off by default for every hospital. To enable it:

```bash
# Via Django admin UI: Hospital → list_editable → tick clinical_module_enabled
# Or via Django shell:
docker compose exec api python manage.py shell -c \
  "from apps.core.models import Hospital; Hospital.objects.filter(name='Your Hospital').update(clinical_module_enabled=True)"
```

Once enabled, nurses and doctors can record clinical events, workflow steps are tracked, escalation rules fire on vitals, and AI summaries include clinical context.

## Related

- **Frontend**: [hospital-copilot-ui](https://github.com/samharsh02/hospital-copilot-ui)
- **Design docs**: [`docs/HLD.md`](docs/HLD.md), [`docs/LLD.md`](docs/LLD.md)
- **Implementation plan**: [`docs/TODO.md`](docs/TODO.md)
