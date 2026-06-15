# Hospital Copilot — High Level Design

## 1. Problem Statement

### 1.1 Problems We Are Solving

Clinical staff in hospital wards operate across multiple disconnected tools — paper checklists, verbal handoffs, and separate HIS/EMR systems that do not talk to each other. This creates four concrete failure modes:

1. **Missed escalations.** A nurse records a dangerously low SpO₂ reading in one place; a doctor on a different system never sees it. Escalation depends on verbal communication, which fails at handoff time.
2. **Checklist drift.** Admission, discharge, and round-based checklists exist on paper or in generic tools. Steps get skipped, signed off without being done, or differ between shifts.
3. **Cognitive overload.** A senior doctor managing 15–20 patients in a ward cannot hold a coherent picture of each patient's last 24 hours of events. They need a synthesised view, not a raw log.
4. **No audit trail.** When a near-miss or adverse event occurs, reconstructing the timeline of what was done, when, and by whom is extremely difficult. Accountability gaps drive poor institutional learning.

Hospital Copilot is a single API-first backend that centralises patient tracking, structured workflows, an append-only clinical event log, deterministic escalation rules, and AI-assisted decision support. It is designed to make the above failure modes structurally impossible rather than culturally discouraged.

### 1.2 Problems We Are NOT Solving

These are explicit out-of-scope decisions, made to keep the system focused and to avoid crossing clinical safety boundaries the system is not equipped to handle:

| Out of Scope | Why |
|---|---|
| Clinical diagnosis | This is a physician's legal and professional responsibility. The system must not produce or imply diagnoses. |
| Prescribing / medication orders | Prescribing involves drug databases, pharmacist review, and regulatory liability. Out of scope entirely. |
| Replacing clinical judgment | AI outputs are suggestions for review, never authoritative instructions. |
| Full EMR replacement | The system complements an existing HIS/EMR, not replaces it. We are the operational layer on top. |
| Medical device integration | Vitals from bedside monitors, infusion pumps, ventilators — not in scope. Data is manually entered. |
| Offline mode | All clinical data must be centrally stored and consistent. There is no offline-first design. |
| Billing and insurance | No financial workflows, insurance codes, or payer integrations. |
| Regulatory compliance (HIPAA, GDPR) | PII encryption and access control are in place, but formal compliance certification is not part of this release. |
| Scheduling and shift management | Staff scheduling, rosters, and leave management are separate concerns. |

### 1.3 Problems That Can Be Solved Later

These are valid problems that sit in the system's natural direction of growth but are deliberately deferred:

| Deferred Problem | When It Becomes Relevant |
|---|---|
| FHIR/HL7 integration with existing HIS | When the hospital has a compatible HIS and needs bidirectional sync |
| Medical device data ingestion (IoT) | When wards have device APIs to expose — removes manual vitals entry |
| Predictive risk scoring (ML) | After 6–12 months of event data; requires a labelled dataset |
| Drug interaction checking | Requires a licensed pharmacological database |
| Voice input for nurses | Hands-free event recording during procedures — needs ASR pipeline |
| Scheduled / recurring workflows | Rounds-based checklists triggered on a timer, not manually |
| Multi-tenant SaaS with billing | When expanding beyond a single hospital group to a product offering |
| Mobile native apps | After the React web client is stable and usage patterns are clear |
| Read replica / horizontal scaling | When concurrent users exceed ~100 and the 2 vCPU constraint binds |

---

## 2. Users and Consumers

### 2.1 Internal Users (clinical staff)

| Role | Who they are | What they need from the system |
|---|---|---|
| **Ward Staff** | Reception, orderlies, ward helpers | Admit and discharge patients, see bed occupancy |
| **Nurse** | Primary bedside caregiver | Record vitals and medication events, complete workflow steps, acknowledge escalation alerts |
| **Doctor** | Physician, registrar, consultant | Review patient event timeline, request AI summaries, resolve alerts, write doctor notes |
| **Hospital Admin** | IT manager, head of nursing | Manage workflow templates, escalation rules, user accounts within their hospital |
| **SUPERADMIN** | Platform operator | Cross-hospital access for support and onboarding |

**Key insight for design:** Nurses are the highest-frequency users. Every API endpoint that nurses hit (record event, complete step) must be low-latency and low-friction. The cost of a slow interface is a nurse skipping documentation.

### 2.2 External Consumers (future)

