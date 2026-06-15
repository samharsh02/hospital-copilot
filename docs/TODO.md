# Hospital Copilot — Plan & TODO

This file is the single source of truth for what's done, what's next, and what's blocked.
**Update it at the end of every implementation session.**

---

## Done

### Infrastructure
- [x] Server provisioned: `172.16.232.103` (CentOS 7, 2 vCPU, 3.6 GB RAM + 2 GB swap, 20 GB disk)
- [x] Python 3.11.9 compiled from source (with OpenSSL 1.1.1k)
- [x] PostgreSQL 15 installed and running (`hospital_copilot` DB, `hospital` user)
- [x] Redis 7.2 installed and running (localhost only)
- [x] App deployed to `/opt/hospital-copilot/` from GitHub
- [x] `hospital-copilot` systemd service (gunicorn + 2 uvicorn workers, port 8000)
- [x] `hospital-copilot-celery` systemd service (celery -A config, 2 workers)
- [x] All migrations applied; API responding at `http://172.16.232.103:8000/health/`
- [ ] **Nginx** reverse proxy + TLS (port 80→443, proxy to :8000) — not yet installed

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

### 1. `apps/patients` — Core domain ← **start here**

The patient record is the central entity everything else references.

- [ ] `Patient` model — MRN, first/last name (encrypted PII), date of birth, gender, blood group, contact phone (encrypted), emergency contact, hospital FK, admitted_at, discharged_at, is_active
- [ ] `Ward` model — name, hospital FK, capacity
- [ ] `Bed` model — number, ward FK, is_occupied
- [ ] `Admission` model — patient FK, bed FK, admitted_by (User FK), admitted_at, discharged_at, notes
- [ ] Patient search endpoint (`GET /api/v1/patients/?search=&ward=&status=`)
- [ ] Patient CRUD (`GET/POST /api/v1/patients/`, `GET/PATCH /api/v1/patients/<id>/`)
- [ ] Admission endpoints (`POST /api/v1/patients/<id>/admit/`, `POST /api/v1/patients/<id>/discharge/`)
- [ ] Ward + Bed list endpoints
- [ ] Role-based permission: WARD_STAFF and above can read; NURSE/DOCTOR can admit; ADMIN can create/delete
- [ ] Migrations
- [ ] Tests — service + view layer

### 2. `apps/workflows` — Clinical workflows

Structured checklists that run during a patient's stay (admission checklist, vitals round, discharge process, etc.).

- [ ] `WorkflowTemplate` model — name, hospital FK, steps (JSONField), trigger (on_admit / on_discharge / manual)
- [ ] `WorkflowInstance` model — template FK, patient admission FK, status (pending/in_progress/completed), assigned_to (User FK), started_at, completed_at
- [ ] `WorkflowStep` model — instance FK, step_index, title, is_completed, completed_by, completed_at, notes
- [ ] Endpoints: create/list templates, start instance from template, complete a step, view instance status
- [ ] Tests

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

- [ ] **Nginx** — install, configure as reverse proxy on :80/:443, proxy to :8000, serve WebSocket upgrade
- [ ] **TLS certificate** — Let's Encrypt (certbot) or provide a cert; needed before any external traffic
- [ ] **Firewall** — `firewalld` rules: open 80, 443; keep 8000 internal only
- [ ] **Change admin password** — default is `changeme123!`, must be changed before external exposure
- [ ] **Set `ANTHROPIC_API_KEY`** in `/opt/hospital-copilot/.env` on the server
- [ ] **`.env.example`** — review and keep in sync with actual required vars

---

## Known Issues / Tech Debt

- `ALLOWED_HOSTS` on the server includes `127.0.0.1` as a workaround for health checks; once Nginx is in front, restrict to `172.16.232.103` and `localhost` only
- Git committer name/email is auto-configured from hostname — run `git config --global user.name` / `user.email` locally to fix
- Python 3.11 source still in `/tmp/Python-3.11.9` (~200 MB); safe to delete once the build is confirmed stable
- Test suite uses `--no-migrations` (syncdb); migration smoke tests against a real DB are not covered
