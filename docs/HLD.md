# Hospital Copilot — High Level Design

## 1. Purpose

Hospital Copilot is a clinical operations platform for hospital staff. It centralises patient admission tracking, structured clinical workflows, a real-time event log, and AI-assisted decision support (powered by Claude) into a single API-first system. The intended users are ward staff, nurses, doctors, and hospital administrators operating through web or mobile frontends.

---

## 2. System Context

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
│  │  Nginx  (:80 → :443 redirect,  :443 TLS termination)    │  │
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
│  │ :5432 (local)   │  │ :6379 (local)                      │  │
│  │                 │  │  /0 — Channels layer               │  │
│  │ Primary store   │  │  /1 — Django cache                 │  │
│  │ for all domain  │  │  /2 — Celery broker + results      │  │
│  │ data            │  └──────────┬────────────────────────┘   │
│  └─────────────────┘             │                             │
│                         ┌────────▼─────────────────────────┐  │
│                         │ Celery workers ×2  (-A config)    │  │
│                         │ Async: AI calls, rule eval,       │  │
│                         │ notification dispatch             │  │
│                         └──────────────────────────────────┘  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (Anthropic API)
                         ▼
              ┌─────────────────────┐
              │  Anthropic Claude   │
              │  (claude-sonnet-*)  │
              │  external API only  │
              └─────────────────────┘
```

---

## 3. Component Responsibilities

### 3.1 Nginx (not yet installed)
- TLS termination; forwards plain HTTP to uvicorn on `:8000`
- WebSocket upgrade passthrough (`Upgrade: websocket`)
- Serves static files directly (Django `collectstatic` output)
- Rate limiting at the edge

### 3.2 gunicorn + uvicorn workers
- `gunicorn -k uvicorn.workers.UvicornWorker` — combines gunicorn's process management with uvicorn's ASGI runtime
- 2 workers (constrained by 2 vCPUs); each handles both HTTP and WebSocket connections
- Graceful restart on `SIGHUP`; logs to `/var/log/hospital-copilot/`

### 3.3 Django application
The application is split into domain apps. Each app owns its own models, serializers, services, and URL routes.

| App | Responsibility |
|-----|---------------|
| `core` | Shared base (mixins, Hospital model, exception hierarchy, pagination) |
| `users` | Authentication, user profiles, role management |
| `patients` | Patient records, ward/bed management, admissions |
| `workflows` | Clinical checklist templates and running instances |
| `events` | Append-only clinical event log per admission |
| `escalations` | Rule engine that fires alerts from events |
| `intelligence` | Claude API integration — summaries, risk flags, drug checks |
| `communications` | WebSocket push to connected clients; persistent notifications |
| `integrations` | External system connectors (HL7/FHIR — design TBD) |

### 3.4 PostgreSQL 15
Single primary database. All domain data lives here. No read replicas at this scale. Connection pooling is handled at the Django level (`CONN_MAX_AGE` — to be configured).

### 3.5 Redis 7
Three logical databases on one instance:
- **DB 0** — Django Channels layer (WebSocket group messaging)
- **DB 1** — Django cache (session data, cached querysets)
- **DB 2** — Celery broker and result backend

### 3.6 Celery workers
Handle tasks that must not block the HTTP request cycle:
- Anthropic API calls (can take 2–15 s)
- Escalation rule evaluation after a batch of events
- WebSocket push fan-out to large hospital groups
- Future: HL7 message processing, scheduled reports

### 3.7 Anthropic Claude (external)
Called only from the `intelligence` app via the `anthropic` Python SDK. No local model. No GPU required on the VM. API key stored in `.env` as `ANTHROPIC_API_KEY`.

---

## 4. Data Flow

### 4.1 Standard HTTP request
```
Client → Nginx → uvicorn → Django middleware stack
       → Router → View → Serializer (validate)
       → Service (business logic) → ORM → PostgreSQL
       → Response ← Serializer (render)
```

### 4.2 AI query (async)
```
Client POST /api/v1/intelligence/query/
  → Django view validates request
  → Celery task enqueued (Redis /2)
  → HTTP 202 Accepted returned immediately
  → Celery worker picks up task
  → Builds context from patient events (PostgreSQL read)
  → anthropic.messages.create() → Claude API
  → Saves IntelligenceRequest record with response + tokens
  → Dispatches WebSocket notification to requesting user