| Consumer | How they consume |
|---|---|
| HIS / EMR systems | REST webhooks or FHIR push from the integrations app |
| Mobile apps | Same REST + WebSocket API; JWT auth is mobile-friendly |
| Reporting / analytics tools | Read-only API or direct Postgres read replica |

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        External World                         │
│                                                              │
│   Web / Mobile clients          HIS / EMR systems           │
│   (Nurse station, Doctor app)   (HL7 / FHIR — future)       │
└───────────┬──────────────────────────────┬───────────────────┘
            │ HTTPS / WSS                  │ Webhooks / FHIR
            ▼                              ▼
┌───────────────────────────────────────────────────────────────┐
│                     172.16.232.103                            │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Nginx  (:80 / :443 TLS termination)                    │  │
│  └──────────────────────┬──────────────────────────────────┘  │
│                         │ HTTP + WS proxy → :8000             │
│  ┌──────────────────────▼──────────────────────────────────┐  │
│  │   gunicorn  (process manager)                           │  │
│  │   └── uvicorn workers  ×2  (ASGI: HTTP + WebSocket)     │  │
│  │        └── Django 5.1 application                       │  │
│  └──────────┬─────────────────────┬───────────────────────┘  │
│             │                     │                            │
│  ┌──────────▼──────┐  ┌──────────▼────────────────────────┐  │
│  │ PostgreSQL 15   │  │ Redis 7                            │  │
│  │ :5432           │  │ :6379                              │  │
│  │                 │  │  /0 — Channels layer (WebSocket)   │  │
│  │ Single source   │  │  /1 — Django cache                 │  │
│  │ of truth for    │  │  /2 — Celery broker + results      │  │
│  │ all domain data │  └──────────┬────────────────────────┘   │
│  └─────────────────┘             │                             │
│                         ┌────────▼─────────────────────────┐  │
│                         │ Celery workers ×2  (-A config)    │  │
│                         │ AI calls, rule eval, WS dispatch  │  │
│                         └──────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (Anthropic API) ← AI boundary
                         ▼
              ┌─────────────────────┐
              │  Anthropic Claude   │
              │  (claude-sonnet-*)  │
              │  external API only  │
              └─────────────────────┘
