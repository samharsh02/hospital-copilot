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
- [x] `Hospital` model — name, type, city, state, bed_count, is_active, **`clinical_module_enabled`** (default False)
- [x] `clinical_module_enabled` — gates clinical features (events, escalations, workflows) per hospital; operational layer always works regardless
- [x] Exception hierarchy — `AppError`, `NotFoundError`, `PermissionDeniedError`, `ValidationError`, `ConflictError`, `custom_exception_handler`
- [x] `StandardPagination`, `elapsed_minutes()`, `format_duration()`
- [x] `HospitalAdmin` with `list_editable` for `clinical_module_enabled` and `is_active`
- [x] Migrations (`0001_initial`, `0002_initial`, `0003_hospital_clinical_module_flag`)
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

### 3. `apps/events` — Clinical events log ✅ DONE

Append-only log of significant events during a patient stay (vitals recorded, medication given, nurse note, doctor visit, etc.).

- [x] `ClinicalEvent` model — patient FK, admission FK, event_type, recorded_by (nullable SET NULL), recorded_at (indexed), payload (JSONField), notes + BaseMixin
- [x] `EventType` constants — VITALS, MEDICATION, NURSE_NOTE, DOCTOR_NOTE, LAB_RESULT, ALERT, OTHER
- [x] `POST /api/v1/events/` — record event (NURSE+); guards: wrong patient-admission combo, discharged admission
- [x] `GET /api/v1/events/` — list (auth, hospital-scoped, filterable by patient/admission/event_type/date_from/date_to)
- [x] `GET /api/v1/patients/<id>/events/` — patient event timeline (filterable by event_type/date range)
- [x] Migration `0001_initial`
- [x] Tests — 28 passing (10 service + 18 view)

### 4. `apps/escalations` — Escalation rules and alerts ✅ DONE

Rules that fire when a patient condition or workflow threshold is breached.

- [x] `EscalationRule` model — hospital FK, name, condition (JSONField DSL), priority (LOW/MEDIUM/HIGH/CRITICAL), notify_roles (JSONField list), is_active, soft-delete + audit
- [x] `EscalationAlert` model — rule FK, patient FK, admission FK, triggered_at, acknowledged_at, acknowledged_by, resolved_at, status (OPEN/ACKNOWLEDGED/RESOLVED)
- [x] Condition DSL evaluator — `_resolve_field` (payload.*, event_type, notes), `_evaluate_condition` (eq/ne/lt/lte/gt/gte/in), `_validate_condition`
- [x] `evaluate_escalation_rules(admission_id)` — evaluates active rules against latest event, deduplicates OPEN alerts, pushes WS notification (best-effort)
- [x] `evaluate_escalation_rules_task` — Celery task with 3 retries, exponential backoff
- [x] Lazy import in `record_event` (events app) dispatches task in try/except — never blocks event recording
- [x] `GET/POST /api/v1/escalation-rules/` — list (ADMIN+, hospital-scoped, ?active=) + create (ADMIN+)
- [x] `GET/PATCH/DELETE /api/v1/escalation-rules/<id>/` — detail, patch (ADMIN+), soft-delete (ADMIN+)
- [x] `GET /api/v1/escalation-alerts/` — list (all auth, hospital-scoped, ?status=/?patient=/?admission=)
- [x] `POST /api/v1/escalation-alerts/<id>/acknowledge/` — (NURSE+); guards: non-OPEN → 400
- [x] `POST /api/v1/escalation-alerts/<id>/resolve/` — (DOCTOR+); guards: already resolved → 409
- [x] WS push `_push_alert_notification` — channels group_send to `hospital_<id>` (best-effort, try/except)
- [x] Migration `0001_initial`
- [x] Tests — 65 passing (37 service + 28 view, including end-to-end event→task→alert pipeline)

### 5. `apps/intelligence` — Claude-powered decision support ✅ DONE

Two-tier context: Tier 1 (operational data, always) + Tier 2 (clinical events + alerts, only when `clinical_module_enabled = True`). Every response carries a mandatory disclaimer. Claude is instructed to say "insufficient data" rather than speculate when context is sparse.

