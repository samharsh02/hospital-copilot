# Hospital Copilot — Low Level Design

## 0. Design Philosophy

The LLD documents the concrete implementation choices — schemas, contracts, and invariants. Every decision here has a reason; this section captures the non-obvious ones so they can be defended or revisited deliberately.

### Critical invariants the system must never violate

These are not enforced by the database alone — they are enforced in the service layer, tested explicitly, and must survive any refactor:

| Invariant | Where enforced |
|---|---|
| A patient may have at most one active admission at a time | `admit_patient()` checks `discharged_at IS NULL` before creating a new `Admission` |
| A bed may only be occupied by one patient at a time | `admit_patient()` checks `bed.is_occupied` before assigning; `discharge_patient()` sets it back to `False` |
| An event cannot be recorded against a discharged admission | `record_event()` checks `admission.discharged_at IS NULL` |
| An event's admission must belong to its patient | `record_event()` checks `admission.patient_id == patient.pk` |
| A workflow cannot start on an inactive template | `start_workflow()` checks `template.is_active` |
| A workflow cannot start on a discharged admission | `start_workflow()` checks `admission.discharged_at IS NULL` |
| Hospital scoping: a user sees only their hospital's data | Every `get_*_queryset()` applies `filter(hospital=user.hospital)` unless `SUPERADMIN` |
| AI outputs cannot write to patient records | The `intelligence` app has no ORM write path to `patients`, `events`, or `admissions` |

### Why the service layer, not database constraints?

Most of the above could theoretically be expressed as partial indexes or triggers in Postgres. We chose the service layer because:
- It is testable in isolation without a running database
- Error messages are domain-specific (e.g. "Patient already has an active admission"), not Postgres constraint violation strings
- The logic is readable by anyone who opens `services.py`, not hidden in a migration

Database-level constraints are used for structural guarantees only (PKs, FKs, NOT NULL, unique_together).

### AI contract at the service layer

The `intelligence` app's service layer is the only place in the codebase where an external API call is made. Its design contract:

- Input: structured data pulled from the database (events, admissions) — never raw user text
- Output: stored as `IntelligenceRequest.response_text` with full metadata (prompt type, tokens used, latency, status)
- Side effects: exactly one — a WebSocket push to the requesting user after the task completes
- No write path: the service reads from `events` and `admissions`, writes only to `intelligence_requests`
- Retry policy: 2× with exponential backoff; on final failure, `status=FAILED` is set so the client can see the query did not complete

This contract ensures that even if Claude returns a hallucinated or harmful output, no data is automatically written to clinical records.

---

## 1. Database Schema

### Conventions

- All tables use `BigAutoField` PKs (Django default).
- Every domain table inherits `BaseMixin` (`created_at`, `updated_at`, `created_by_id`, `updated_by_id`). Entities that can be logically deleted also inherit `SoftDeleteMixin` (`is_deleted`, `deleted_at`, `deleted_by_id`).
- Soft-deleted rows are excluded by the default `objects` manager; `all_objects` sees everything.
- PII fields on `Patient` use `EncryptedCharField` (AES-256 via `django-encrypted-model-fields`, Fernet). These fields cannot be searched at the database level — search is done by MRN (unencrypted).
- All datetimes are timezone-aware (`USE_TZ = True`, `TIME_ZONE = "Asia/Kolkata"`).

---

### 1.1 `hospitals` (apps.core — Hospital)

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `name` | varchar(200) | not null |
| `type` | varchar(20) | not null, choices: PRIVATE\_SINGLE \| PRIVATE\_CHAIN \| GOVERNMENT \| TRUST |
| `city` | varchar(100) | not null |
| `state` | varchar(100) | not null |
| `bed_count` | integer | not null |
| `is_active` | boolean | not null, default true |
| `created_at` | timestamptz | not null, auto |
| `updated_at` | timestamptz | not null, auto |
| `created_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `updated_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `is_deleted` | boolean | not null, default false, indexed |
| `deleted_at` | timestamptz | nullable |
| `deleted_by_id` | bigint | FK → users(id), nullable, SET NULL |