```

---

## 4. Application Layer Map

The Django application is divided into domain apps. The table below marks the **AI boundary** — which layers AI touches and which are entirely deterministic.

| App | Responsibility | AI Involved? |
|---|---|---|
| `core` | Base mixins, Hospital model, exception hierarchy, pagination | No |
| `users` | Authentication, JWT, role management | No |
| `patients` | Patient records, ward/bed management, admissions | No |
| `workflows` | Structured checklist templates and running instances | No |
| `events` | Append-only clinical event log | No — but **feeds AI context** |
| `escalations` | Deterministic rule engine that fires alerts from events | **No — intentionally not AI** |
| `intelligence` | Claude API integration — summaries, risk flags, drug checks | **Yes — only layer** |
| `communications` | WebSocket push, persistent notifications | No |
| `integrations` | External system connectors (HL7/FHIR) | No |

### Why escalations are deterministic and not AI-driven

The escalation engine evaluates simple rules (e.g. "SpO₂ < 90% → CRITICAL alert"). These rules are configured by hospital admins and evaluated deterministically against event payloads. We deliberately chose rules over ML here:

- A rule either fires or it does not — the outcome is auditable and explainable
- A wrong rule can be corrected in minutes; a wrong model requires retraining
- Clinical staff need to trust that an alert fired for a specific, known reason
- Rules have zero false positives if written correctly; an ML model cannot make that guarantee in V1

---

## 5. AI Safety in a Healthcare Context

Healthcare is a domain where a false positive or false negative can directly harm a patient. This is not a hypothetical risk — it is the central constraint that shaped every AI-related design decision.

### 5.1 What the AI does

The `intelligence` app uses Claude to:
- Summarise a patient's last N events into a readable narrative for a doctor
- Flag patterns that may warrant attention (e.g. gradually rising temperature over 6 hours)
- Check a medication list for potential interactions (using Claude's knowledge, not a pharmacological DB)
- Suggest a next action given the patient's clinical picture

### 5.2 What the AI is structurally prevented from doing

| Prohibited action | How it's enforced |
|---|---|
| Writing to patient records | The `intelligence` app has read access to events; it has no write path to `patients`, `admissions`, or `events` tables |
| Triggering workflow steps | Workflow step completion requires an authenticated human user; there is no service call from intelligence to workflows |
| Acknowledging or resolving escalation alerts | Alert state changes require an authenticated user action; no Celery task can do this |
| Sending notifications autonomously | The push goes from the Celery task to the WebSocket group, but only after a human-triggered query completes |
| Making diagnoses | System prompts explicitly instruct Claude to frame outputs as observations and suggestions, never diagnoses |

### 5.3 Human-in-the-loop by design

Every AI-generated output:
1. Is stored as an `IntelligenceRequest` record with the full prompt context, response text, token count, and latency
2. Is surfaced to the user clearly labelled as AI-generated
3. Requires an explicit clinical action from a doctor or nurse before it has any effect on the patient record
4. Can be re-queried if the clinician disagrees — the system makes no assumption that the AI was correct

### 5.4 Grounded prompts reduce hallucination risk

AI prompts are built from structured, factual data already in the database (event payloads, admission timestamps, recorded vitals). We do not ask Claude to infer things not in the data. The prompt structure is:

```
"Here are the last N clinical events for this patient, in chronological order: [structured data].
Summarise what has happened and flag anything that warrants clinical attention.
Do not diagnose. Frame all observations as things that may warrant clinician review."
```

This bounds Claude's output to what the data contains, dramatically reducing the space for hallucination.

---

## 6. Technical Complexity

### 6.1 Hospital scoping as a hard invariant

Every queryset in every service must be scoped to `user.hospital`. A bug in any one of them leaks another hospital's patient data (PHI). This is enforced:

- In the service layer: every `get_*_queryset()` function applies the hospital filter
- In tests: every view test has a negative test asserting that data from another hospital returns 0 results or 404
- SUPERADMIN is the only role that bypasses this, and only intentionally

### 6.2 PII encryption complicates search

Patient first name, last name, phone, and emergency contact phone are stored as `EncryptedCharField` (AES-256, Fernet). This makes substring search on those fields impossible at the database level. We work around this by:

- Keeping MRN unencrypted (it's a non-personally-identifying hospital reference number) as the primary search key
- Patient name search is deferred to a later phase (requires either client-side decryption + search or a separate search index)

### 6.3 Append-only event log as the source of truth for AI

The `clinical_events` table is the input to every AI query and every escalation rule evaluation. It must be:

- Truly append-only: no UPDATE or DELETE exposed via API
- Indexed on `recorded_at` for timeline queries
- Rich enough in payload structure that rules can evaluate it without ambiguity

This also means the events table will be the largest and fastest-growing table in the system.

### 6.4 Real-time fan-out at scale

When an escalation alert fires, a WebSocket message must be pushed to every online user in the hospital's group. Django Channels handles this via Redis pub/sub (DB 0). The challenge is:

- A hospital may have many staff online simultaneously
- Each `channel_layer.group_send()` call fans out to all group members
- Redis must not become a bottleneck; the current single-instance setup handles ~100 concurrent connections comfortably

### 6.5 AI call latency is unpredictable

Claude API calls can take 2–15 seconds depending on context length and load. Making an AI call synchronously in a request handler would hold a uvicorn worker for that entire time, blocking other requests. Solution: every AI query is dispatched as a Celery task; the HTTP endpoint returns `202 Accepted` immediately with a request ID, and the client polls or waits for a WebSocket push.

---

## 7. Data Flow

### 7.1 Standard HTTP request

```
Client → Nginx → uvicorn → Django middleware stack
       → Router → View → Serializer (validate input)
       → Service (business logic, hospital scoping)
       → ORM → PostgreSQL
       → Response ← Serializer (render output)
```

### 7.2 AI query (async, non-blocking)

```
Client POST /api/v1/intelligence/query/
  → View validates request, creates IntelligenceRequest (status=PENDING)
  → HTTP 202 Accepted returned immediately (request_id in body)
  → Celery task enqueued (Redis DB 2)
  → Celery worker picks up task
  → Builds prompt from patient events (PostgreSQL read)
  → anthropic.messages.create() → Claude API (2–15 s)
  → Updates IntelligenceRequest (status=COMPLETED, response_text, tokens_used)
  → Pushes WebSocket notification to requesting user (Redis DB 0)
  → Client receives push; fetches result from GET /intelligence/<id>/
