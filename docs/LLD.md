# Hospital Copilot — Low Level Design

## 1. Database Schema

### Conventions
- All tables use `BigAutoField` PKs (Django default).
- Every domain table inherits `BaseMixin` (audit timestamps + who) and where appropriate `SoftDeleteMixin` (logical delete).
- Soft-deleted rows are excluded by the default `objects` manager; `all_objects` sees everything.
- PII fields on Patient use `EncryptedCharField` / `EncryptedTextField` (AES-256 via `django-encrypted-model-fields`).
- Timezone-aware datetimes throughout (`USE_TZ = True`, `TIME_ZONE = "Asia/Kolkata"`).

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
| `password` | varchar(128) | not null (hashed) |
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

---

### 1.3 `patients` (apps.patients — Patient) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `mrn` | varchar(50) | not null, unique per hospital |
| `first_name` | EncryptedCharField | not null (AES-256) |
| `last_name` | EncryptedCharField | not null (AES-256) |
| `date_of_birth` | date | not null |
| `gender` | varchar(10) | not null, choices: MALE \| FEMALE \| OTHER |
| `blood_group` | varchar(5) | nullable, choices: A+ \| A- \| B+ \| B- \| AB+ \| AB- \| O+ \| O- |
| `contact_phone` | EncryptedCharField | nullable (AES-256) |
| `emergency_contact_name` | varchar(200) | nullable |
| `emergency_contact_phone` | EncryptedCharField | nullable (AES-256) |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `is_active` | boolean | not null, default true |
| + BaseMixin + SoftDeleteMixin columns | | |

---

### 1.4 `wards` (apps.patients — Ward) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `name` | varchar(100) | not null |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `capacity` | integer | not null |
| + BaseMixin + SoftDeleteMixin columns | | |

---

### 1.5 `beds` (apps.patients — Bed) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `number` | varchar(20) | not null |
| `ward_id` | bigint | FK → wards(id), not null, CASCADE |
| `is_occupied` | boolean | not null, default false |
| + BaseMixin columns | | |

Unique constraint: `(ward_id, number)`.

---

### 1.6 `admissions` (apps.patients — Admission) — planned

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

A patient may have multiple admissions over time (one active at a time, enforced in the service layer by checking `discharged_at IS NULL`).

---

### 1.7 `workflow_templates` (apps.workflows — WorkflowTemplate) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `name` | varchar(200) | not null |
| `hospital_id` | bigint | FK → hospitals(id), not null, CASCADE |
| `steps` | jsonb | not null — array of `{index, title, description}` |
| `trigger` | varchar(20) | not null, choices: ON\_ADMIT \| ON\_DISCHARGE \| MANUAL |
| `is_active` | boolean | not null, default true |
| + BaseMixin + SoftDeleteMixin columns | | |

---

### 1.8 `workflow_instances` (apps.workflows — WorkflowInstance) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `template_id` | bigint | FK → workflow\_templates(id), not null |
| `admission_id` | bigint | FK → admissions(id), not null |
| `status` | varchar(20) | not null, choices: PENDING \| IN\_PROGRESS \| COMPLETED \| CANCELLED |
| `assigned_to_id` | bigint | FK → users(id), nullable, SET NULL |
| `started_at` | timestamptz | nullable |
| `completed_at` | timestamptz | nullable |
| + BaseMixin columns | | |

---

### 1.9 `workflow_steps` (apps.workflows — WorkflowStep) — planned

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

---

### 1.10 `clinical_events` (apps.events — ClinicalEvent) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `patient_id` | bigint | FK → patients(id), not null |
| `admission_id` | bigint | FK → admissions(id), not null |
| `event_type` | varchar(20) | not null, choices: VITALS \| MEDICATION \| NURSE\_NOTE \| DOCTOR\_NOTE \| LAB\_RESULT \| ALERT \| OTHER |
| `recorded_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `recorded_at` | timestamptz | not null, default now() |
| `payload` | jsonb | not null — type-specific structured data |
| `notes` | text | blank |
| + BaseMixin columns | | |

Append-only: no update/delete exposed via API. `recorded_at` indexed for timeline queries.

---

### 1.11 `escalation_rules` (apps.escalations — EscalationRule) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `hospital_id` | bigint | FK → hospitals(id), not null |
| `name` | varchar(200) | not null |
| `condition` | jsonb | not null — rule DSL evaluated against event payload |
| `priority` | varchar(10) | not null, choices: LOW \| MEDIUM \| HIGH \| CRITICAL |
| `notify_roles` | varchar[] | array of UserRole values |
| `is_active` | boolean | not null, default true |
| + BaseMixin + SoftDeleteMixin columns | | |

---

### 1.12 `escalation_alerts` (apps.escalations — EscalationAlert) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `rule_id` | bigint | FK → escalation\_rules(id), not null |
| `patient_id` | bigint | FK → patients(id), not null |
| `admission_id` | bigint | FK → admissions(id), not null |
| `triggered_at` | timestamptz | not null, auto |
| `status` | varchar(20) | not null, choices: OPEN \| ACKNOWLEDGED \| RESOLVED |
| `acknowledged_at` | timestamptz | nullable |
| `acknowledged_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `resolved_at` | timestamptz | nullable |
| + BaseMixin columns | | |