---

### 1.2 `users` (apps.users — User, extends auth\_user)

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `username` | varchar(150) | not null, unique |
| `email` | varchar(254) | not null |
| `password` | varchar(128) | not null (hashed, Django PBKDF2) |
| `first_name` | varchar(150) | not null, default "" |
| `last_name` | varchar(150) | not null, default "" |
| `is_staff` | boolean | not null, default false |
| `is_active` | boolean | not null, default true |
| `is_superuser` | boolean | not null, default false |
| `last_login` | timestamptz | nullable |
| `date_joined` | timestamptz | not null, auto |
| `role` | varchar(20) | not null, default "WARD\_STAFF", choices: SUPERADMIN \| ADMIN \| DOCTOR \| NURSE \| WARD\_STAFF |
| `hospital_id` | bigint | FK → hospitals(id), nullable, SET NULL |
| `phone` | varchar(20) | not null, default "" |

**Design note:** `hospital_id` is nullable to allow SUPERADMIN users who span all hospitals. Non-SUPERADMIN users without a hospital assignment cannot see any data — the scoping filter returns an empty queryset.

---

### 1.3 `patients` (apps.patients — Patient) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `mrn` | varchar(50) | not null, unique per hospital |
| `first_name` | EncryptedCharField | not null (AES-256) |
| `last_name` | EncryptedCharField | not null (AES-256) |
| `date_of_birth` | date | not null |
| `gender` | varchar(10) | not null, choices: MALE \| FEMALE \| OTHER |
| `blood_group` | varchar(5) | blank, choices: A+ \| A- \| B+ \| B- \| AB+ \| AB- \| O+ \| O- |
| `contact_phone` | EncryptedCharField | blank (AES-256) |
| `emergency_contact_name` | varchar(200) | blank |
| `emergency_contact_phone` | EncryptedCharField | blank (AES-256) |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `is_active` | boolean | not null, default true |
| + BaseMixin + SoftDeleteMixin columns | | |

Unique constraint: `(hospital_id, mrn)` — MRN is unique within a hospital, not globally.

---

### 1.4 `wards` (apps.patients — Ward) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `name` | varchar(100) | not null |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `capacity` | integer | not null |
| + BaseMixin + SoftDeleteMixin columns | | |

---

### 1.5 `beds` (apps.patients — Bed) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `number` | varchar(20) | not null |
| `ward_id` | bigint | FK → wards(id), not null, CASCADE |
| `is_occupied` | boolean | not null, default false |
| + BaseMixin columns | | |

Unique constraint: `(ward_id, number)`.

**Design note:** `is_occupied` is a denormalised flag maintained by the service layer. It is set to `True` by `admit_patient()` and `False` by `discharge_patient()`. This avoids a subquery on the admissions table for every bed list view.

---