```

### 7.3 Escalation alert (deterministic, synchronous in Celery)

```
POST /api/v1/events/ → ClinicalEvent saved to PostgreSQL
  → record_event() enqueues evaluate_escalation_rules.delay(admission_id)
  → Celery: loads active EscalationRules for the hospital
  → Evaluates rule conditions against latest event payload (JSON DSL)
  → Matching rule → EscalationAlert created (status=OPEN)
  → group_send() to hospital WebSocket group (Redis DB 0)
  → All online staff in the hospital see the alert in real time
```

### 7.4 WebSocket connection lifecycle

```
Client → wss://host/ws/notifications/?token=<JWT>
  → Django Channels ASGI handler
  → NotificationConsumer.connect()
  → JWT validated from query param (before join)
  → Consumer joins f"hospital_{user.hospital_id}" channel group
  → Stays open; receives server-push messages as JSON
  → On disconnect: leaves group, connection freed
```

---

## 8. Authentication and Authorisation

- **Mechanism**: JWT via `djangorestframework-simplejwt`
- **Access token lifetime**: 8 hours (balances security against nurse shift length)
- **Refresh token lifetime**: 7 days, rotated on each use, blacklisted after rotation (prevents replay)
- **WebSocket auth**: JWT passed as `?token=` query param; validated in `connect()` before joining any group — unauthenticated connections are closed with code 4001

### Role hierarchy

```
SUPERADMIN > ADMIN > DOCTOR > NURSE > WARD_STAFF
```

Permissions are additive upward: a DOCTOR can do everything a NURSE can, plus more. Role enforcement is per-view via DRF permission classes. Hospital scoping is enforced at the queryset level in each service — not in the view.

---

## 9. Security Considerations

| Concern | Mitigation |
|---|---|
| PHI at rest | `EncryptedCharField` (AES-256 Fernet) on patient name and phone fields |
| Auth token theft | Short-lived access tokens (8 h); refresh token rotation + blacklist on every use |
| SQL injection | Django ORM parameterised queries throughout; no raw SQL |
| Mass assignment | Serializers with explicit `fields` lists; write operations go through the service layer |
| Cross-hospital data leak | Hospital scoping enforced in every queryset; tested with negative tests per endpoint |
| HTTPS | TLS termination at Nginx (pending Let's Encrypt setup) |
| Host validation | `ALLOWED_HOSTS` enforced by Django |
| Secret management | `.env` on server, not in version control; `.gitignore` covers `.env*` patterns |
| AI prompt injection | Prompts are built from structured DB data, not from user-provided free text |

---

## 10. Non-Functional Requirements

| Attribute | Target | Notes |
|---|---|---|
| Latency (p95, non-AI) | < 200 ms | AI queries are async — latency is the Celery task time, not the HTTP response |
| Throughput | ~50 concurrent users | 2 vCPU / 3.6 GB RAM; comfortable headroom at this scale |
| Availability | Best-effort (single VM) | No HA in V1; add a replica + load balancer to improve |
| Data durability | PostgreSQL + R1Soft VM snapshots (E2E infra) | No application-level backup yet |
| Scalability path | Increase `--workers` as vCPUs grow; Postgres read replica for AI context queries; Redis Sentinel for HA |

---

## 11. Technology Choices and Rationale

| Decision | Choice | Why this over the alternative |
|---|---|---|
| Language | Python 3.11 | Ecosystem fit for AI/ML libs; Anthropic SDK is Python-first |
| Framework | Django 5.1 + DRF | ORM, admin, auth, migrations, and REST framework in one — FastAPI gives us none of that out of the box |
| ASGI server | uvicorn + gunicorn | uvicorn handles WebSocket natively; gunicorn manages worker processes and graceful restarts |
| Database | PostgreSQL 15 | JSONB for event payloads; strong referential integrity; proven at scale |
| Cache / broker | Redis 7 | Single dependency covers Celery broker, Django cache, and Channels layer — avoids RabbitMQ |
| Real-time | Django Channels 4 | Native Django integration; no separate WS microservice needed |
| Task queue | Celery 5 | Mature, auto-discovers tasks from installed apps; retry policies are built in |
| AI | Anthropic Claude API | No GPU required; strong clinical text reasoning; context-window size handles multi-day event logs |
| PII encryption | `django-encrypted-model-fields` | Field-level Fernet encryption; transparent to ORM queries on non-PII fields |
| Auth | JWT (simplejwt) | Stateless; mobile-friendly; blacklist support for logout; no server-side session storage |