---

### 1.13 `intelligence_requests` (apps.intelligence — IntelligenceRequest) — planned

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `patient_id` | bigint | FK → patients(id), not null |
| `admission_id` | bigint | FK → admissions(id), not null |
| `requested_by_id` | bigint | FK → users(id), nullable, SET NULL |
| `prompt_type` | varchar(20) | not null, choices: SUMMARY \| RISK\_FLAG \| NEXT\_ACTION \| DRUG\_CHECK |
| `status` | varchar(20) | not null, choices: PENDING \| COMPLETED \| FAILED |
| `response_text` | text | nullable |
| `tokens_used` | integer | nullable |
| `latency_ms` | integer | nullable |
| `created_at` | timestamptz | not null, auto |
| `completed_at` | timestamptz | nullable |

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

### 1.15 Entity Relationship (key relationships)

```
Hospital ──< User (hospital_id)
Hospital ──< Patient (hospital_id)
Hospital ──< Ward (hospital_id)
Hospital ──< WorkflowTemplate (hospital_id)
Hospital ──< EscalationRule (hospital_id)

Patient ──< Admission (patient_id)
Ward ──< Bed (ward_id)
Bed ──< Admission (bed_id)          [nullable]

Admission ──< WorkflowInstance (admission_id)
Admission ──< ClinicalEvent (admission_id)
Admission ──< EscalationAlert (admission_id)
Admission ──< IntelligenceRequest (admission_id)

WorkflowTemplate ──< WorkflowInstance (template_id)
WorkflowInstance ──< WorkflowStep (instance_id)

EscalationRule ──< EscalationAlert (rule_id)

User ──< Notification (user_id)
```

---

## 2. API Endpoint Specification

All endpoints are under `/api/v1/`. Default auth: `Authorization: Bearer <access_token>`. Errors follow the shape `{"error": "<ERROR_CODE>", "message": "<human text>"}`.

### 2.1 Auth (`/api/v1/auth/`)

#### `POST /auth/register/`
Auth: none  
Body:
```json
{
  "username": "string (required)",
  "password": "string (required, validated)",
  "email": "string (optional)",
  "first_name": "string (optional)",
  "last_name": "string (optional)",
  "role": "WARD_STAFF | NURSE | DOCTOR | ADMIN | SUPERADMIN (default: WARD_STAFF)",
  "hospital": "integer (hospital pk, optional)",
  "phone": "string (optional)"
}
```
Response `201`:
```json
{
  "user": { "id": 1, "username": "...", "role": "...", ... },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```
Errors: `400 VALIDATION_ERROR`, `409 CONFLICT` (duplicate username/email)

---

#### `POST /auth/login/`
Auth: none  
Body: `{"username": "string", "password": "string"}`  
Response `200`: `{"access": "<jwt>", "refresh": "<jwt>"}`  
Errors: `400 VALIDATION_ERROR` (bad credentials or inactive user)

---

#### `POST /auth/logout/`
Auth: required  
Body: `{"refresh": "<refresh_token>"}`  
Response `204`  
Errors: `400 VALIDATION_ERROR` (missing or invalid token)

---

#### `GET /auth/me/`
Auth: required  
Response `200`: `UserSerializer` object  

#### `PATCH /auth/me/`
Auth: required  
Body (partial): `{"first_name": "...", "last_name": "...", "phone": "..."}`  
Response `200`: updated `UserSerializer`  
Note: `role` and `hospital` are not patchable here; those are admin operations.

---

### 2.2 Patients (`/api/v1/patients/`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/patients/` | required | List patients (hospital-scoped, paginated). Query params: `search`, `ward`, `status` (active\|discharged) |
| `POST` | `/patients/` | ADMIN+ | Create patient record |
| `GET` | `/patients/<id>/` | required | Retrieve patient detail |
| `PATCH` | `/patients/<id>/` | NURSE+ | Update non-PII fields |
| `DELETE` | `/patients/<id>/` | ADMIN+ | Soft-delete |
| `POST` | `/patients/<id>/admit/` | WARD\_STAFF+ | Admit patient to a bed |
| `POST` | `/patients/<id>/discharge/` | WARD\_STAFF+ | Discharge patient |
| `GET` | `/patients/<id>/admissions/` | required | Admission history |
| `GET` | `/patients/<id>/events/` | required | Clinical event timeline |
| `GET` | `/patients/<id>/intelligence/` | DOCTOR\|NURSE | Past AI queries for this patient |
| `GET` | `/wards/` | required | List wards for the hospital |
| `GET` | `/wards/<id>/beds/` | required | List beds and occupancy |