### 1.6 `admissions` (apps.patients — Admission) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `patient_id` | bigint | FK → patients(id), not null, CASCADE |
| `bed_id` | bigint | FK → beds(id), nullable, SET NULL |
| `admitted_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `admitted_at` | timestamptz | not null |
| `discharged_at` | timestamptz | nullable |
| `notes` | text | blank |
| + BaseMixin columns | | |

A patient may have multiple admissions over time. Exactly one may be active (`discharged_at IS NULL`) at any time — enforced in `admit_patient()`.

**Design note:** We do not add a database-level partial unique index on `(patient_id, discharged_at IS NULL)` in V1 because it complicates the migration and the service-layer guard with an explicit test is sufficient. This is a known trade-off.

---

### 1.7 `workflow_templates` (apps.workflows — WorkflowTemplate) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `name` | varchar(200) | not null |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `steps` | jsonb | not null — array of `{index: int, title: str, description: str}` |
| `trigger` | varchar(20) | not null, choices: ON\_ADMIT \| ON\_DISCHARGE \| MANUAL |
| `is_active` | boolean | not null, default true |
| + BaseMixin + SoftDeleteMixin columns | | |

**Design note:** Steps are stored as JSONB on the template rather than as a separate table. This avoids a join on every template read, allows the template to evolve without affecting existing instances (which snapshot the step titles at start time into `WorkflowStep` rows), and keeps template CRUD simple.

---

### 1.8 `workflow_instances` (apps.workflows — WorkflowInstance) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `template_id` | bigint | FK → workflow\_templates(id), not null, CASCADE |
| `admission_id` | bigint | FK → admissions(id), not null, CASCADE |
| `status` | varchar(20) | not null, choices: PENDING \| IN\_PROGRESS \| COMPLETED \| CANCELLED |
| `assigned_to_id` | bigint | FK → users(id), nullable, SET NULL |
| `started_at` | timestamptz | nullable |
| `completed_at` | timestamptz | nullable |
| + BaseMixin columns | | |

Status transitions: `PENDING → IN_PROGRESS` (first step completed) `→ COMPLETED` (all steps done) or `→ CANCELLED`.

---

### 1.9 `workflow_steps` (apps.workflows — WorkflowStep) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `instance_id` | bigint | FK → workflow\_instances(id), not null, CASCADE |
| `step_index` | integer | not null |
| `title` | varchar(200) | not null |
| `is_completed` | boolean | not null, default false |
| `completed_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `completed_at` | timestamptz | nullable |
| `notes` | text | blank |
| + BaseMixin columns | | |

Unique constraint: `(instance_id, step_index)`.

**Design note:** Step rows are created from the template's JSONB at instance start time (`start_workflow()`). This means the step titles are a snapshot — changing the template later does not affect in-progress instances.

---

### 1.10 `clinical_events` (apps.events — ClinicalEvent) ✅ implemented

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `patient_id` | bigint | FK → patients(id), not null, CASCADE |
| `admission_id` | bigint | FK → admissions(id), not null, CASCADE |
| `event_type` | varchar(20) | not null, choices: VITALS \| MEDICATION \| NURSE\_NOTE \| DOCTOR\_NOTE \| LAB\_RESULT \| ALERT \| OTHER |
| `recorded_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `recorded_at` | timestamptz | not null, default now(), indexed |
| `payload` | jsonb | not null — type-specific structured data |
| `notes` | text | blank |
| + BaseMixin columns | | |

Append-only: no UPDATE or DELETE is exposed via the API. `recorded_at` is indexed because it is the primary ordering key for the event timeline and for the AI context window query ("last N events before now").

**Design note on payload schema:** We deliberately do not enforce a JSONB schema per event type at the database level. The flexibility allows a hospital to add custom fields (e.g. blood pressure cuff ID) without a migration. Validation can be added later at the serializer level if standardisation becomes important.

---

### 1.11 `escalation_rules` (apps.escalations — EscalationRule) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `name` | varchar(200) | not null |
| `condition` | jsonb | not null — rule DSL evaluated against event payload |
| `priority` | varchar(10) | not null, choices: LOW \| MEDIUM \| HIGH \| CRITICAL |
| `notify_roles` | varchar[] | array of UserRole values — which roles receive the alert push |
| `is_active` | boolean | not null, default true |
| + BaseMixin + SoftDeleteMixin columns | | |

**Design note on the rule DSL:** The `condition` field stores a JSON expression that is evaluated against the event payload. Example:
```json
{"field": "payload.spo2", "op": "lt", "value": 90}
```
The evaluator in `escalations/services.py` supports `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, and `in`. This is intentionally simple — it is not a Turing-complete rule engine. Complex logic should be multiple rules.

