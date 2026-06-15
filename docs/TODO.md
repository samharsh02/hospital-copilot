# Hospital Copilot — Plan & TODO

This file is the single source of truth for what's done, what's next, and what's blocked.
**Update it at the end of every implementation session.**

---

## Done

### Infrastructure
- [x] Server provisioned: `172.16.232.103` (CentOS 7, 2 vCPU, 3.6 GB RAM + 2 GB swap, 20 GB disk)
- [x] Docker CE 26.1.4 + Docker Compose v2.27.1 installed on server
- [x] Backend `Dockerfile` (python:3.11-slim; entrypoint runs migrate then starts gunicorn)
- [x] `docker-compose.yml` — services: db (postgres:15), redis:7, api, celery, frontend, nginx
- [x] `nginx/nginx.conf` — routes `/api/` + `/ws/` to api:8000, `/` to frontend container
- [x] Frontend scaffolded at `frontend/` — React 18 + Vite 6 + TypeScript; auth layer wired
- [x] Frontend `Dockerfile` — multi-stage: Node 20 build → nginx:alpine serve
- [x] Frontend repo at https://github.com/samharsh02/hospital-copilot-ui.git (main branch)
- [x] Python 3.11.9 compiled from source (with OpenSSL 1.1.1k) — superseded by Docker
- [x] PostgreSQL 15 installed and running on host — superseded by Docker volume
- [x] Redis 7.2 installed and running on host — superseded by Docker container
- [x] Old systemd services (`hospital-copilot`, `hospital-copilot-celery`) stopped and disabled

### `apps/core` — Base layer
- [x] `BaseMixin` — `created_at`, `updated_at`, `created_by`, `updated_by`
- [x] `SoftDeleteMixin` — `is_deleted`, `deleted_at`, `deleted_by`, `soft_delete()`, `ActiveManager`
- [x] `Hospital` model — name, type, city, state, bed_count, is_active
- [x] Exception hierarchy — `AppError`, `NotFoundError`, `PermissionDeniedError`, `ValidationError`, `ConflictError`, `custom_exception_handler`
- [x] `StandardPagination`, `elapsed_minutes()`, `format_duration()`
- [x] Migrations (`0001_initial`, `0002_initial`)
- [x] Tests — 55 passing

### `apps/users` — Auth
- [x] `User(AbstractUser)` — adds `role`, `hospital` FK, `phone`
- [x] `UserRole` choices — SUPERADMIN, ADMIN, DOCTOR, NURSE, WARD_STAFF
- [x] `register_user()` service — deduplicates username/email
- [x] JWT auth endpoints: `POST /api/v1/auth/register/`, `POST /api/v1/auth/login/`, `POST /api/v1/auth/logout/` (blacklist), `GET/PATCH /api/v1/auth/me/`
- [x] Token blacklist (`rest_framework_simplejwt.token_blacklist`)
- [x] Migration (`0001_initial`)
- [x] Tests — 30 passing (service + view layer)

---

## Up Next

Work through the apps in dependency order. Each app should follow the same pattern:
`constants → models → migrations → services → serializers → views → urls → tests`.

### 1. `apps/patients` — Core domain ✅ DONE

- [x] `Patient` model — MRN, encrypted first/last name, dob, gender, blood group, encrypted contact phone, emergency contact, hospital FK, soft-delete + audit
- [x] `Ward` model — name, hospital FK, capacity, soft-delete + audit
- [x] `Bed` model — number, ward FK, is_occupied, audit; unique_together (ward, number)
- [x] `Admission` model — patient + bed FK, admitted_by, admitted/discharged timestamps, notes
- [x] `GET /api/v1/patients/?search=&ward=&status=` — search by MRN, filter by ward, filter active/discharged
- [x] `GET/POST /api/v1/patients/` — list (all auth) + create (ADMIN+)
- [x] `GET/PATCH/DELETE /api/v1/patients/<id>/` — detail, patch (NURSE+), soft-delete (ADMIN+)
- [x] `POST /api/v1/patients/<id>/admit/` — admit to bed (or no bed); guards: already admitted 400, occupied bed 409
- [x] `POST /api/v1/patients/<id>/discharge/` — discharge; frees bed; guard: not admitted 400
- [x] `GET /api/v1/patients/<id>/admissions/` — admission history
- [x] `GET /api/v1/wards/`, `GET /api/v1/wards/<id>/beds/`
- [x] `permissions.py` — `IsNurseOrAbove`, `IsAdminOrAbove` role-rank permission classes
- [x] `FIELD_ENCRYPTION_KEY` wired into settings; `encrypted_model_fields` in INSTALLED_APPS
- [x] Migration `0001_initial`
- [x] Tests — 47 passing (service + view layer)

### 2. `apps/workflows` — Clinical workflows ✅ DONE

Structured checklists that run during a patient's stay (admission checklist, vitals round, discharge process, etc.).