```

### 4.3 Real-time escalation alert
```
New ClinicalEvent saved
  → post_save signal → evaluate_escalation_rules() task (Celery)
  → Celery: queries EscalationRules for the hospital
  → Matching rule found → EscalationAlert created
  → Channel group message pushed to all online staff
     in the hospital's WebSocket group (Redis /0)
  → Connected clients receive JSON push without polling
```

### 4.4 WebSocket connection
```
Client connects to wss://host/ws/notifications/?token=<JWT>
  → Django Channels ASGI handler
  → NotificationConsumer.connect()
  → JWT validated from query param
  → Consumer joins hospital-scoped channel group
  → Stays open; receives server-push messages
```

---

## 5. Authentication & Authorisation

- **Mechanism**: JWT via `djangorestframework-simplejwt`
- **Token lifetime**: access 8 h, refresh 7 d
- **Rotation**: refresh tokens are rotated and blacklisted on each use (prevents replay)
- **WebSocket auth**: JWT passed as `?token=` query param on connect; validated in `connect()` before joining any group

### Role hierarchy

| Role | Typical user | Key permissions |
|------|-------------|-----------------|
| `SUPERADMIN` | Platform operator | Full access across all hospitals |
| `ADMIN` | Hospital IT / admin | Full access within their hospital |
| `DOCTOR` | Physician | Read all, write notes/events, request AI |
| `NURSE` | Ward nurse | Read all, record events, complete workflow steps |
| `WARD_STAFF` | Reception, orderly | Read patient list, admit/discharge |

Role enforcement is implemented per-view using DRF permission classes. Hospital scoping (a user can only see their own hospital's data) is enforced at the queryset level in each service.

---

## 6. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| PII at rest | `django-encrypted-model-fields` on Patient name and phone fields |
| Auth token theft | Short-lived access tokens (8 h); refresh rotation + blacklist |
| SQL injection | Django ORM parameterised queries throughout |
| Mass assignment | Serializers with explicit `fields` lists; write operations via service layer |
| HTTPS | TLS termination at Nginx (pending) |
| Host validation | `ALLOWED_HOSTS` enforced by Django |
| Secrets | `.env` file on server, not in version control; `.gitignore` covers `.env*` |
| Admin password | Default `changeme123!` — must be rotated before external traffic |

---

## 7. Non-Functional Requirements

| Attribute | Target | Notes |
|-----------|--------|-------|
| Latency (p95) | < 200 ms | For non-AI endpoints; AI queries are async |
| Throughput | ~50 concurrent users | 2 vCPU / 3.6 GB RAM is the constraint |
| Availability | Best-effort (single VM, no HA) | Add a replica / load balancer to improve |
| Data durability | Delegated to PostgreSQL + R1Soft VM snapshots | No application-level backup yet |
| Scalability path | Add vCPUs → increase `--workers`; add Postgres replica → use `DATABASE_REPLICA_URL` | |

---

## 8. Technology Choices

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.11 | Ecosystem fit for AI/ML libs; team familiarity |
| Framework | Django 5.1 + DRF | Batteries-included ORM, admin, auth; DRF for REST |
| ASGI server | uvicorn + gunicorn | uvicorn for async/WS performance; gunicorn for process management |
| Database | PostgreSQL 15 | JSONB for dynamic payloads, strong referential integrity |
| Cache / broker | Redis 7 | Single dependency for cache, Celery, and Channels |
| Real-time | Django Channels 4 | Native Django integration; Redis channel layer |
| Task queue | Celery 5 | Mature, battle-tested; auto-discovers tasks from installed apps |
| AI | Anthropic Claude API | No GPU needed; strong clinical text reasoning |
| PII encryption | `django-encrypted-model-fields` | Field-level symmetric encryption; transparent to ORM |
| Auth | JWT (simplejwt) | Stateless; mobile-friendly; token blacklist for logout |

---

## 9. Deployment Architecture

```
/opt/hospital-copilot/          Application root
├── .venv/                      Python 3.11 virtualenv
├── .env                        Secrets (not in git)
├── staticfiles/                collectstatic output (served by Nginx)
└── ...

/var/log/hospital-copilot/      Application logs
├── access.log                  Gunicorn access log
├── error.log                   Gunicorn error log
└── celery.log                  Celery worker log

Systemd units:
  hospital-copilot              gunicorn ASGI server
  hospital-copilot-celery       Celery worker
  postgresql-15                 Database
  redis                         Cache / broker
```

Deploy workflow:
```bash
ssh root@172.16.232.103
cd /opt/hospital-copilot
git pull
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py migrate
systemctl restart hospital-copilot hospital-copilot-celery
```