**Why rules and not AI for escalations:** A rule either fires or it does not. This is auditable. An ML model cannot provide that guarantee in a safety-critical context. False negatives (missed critical alerts) are unacceptable in a clinical setting; we accept a higher false positive rate from conservative rules over any false negative risk from a probabilistic model.

---

### 1.12 `escalation_alerts` (apps.escalations — EscalationAlert) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `rule_id` | bigint | FK → escalation\_rules(id), not null, CASCADE |
| `patient_id` | bigint | FK → patients(id), not null, CASCADE |
| `admission_id` | bigint | FK → admissions(id), not null, CASCADE |
| `triggered_at` | timestamptz | not null, auto |
| `status` | varchar(20) | not null, choices: OPEN \| ACKNOWLEDGED \| RESOLVED |
| `acknowledged_at` | timestamptz | nullable |
| `acknowledged_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `resolved_at` | timestamptz | nullable |
| + BaseMixin columns | | |

Status transitions: `OPEN → ACKNOWLEDGED` (NURSE+) `→ RESOLVED` (DOCTOR+). Only DOCTOR or above can resolve — this enforces that a physician has reviewed the alert before it is closed.

---

### 1.13 `intelligence_requests` (apps.intelligence — IntelligenceRequest) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `patient_id` | bigint | FK → patients(id), not null, CASCADE |
| `admission_id` | bigint | FK → admissions(id), not null, CASCADE |
| `requested_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `prompt_type` | varchar(20) | not null, choices: SUMMARY \| RISK\_FLAG \| NEXT\_ACTION \| DRUG\_CHECK |
| `status` | varchar(20) | not null, choices: PENDING \| COMPLETED \| FAILED |
| `response_text` | text | nullable |
| `tokens_used` | integer | nullable |
| `latency_ms` | integer | nullable |
| `created_at` | timestamptz | not null, auto |
| `completed_at` | timestamptz | nullable |

**Design note:** Every AI query is persisted. This creates an audit trail: which clinician asked what, with what patient context, and what Claude responded. Token counts and latency support cost monitoring and performance analysis. If a response is later disputed, the exact request can be reconstructed.

---

### 1.14 `notifications` (apps.communications — Notification) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `user_id` | bigint | FK → users(id), not null, CASCADE |
| `type` | varchar(30) | not null, choices: ESCALATION \| WORKFLOW \| SYSTEM |
| `message` | text | not null |
| `payload` | jsonb | nullable — extra context (e.g. patient\_id, alert\_id) |
| `read_at` | timestamptz | nullable |
| `created_at` | timestamptz | not null, auto |

---

### 1.15 Entity Relationship

```
Hospital ──< User (hospital_id)
Hospital ──< Patient (hospital_id)
Hospital ──< Ward (hospital_id)
Hospital ──< WorkflowTemplate (hospital_id)
Hospital ──< EscalationRule (hospital_id)

Patient ──< Admission (patient_id)
Ward ──< Bed (ward_id)
Bed ──< Admission (bed_id)                  [nullable]

Admission ──< WorkflowInstance (admission_id)
Admission ──< ClinicalEvent (admission_id)
Admission ──< EscalationAlert (admission_id)
Admission ──< IntelligenceRequest (admission_id)

WorkflowTemplate ──< WorkflowInstance (template_id)
WorkflowInstance ──< WorkflowStep (instance_id)

EscalationRule ──< EscalationAlert (rule_id)

User ──< Notification (user_id)
```

The `Admission` entity is the central hub of the clinical data model. All activity (events, workflows, alerts, AI queries) is scoped to an admission, not just a patient. This is intentional: the same patient may be admitted multiple times, and each admission is a separate clinical episode with its own timeline.

---

## 2. API Endpoint Specification

All endpoints are under `/api/v1/`. Auth: `Authorization: Bearer <access_token>`. Errors follow `{"error": "<ERROR_CODE>", "message": "<human text>"}`.