- [x] `WorkflowTemplate` model — name, hospital FK, steps (JSONField array of {index, title, description}), trigger (ON_ADMIT / ON_DISCHARGE / MANUAL), is_active, soft-delete + audit
- [x] `WorkflowInstance` model — template FK, admission FK, status (PENDING→IN_PROGRESS→COMPLETED/CANCELLED), assigned_to (User FK nullable), started_at, completed_at
- [x] `WorkflowStep` model — instance FK, step_index, title, is_completed, completed_by, completed_at, notes
- [x] `GET/POST /api/v1/workflow-templates/` — list (all auth, hospital-scoped) + create (ADMIN+)
- [x] `GET/PATCH/DELETE /api/v1/workflow-templates/<id>/` — detail, patch (ADMIN+), soft-delete (ADMIN+)
- [x] `GET/POST /api/v1/workflow-instances/` — list (all auth, hospital-scoped) + start (NURSE+)
- [x] `GET /api/v1/workflow-instances/<id>/` — detail with steps inline
- [x] `POST /api/v1/workflow-instances/<id>/steps/<step_index>/complete/` — complete step (NURSE+); auto-advances instance status
- [x] `POST /api/v1/workflow-instances/<id>/cancel/` — cancel (NURSE+)
- [x] Migration `0001_initial`
- [x] Tests — 54 passing (27 service + 27 view)

### 3. `apps/events` — Clinical events log

Append-only log of significant events during a patient stay (vitals recorded, medication given, nurse note, doctor visit, etc.).

- [ ] `ClinicalEvent` model — patient FK, admission FK, event_type (choices), recorded_by (User FK), recorded_at, payload (JSONField), notes
- [ ] `EventType` constants — VITALS, MEDICATION, NURSE_NOTE, DOCTOR_NOTE, LAB_RESULT, ALERT, OTHER
- [ ] Endpoints: `POST /api/v1/events/` (record), `GET /api/v1/patients/<id>/events/` (timeline)
- [ ] Tests

### 4. `apps/escalations` — Escalation rules and alerts

Rules that fire when a patient condition or workflow threshold is breached.

- [ ] `EscalationRule` model — hospital FK, name, condition (JSONField), priority (LOW/MEDIUM/HIGH/CRITICAL), notify_roles
- [ ] `EscalationAlert` model — rule FK, patient FK, admission FK, triggered_at, acknowledged_at, acknowledged_by, resolved_at, status
- [ ] Rule evaluation service (called after each new ClinicalEvent)
- [ ] Endpoints: CRUD rules, list/acknowledge/resolve alerts
- [ ] Tests

### 5. `apps/intelligence` — Claude-powered suggestions

Uses the Anthropic API to generate clinical decision support from the patient's event history.

- [ ] `IntelligenceRequest` model — patient FK, admission FK, requested_by, prompt_type (SUMMARY / RISK_FLAG / NEXT_ACTION / DRUG_CHECK), created_at, response_text, tokens_used, latency_ms
- [ ] `generate_summary()` service — builds context from recent events, calls `anthropic.messages.create`, stores result
- [ ] Async task (Celery) for non-blocking AI calls
- [ ] Endpoints: `POST /api/v1/intelligence/query/`, `GET /api/v1/patients/<id>/intelligence/`
- [ ] Rate-limit per hospital (don't hammer Anthropic)
- [ ] Tests (mock Anthropic SDK in tests)

### 6. `apps/communications` — WebSocket notifications

Real-time push to connected clients (nurse station, doctor tablet) using Django Channels.

- [ ] Django Channels routing (`config/asgi.py` already has ASGI setup)
- [ ] `NotificationConsumer` — WebSocket consumer, auth via JWT query param
- [ ] Server-side push: when an EscalationAlert fires → push to all users in the hospital's group
- [ ] `Notification` model — user FK, message, type, read_at, created_at (for persistence / unread count)
- [ ] REST endpoints: `GET /api/v1/notifications/` (list), `POST /api/v1/notifications/<id>/read/`
- [ ] Tests (use `channels.testing.WebsocketCommunicator`)

### 7. `apps/integrations` — External system connectors

Connect to hospital HIS/EMR systems, lab systems, etc.

- [ ] Design TBD — depends on which external systems are in scope
- [ ] Likely: HL7 FHIR ingest endpoint, outbound webhook delivery
- [ ] Placeholder until requirements are clearer

---

## Infrastructure Remaining

- [ ] **TLS certificate** — Let's Encrypt (certbot) or provide a cert; needed before external traffic. Add HTTPS listener to nginx/nginx.conf and update ALLOWED_HOSTS.
- [ ] **Firewall** — `firewalld` rules: open 80 (and 443 after TLS); keep 8000 internal only (nginx handles external traffic now)
- [ ] **Change admin password** — default is `changeme123!`, must be changed before external exposure
- [ ] **Set `ANTHROPIC_API_KEY`** in `/opt/hospital-copilot/.env` on the server
- [ ] **Migrate existing PostgreSQL data** — current data is in the host PostgreSQL; after `docker compose up`, run migrations into the new Docker Postgres volume (`docker compose exec api python manage.py migrate`)

---

## Known Issues / Tech Debt

- Git committer name/email is auto-configured from hostname — run `git config --global user.name` / `user.email` locally and on server to fix
- Python 3.11 source still in `/tmp/Python-3.11.9` on server (~200 MB); safe to delete (build now uses Docker)
- Test suite uses `--no-migrations` (syncdb); migration smoke tests against a real DB are not covered
- `DJANGO_SETTINGS_MODULE` is hardcoded to `production` in the Dockerfile `ENV`; override via compose env if dev image is needed
- Frontend has no router yet (`react-router-dom` not installed); only Login and Dashboard pages exist as a scaffold