**Prompt types:**
- `PATIENT_SUMMARY` — always available; admission timeline, LOS, ward/bed, demographics; enriched with clinical events if Tier 2 is enabled
- `DISCHARGE_READINESS` — always available; flags if LOS is atypically long based on operational data
- `RISK_FLAG` — clinical module only; needs clinical event history to flag patterns (e.g. SpO₂ trend)
- `CLINICAL_SUMMARY` — clinical module only; synthesises clinical events into a narrative for the treating doctor

- [x] `apps/intelligence/constants.py` — `PromptType`, `RequestStatus`, `CLINICAL_ONLY_PROMPT_TYPES`, `DISCLAIMER`
- [x] `apps/intelligence/models.py` — `IntelligenceRequest`: patient FK, admission FK, requested_by (nullable SET NULL), prompt_type, status (PENDING/COMPLETED/FAILED), clinical_context_used (bool), response_text (text, nullable), disclaimer (text), tokens_used, latency_ms, completed_at
- [x] `apps/intelligence/services.py`:
  - `request_ai_query(*, user, patient, admission, prompt_type)` — creates row (PENDING), enqueues task, returns 202 immediately
  - `_build_tier1_context(admission)` — MRN, age, gender, LOS, ward/bed; handles string DOB from in-memory ORM objects
  - `_build_tier2_context(admission)` — last 20 `ClinicalEvent` rows + open `EscalationAlert` rows
  - `build_prompt(request)` — Tier 1 always + Tier 2 if `hospital.clinical_module_enabled`; returns `(prompt_text, clinical_context_used)`
  - `run_ai_query(request_id)` — calls Anthropic API; writes result + disclaimer; pushes WS notification; re-raises on failure (task owns FAILED)
  - `mark_request_failed(request_id)` — sets FAILED + completed_at
  - `get_request_queryset(*, user)` — hospital-scoped; SUPERADMIN sees all
- [x] `apps/intelligence/tasks.py` — `run_ai_query_task` (bind=True, max_retries=2, exponential backoff 2^n × 60 s)
- [x] `apps/intelligence/serializers.py` — `IntelligenceRequestSerializer`, `IntelligenceQueryCreateSerializer`
- [x] `apps/intelligence/views.py` — `QueryCreateView` (POST ADMIN+, returns 202), `QueryDetailView` (GET), `PatientIntelligenceHistoryView` (GET, nested under patients urls)
- [x] `apps/intelligence/urls.py`
- [x] `apps/intelligence/admin.py`
- [x] Migration `0001_initial`
- [x] Tests — 46 passing (28 service + 18 view); Anthropic patched via `patch("apps.intelligence.services.anthropic")`

### 6. `apps/communications` — WebSocket notifications ✅ DONE

Real-time push to connected clients (nurse station, doctor tablet) using Django Channels.

- [x] `HospitalConsumer` (AsyncJsonWebsocketConsumer) — JWT auth via `?token=` query param; joins `hospital_<id>` channel group on connect; handles `notify` events from group_send
- [x] Close codes: 4001 (missing/invalid token), 4002 (no hospital — SUPERADMIN not supported on WS)
- [x] `notify` event handler: persists `Notification` to DB for the connected user first, then delivers JSON to client (ordering guarantees DB write precedes receive_json in tests)
- [x] `Notification` model — user FK, hospital FK (nullable), kind (ESCALATION/INTELLIGENCE_COMPLETE/WORKFLOW_UPDATE/GENERAL), payload (JSONField), read_at (nullable), `is_read` property, BaseMixin
- [x] `GET /api/v1/notifications/` — list own notifications, paginated; `?unread=true` filter
- [x] `POST /api/v1/notifications/<id>/read/` — mark single notification read (idempotent)
- [x] `POST /api/v1/notifications/read-all/` — mark all own unread read
- [x] WebSocket routing wired into `config/asgi.py`; REST URLs in `config/urls.py`
- [x] `daphne` installed (required by channels.testing for WebsocketCommunicator)
- [x] Migration `0001_initial`
- [x] Tests — 35 passing (9 consumer via WebsocketCommunicator + TransactionTestCase, 11 service, 15 view)

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