### 2.1 Auth (`/api/v1/auth/`) ✅ implemented

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register/` | none | Register user; returns access + refresh tokens |
| `POST` | `/auth/login/` | none | Authenticate; returns access + refresh tokens |
| `POST` | `/auth/logout/` | required | Blacklist refresh token |
| `GET` | `/auth/me/` | required | Current user profile |
| `PATCH` | `/auth/me/` | required | Update first\_name, last\_name, phone (role and hospital are admin-only changes) |

#### `POST /auth/register/` — body
```json
{
  "username": "string (required)",
  "password": "string (required, min 8 chars)",
  "email": "string (optional)",
  "first_name": "string (optional)",
  "last_name": "string (optional)",
  "role": "WARD_STAFF | NURSE | DOCTOR | ADMIN | SUPERADMIN (default: WARD_STAFF)",
  "hospital": "integer (hospital pk, optional)",
  "phone": "string (optional)"
}
```
Response `201`: `{"user": {...}, "access": "<jwt>", "refresh": "<jwt>"}`
Errors: `400 VALIDATION_ERROR`, `409 CONFLICT` (duplicate username/email)

#### `POST /auth/login/` — body
```json
{"username": "string", "password": "string"}
```
Response `200`: `{"access": "<jwt>", "refresh": "<jwt>"}`

---

### 2.2 Patients (`/api/v1/patients/`) ✅ implemented

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/patients/` | required | List (hospital-scoped, paginated). Params: `search` (MRN), `ward`, `status` (active\|discharged) |
| `POST` | `/patients/` | ADMIN+ | Create patient record |
| `GET` | `/patients/<id>/` | required | Patient detail |
| `PATCH` | `/patients/<id>/` | NURSE+ | Update non-PII fields |
| `DELETE` | `/patients/<id>/` | ADMIN+ | Soft-delete |
| `POST` | `/patients/<id>/admit/` | required | Admit to bed (bed optional) |
| `POST` | `/patients/<id>/discharge/` | required | Discharge; frees bed |
| `GET` | `/patients/<id>/admissions/` | required | Admission history |
| `GET` | `/patients/<id>/events/` | required | Clinical event timeline; params: `event_type`, `date_from`, `date_to` |
| `GET` | `/wards/` | required | List wards for the hospital |
| `GET` | `/wards/<id>/beds/` | required | List beds and occupancy |

---

### 2.3 Workflows (`/api/v1/workflow-*`) ✅ implemented

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/workflow-templates/` | required | List templates (hospital-scoped). Param: `active` (true\|false) |
| `POST` | `/workflow-templates/` | ADMIN+ | Create template |
| `GET` | `/workflow-templates/<id>/` | required | Retrieve template |
| `PATCH` | `/workflow-templates/<id>/` | ADMIN+ | Update template |
| `DELETE` | `/workflow-templates/<id>/` | ADMIN+ | Soft-delete |
| `GET` | `/workflow-instances/` | required | List instances. Params: `template`, `admission` |
| `POST` | `/workflow-instances/` | NURSE+ | Start instance from template for an admission |
| `GET` | `/workflow-instances/<id>/` | required | Detail with steps nested inline |
| `POST` | `/workflow-instances/<id>/steps/<n>/complete/` | NURSE+ | Complete a step; auto-advances instance status |
| `POST` | `/workflow-instances/<id>/cancel/` | NURSE+ | Cancel instance |

---

### 2.4 Events (`/api/v1/events/`) ✅ implemented

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/events/` | NURSE+ | Record clinical event. Guards: discharged admission → 400, wrong patient → 400 |
| `GET` | `/events/` | required | List events (hospital-scoped). Params: `patient`, `admission`, `event_type`, `date_from`, `date_to` |

---