---

### 2.3 Workflows (`/api/v1/workflows/`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/workflow-templates/` | required | List templates for the hospital |
| `POST` | `/workflow-templates/` | ADMIN+ | Create template |
| `GET` | `/workflow-templates/<id>/` | required | Retrieve template |
| `PATCH` | `/workflow-templates/<id>/` | ADMIN+ | Update template |
| `DELETE` | `/workflow-templates/<id>/` | ADMIN+ | Soft-delete |
| `POST` | `/workflow-instances/` | NURSE+ | Start a workflow for an admission |
| `GET` | `/workflow-instances/<id>/` | required | View instance and step statuses |
| `POST` | `/workflow-instances/<id>/steps/<step_index>/complete/` | NURSE+ | Complete a step |

---

### 2.4 Events (`/api/v1/events/`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/events/` | NURSE+ | Record a clinical event |
| `GET` | `/events/` | required | List events (filterable by patient, type, date range) |

---

### 2.5 Escalations (`/api/v1/escalations/`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/escalation-rules/` | ADMIN+ | List rules |
| `POST` | `/escalation-rules/` | ADMIN+ | Create rule |
| `PATCH` | `/escalation-rules/<id>/` | ADMIN+ | Update rule |
| `DELETE` | `/escalation-rules/<id>/` | ADMIN+ | Deactivate rule |
| `GET` | `/escalation-alerts/` | required | List open alerts (hospital-scoped) |
| `POST` | `/escalation-alerts/<id>/acknowledge/` | NURSE+ | Acknowledge alert |
| `POST` | `/escalation-alerts/<id>/resolve/` | DOCTOR+ | Resolve alert |

---

### 2.6 Intelligence (`/api/v1/intelligence/`) — planned

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/intelligence/query/` | DOCTOR\|NURSE | Submit AI query; returns `202 Accepted` with request id |
| `GET` | `/intelligence/<id>/` | required | Poll status and result |

---

### 2.7 Communications

| Protocol | Path | Auth | Description |
|----------|------|------|-------------|
| WebSocket | `wss://host/ws/notifications/?token=<jwt>` | JWT query param | Real-time push channel |
| `GET` | `/notifications/` | required | Persistent notification list (paginated) |
| `POST` | `/notifications/<id>/read/` | required | Mark notification as read |

---

## 3. Service Layer Design

Business logic lives in `services.py` within each app. Views call services; services call the ORM. Serializers are input/output contracts only — they do not contain logic.

```
View → serializer.is_valid() → service_function(**validated_data) → ORM
```

### Key service contracts (implemented)

```python
# apps/users/services.py
def register_user(*, username, email, password, first_name="",
                  last_name="", role=UserRole.WARD_STAFF,
                  hospital=None, phone="") -> User:
    # Raises ConflictError on duplicate username or email
```

### Key service contracts (planned)

```python
# apps/patients/services.py
def create_patient(*, mrn, first_name, last_name, date_of_birth,
                   gender, hospital, **kwargs) -> Patient: ...
def admit_patient(*, patient, bed, admitted_by) -> Admission: ...
def discharge_patient(*, admission, discharged_by) -> Admission: ...

# apps/events/services.py
def record_event(*, patient, admission, event_type,
                 recorded_by, payload, notes="") -> ClinicalEvent:
    # After save, enqueues evaluate_escalation_rules.delay(admission_id)

# apps/escalations/services.py
def evaluate_escalation_rules(admission_id: int) -> list[EscalationAlert]:
    # Called as Celery task; evaluates active rules against latest events

# apps/intelligence/services.py
def request_ai_query(*, patient, admission, prompt_type,
                     requested_by) -> IntelligenceRequest:
    # Creates request with status=PENDING, enqueues run_ai_query.delay(request_id)
def run_ai_query(request_id: int) -> None:
    # Celery task: builds context, calls Anthropic, stores result, pushes WS notification
```

---

## 4. Celery Task Design

```
config/celery.py        App definition (hospital_copilot)
apps/*/tasks.py         Tasks auto-discovered per app
```

### Planned tasks