### 2.5 Escalations (`/api/v1/escalation-*`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/escalation-rules/` | ADMIN+ | List rules for the hospital |
| `POST` | `/escalation-rules/` | ADMIN+ | Create rule |
| `PATCH` | `/escalation-rules/<id>/` | ADMIN+ | Update rule |
| `DELETE` | `/escalation-rules/<id>/` | ADMIN+ | Soft-delete (deactivate) |
| `GET` | `/escalation-alerts/` | required | List alerts (hospital-scoped). Param: `status` (OPEN\|ACKNOWLEDGED\|RESOLVED) |
| `POST` | `/escalation-alerts/<id>/acknowledge/` | NURSE+ | Acknowledge alert |
| `POST` | `/escalation-alerts/<id>/resolve/` | DOCTOR+ | Resolve alert |

---

### 2.6 Intelligence (`/api/v1/intelligence/`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/intelligence/query/` | NURSE+ | Submit AI query. Returns `202 Accepted` with `{"request_id": <id>}` |
| `GET` | `/intelligence/<id>/` | required | Poll status and result. Status: PENDING \| COMPLETED \| FAILED |
| `GET` | `/patients/<id>/intelligence/` | required | Past AI queries for this patient |

**Design note:** The `202 Accepted` pattern is intentional. Making AI calls synchronously would hold a uvicorn worker for 2–15 seconds, blocking other requests. The client either polls `GET /intelligence/<id>/` or waits for a WebSocket push.

---

### 2.7 Communications — planned

| Protocol | Path | Auth | Description |
|----------|------|------|-------------|
| WebSocket | `wss://host/ws/notifications/?token=<jwt>` | JWT query param | Real-time push channel, hospital-scoped |
| `GET` | `/notifications/` | required | Persistent notification list (paginated) |
| `POST` | `/notifications/<id>/read/` | required | Mark notification as read |

---

## 3. Service Layer Design

Business logic lives exclusively in `services.py` within each app. The data flow is:

```
View → serializer.is_valid() → service_function(**validated_data) → ORM → database
```

Views do not contain business logic. Serializers are input/output contracts only — they validate and deserialise, but do not call each other or the ORM directly.

### Why a service layer?

Without it, business logic migrates into views (hard to test without HTTP) or serializers (violates single responsibility). The service layer gives us:
- Pure functions testable with `TestCase` (no HTTP, no serializer overhead)
- A single place to enforce invariants
- A clear write path for each operation — a reviewer can audit what a POST does by reading one function

### Key service contracts (implemented)

```python
# apps/users/services.py
def register_user(*, username, email, password, first_name="",
                  last_name="", role=UserRole.WARD_STAFF,
                  hospital=None, phone="") -> User:
    # Raises ConflictError on duplicate username or email

# apps/patients/services.py
def create_patient(*, user, hospital, mrn, first_name, last_name,
                   date_of_birth, gender, **kwargs) -> Patient:
    # Raises ConflictError if MRN already exists in the hospital

def admit_patient(*, user, patient, bed=None, notes="") -> Admission:
    # Raises ValidationError if patient already admitted
    # Raises ConflictError if bed is occupied
    # Raises ValidationError if bed is from wrong hospital

def discharge_patient(*, user, patient) -> Admission:
    # Raises ValidationError if no active admission

# apps/workflows/services.py
def start_workflow(*, user, template, admission, assigned_to=None) -> WorkflowInstance:
    # Raises ValidationError if template.hospital != admission.patient.hospital
    # Raises ValidationError if template is inactive
    # Raises ValidationError if admission is discharged
    # Creates WorkflowStep rows from template.steps (snapshot)

def complete_step(*, user, instance, step_index, notes="") -> WorkflowStep:
    # Raises ValidationError if instance is COMPLETED or CANCELLED
    # Raises ValidationError if step_index not found
    # Raises ConflictError if step already completed
    # Auto-advances instance: PENDING→IN_PROGRESS on first step, →COMPLETED when all done

# apps/events/services.py
def record_event(*, user, patient, admission, event_type, payload, notes="") -> ClinicalEvent:
    # Raises ValidationError if admission.patient_id != patient.pk
    # Raises ValidationError if admission is discharged
    # After save: enqueues evaluate_escalation_rules.delay(admission.pk) [planned]
```

### Key service contracts (planned)

```python
# apps/escalations/services.py
def evaluate_escalation_rules(admission_id: int) -> list[EscalationAlert]:
    # Called as Celery task after every clinical event
    # Loads all active EscalationRules for the hospital
    # Evaluates each rule's condition JSON against the latest event payload
    # Creates EscalationAlert rows for matching rules
    # Pushes WebSocket notification to hospital group

# apps/intelligence/services.py
def request_ai_query(*, user, patient, admission, prompt_type) -> IntelligenceRequest:
    # Creates IntelligenceRequest (status=PENDING)
    # Enqueues run_ai_query.delay(request_id)
    # Returns immediately (caller gets request_id for polling)

def run_ai_query(request_id: int) -> None:
    # Celery task
    # Fetches IntelligenceRequest and its patient/admission context
    # Builds prompt from last N ClinicalEvents (structured data only)
    # Calls anthropic.messages.create() with the prompt
    # Updates IntelligenceRequest: status=COMPLETED, response_text, tokens_used, latency_ms
    # Pushes WebSocket push to requesting user
    # On failure (after retries): status=FAILED
```

---

## 4. Celery Task Design

```
config/celery.py        App definition (hospital_copilot)
apps/*/tasks.py         Tasks auto-discovered per app
```

All tasks receive plain database IDs, never ORM objects. This is required because Celery serialises arguments with JSON; ORM objects are not serialisable and would create stale-data bugs if they were.

| Task | Module | Triggered by | Retry policy |
|------|--------|-------------|-------|
| `evaluate_escalation_rules` | `apps.escalations.tasks` | `record_event()` | 3× exponential backoff |
| `run_ai_query` | `apps.intelligence.tasks` | `request_ai_query()` | 2× exponential backoff; sets `status=FAILED` on exhaustion |
| `push_notification` | `apps.communications.tasks` | Alert / workflow events | 3× exponential backoff |
| `send_webhook` | `apps.integrations.tasks` | Configurable triggers | 5× exponential backoff |

---

## 5. WebSocket Consumer Design

```python
# apps/communications/consumers.py
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = self.scope["query_string"].decode().split("token=")[-1]
        user = await authenticate_jwt(token)
        if user is None:
            await self.close(code=4001)   # reject before joining any group
            return
        self.group_name = f"hospital_{user.hospital_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        await self.send(text_data=json.dumps(event["data"]))
```

Pushing from a synchronous service:
```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

async_to_sync(get_channel_layer().group_send)(
    f"hospital_{hospital_id}",
    {"type": "notify", "data": {"kind": "ESCALATION", "alert_id": alert.id}},
)
```

Hospital-scoped groups mean a notification always reaches exactly the right staff and never leaks across hospital boundaries.

---

## 6. Authentication Flow

```
Client                        Django                     PostgreSQL
  │                              │                              │
  │  POST /auth/login/           │                              │
  │  {username, password}        │                              │
  ├─────────────────────────────►│                              │
  │                              │  authenticate()              │
  │                              ├─────────────────────────────►│
  │                              │◄─────────────────────────────┤
  │                              │  User + password OK          │
  │                              │  RefreshToken.for_user(user) │
  │◄─────────────────────────────┤                              │
  │  200 {access, refresh}       │                              │
  │                              │                              │
  │  GET /api/v1/auth/me/        │                              │
  │  Authorization: Bearer <AT>  │                              │
  ├─────────────────────────────►│                              │
  │                              │  JWTAuthentication:          │
  │                              │  verify signature + expiry   │
  │                              │  load user from token `sub`  │
  │◄─────────────────────────────┤                              │
  │  200 {user object}           │                              │
  │                              │                              │
  │  POST /auth/logout/          │                              │
  │  {refresh: "<RT>"}           │                              │
  ├─────────────────────────────►│                              │
  │                              │  RefreshToken(rt).blacklist()│
  │                              ├─────────────────────────────►│
  │                              │  token_blacklist row inserted│
  │◄─────────────────────────────┤                              │
  │  204 No Content              │                              │
```