| Task | Module | Triggered by | Retry |
|------|--------|-------------|-------|
| `evaluate_escalation_rules` | `apps.escalations.tasks` | `record_event()` | 3× exp backoff |
| `run_ai_query` | `apps.intelligence.tasks` | `request_ai_query()` | 2× |
| `push_notification` | `apps.communications.tasks` | Alert/workflow events | 3× |
| `send_webhook` | `apps.integrations.tasks` | Configurable triggers | 5× |

All tasks receive plain IDs (not ORM objects) to avoid serialisation issues.

---

## 5. WebSocket Consumer Design

```python
# apps/communications/consumers.py
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = self.scope["query_string"].decode().split("token=")[-1]
        user = await authenticate_jwt(token)   # raises if invalid
        if user is None:
            await self.close(code=4001)
            return
        self.group_name = f"hospital_{user.hospital_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        # Receives from group_send(); forwards to the WebSocket client
        await self.send(text_data=json.dumps(event["data"]))
```

Sending a push from any service:
```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    f"hospital_{hospital_id}",
    {"type": "notify", "data": {"kind": "ESCALATION", "alert_id": alert.id, ...}},
)
```

---

## 6. Authentication Flow (sequence)

```
Client                        Django                     PostgreSQL
  │                              │                              │
  │  POST /auth/login/           │                              │
  │  {username, password}        │                              │
  ├─────────────────────────────►│                              │
  │                              │  authenticate()              │
  │                              ├─────────────────────────────►│
  │                              │◄─────────────────────────────┤
  │                              │  User found, password OK     │
  │                              │  RefreshToken.for_user(user) │
  │◄─────────────────────────────┤                              │
  │  200 {access, refresh}       │                              │
  │                              │                              │
  │  GET /api/v1/auth/me/        │                              │
  │  Authorization: Bearer <AT>  │                              │
  ├─────────────────────────────►│                              │
  │                              │  JWTAuthentication:          │
  │                              │  verify signature, expiry    │
  │                              │  load user from token sub    │
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

All errors (DRF validation, AppError subclasses, unhandled exceptions) are normalised by `custom_exception_handler`:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description"
}
```

| Error code | HTTP | When |
|-----------|------|------|
| `VALIDATION_ERROR` | 400 | Input fails serializer or business rule |
| `NOT_FOUND` | 404 | Resource does not exist or is soft-deleted |
| `PERMISSION_DENIED` | 403 | Authenticated but insufficient role |
| `CONFLICT` | 409 | Duplicate username, email, MRN, etc. |
| `INTERNAL_ERROR` | 500 | Unhandled exception (logged with stack trace) |

DRF's own validation errors (`serializers.ValidationError`) return `400` with the standard DRF format `{"field": ["error"]}` — these are returned as-is by the exception handler (the `response is not None` branch).

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

Defaults: `page_size=25`, max `200`. Override with `?page_size=50`.

---

## 9. Permission Matrix

| Endpoint group | WARD\_STAFF | NURSE | DOCTOR | ADMIN | SUPERADMIN |
|----------------|:-----------:|:-----:|:------:|:-----:|:----------:|
| Auth (register/login/me) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Patient read | ✓ | ✓ | ✓ | ✓ | ✓ |
| Patient create/update | — | ✓ | ✓ | ✓ | ✓ |
| Patient delete (soft) | — | — | — | ✓ | ✓ |
| Admit / Discharge | ✓ | ✓ | ✓ | ✓ | ✓ |
| Record clinical event | — | ✓ | ✓ | ✓ | ✓ |
| Workflow step complete | — | ✓ | ✓ | ✓ | ✓ |
| Acknowledge alert | — | ✓ | ✓ | ✓ | ✓ |
| Resolve alert | — | — | ✓ | ✓ | ✓ |
| AI query | — | ✓ | ✓ | ✓ | ✓ |
| Manage templates/rules | — | — | — | ✓ | ✓ |
| Cross-hospital access | — | — | — | — | ✓ |

---

## 10. Settings & Configuration Summary

| Setting | Value |
|---------|-------|
| `AUTH_USER_MODEL` | `users.User` |
| `JWT ACCESS_TOKEN_LIFETIME` | 8 hours |
| `JWT REFRESH_TOKEN_LIFETIME` | 7 days |
| `JWT ROTATE_REFRESH_TOKENS` | True |
| `JWT BLACKLIST_AFTER_ROTATION` | True |
| `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` | `JWTAuthentication` |
| `REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES` | `IsAuthenticated` |
| `CELERY_TIMEZONE` | `Asia/Kolkata` |
| `TIME_ZONE` | `Asia/Kolkata` |
| `DEFAULT_AUTO_FIELD` | `BigAutoField` |
| `CHANNEL_LAYERS backend` | `channels_redis.core.RedisChannelLayer` |