---

## 7. Error Response Format

All errors are normalised by `custom_exception_handler` in `apps/core/exceptions.py`:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description"
}
```

| Error code | HTTP | When |
|-----------|------|------|
| `VALIDATION_ERROR` | 400 | Input fails serializer validation or a service-layer business rule |
| `NOT_FOUND` | 404 | Resource does not exist, is soft-deleted, or is out of hospital scope |
| `PERMISSION_DENIED` | 403 | Authenticated but insufficient role |
| `CONFLICT` | 409 | Duplicate MRN, username, email, bed already occupied, step already completed |
| `INTERNAL_ERROR` | 500 | Unhandled exception (logged with full stack trace) |

DRF's own field-level validation errors (`{"field": ["message"]}`) pass through unchanged as `400`.

---

## 8. Pagination

All list endpoints use `StandardPagination`:

```json
{
  "count": 142,
  "next": "http://host/api/v1/patients/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Defaults: `page_size=25`, max `page_size=200`.

---

## 9. Permission Matrix

| Endpoint group | WARD\_STAFF | NURSE | DOCTOR | ADMIN | SUPERADMIN |
|----------------|:-----------:|:-----:|:------:|:-----:|:----------:|
| Auth (register / login / me) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Patient read | ✓ | ✓ | ✓ | ✓ | ✓ |
| Patient create | — | — | — | ✓ | ✓ |
| Patient update (non-PII) | — | ✓ | ✓ | ✓ | ✓ |
| Patient soft-delete | — | — | — | ✓ | ✓ |
| Admit / discharge | ✓ | ✓ | ✓ | ✓ | ✓ |
| Record clinical event | — | ✓ | ✓ | ✓ | ✓ |
| Complete workflow step | — | ✓ | ✓ | ✓ | ✓ |
| Cancel workflow | — | ✓ | ✓ | ✓ | ✓ |
| Acknowledge escalation alert | — | ✓ | ✓ | ✓ | ✓ |
| Resolve escalation alert | — | — | ✓ | ✓ | ✓ |
| Submit AI query | — | ✓ | ✓ | ✓ | ✓ |
| Manage templates / rules | — | — | — | ✓ | ✓ |
| Cross-hospital access | — | — | — | — | ✓ |

---

## 10. Settings Reference

| Setting | Value | Why |
|---------|-------|-----|
| `AUTH_USER_MODEL` | `users.User` | Custom user with role and hospital FK |
| `JWT ACCESS_TOKEN_LIFETIME` | 8 hours | Covers a standard nursing shift without requiring mid-shift re-login |
| `JWT REFRESH_TOKEN_LIFETIME` | 7 days | Weekly re-authentication |
| `JWT ROTATE_REFRESH_TOKENS` | True | Each use issues a new refresh token |
| `JWT BLACKLIST_AFTER_ROTATION` | True | Old refresh token cannot be replayed |
| `DEFAULT_AUTHENTICATION_CLASSES` | `JWTAuthentication` | Stateless auth; no server-side sessions |
| `DEFAULT_PERMISSION_CLASSES` | `IsAuthenticated` | All endpoints require auth unless explicitly overridden |
| `CELERY_TIMEZONE` | `Asia/Kolkata` | Task schedules match clinical shift times |
| `TIME_ZONE` | `Asia/Kolkata` | All timestamps stored as UTC, displayed in IST |
| `DEFAULT_AUTO_FIELD` | `BigAutoField` | Future-proof PK size (> 2 billion rows) |
| `CHANNEL_LAYERS backend` | `channels_redis.core.RedisChannelLayer` | Redis DB 0 for WebSocket group messaging |
