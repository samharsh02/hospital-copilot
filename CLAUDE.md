# Hospital Copilot — Project Reference

## Server

| Item | Value |
|------|-------|
| IP | `172.16.232.103` |
| Access | `ssh root@172.16.232.103` |
| OS | CentOS 7 |
| CPUs | 2 vCPUs (QEMU) |
| RAM | 3.6 GB + 2 GB swap |
| Disk | 20 GB (`/dev/sda1`, ext4) |

This server hosts **everything** for the project:

- Django API server (uvicorn + ASGI)
- PostgreSQL database
- Redis (Celery broker, result backend, cache, Django Channels layer)
- Celery workers
- Nginx (reverse proxy, TLS termination)

**LLM calls are external only** — no local model inference. The app calls the Anthropic API directly (`ANTHROPIC_API_KEY`). If a self-hosted inference endpoint is added later (e.g., vLLM), it will live on a separate GPU node.

## Spec Assessment

The 2 vCPU / 3.6 GB setup is **sufficient for development and light production use** (< ~50 concurrent users). Memory budget at steady state:

| Service | Est. RAM |
|---------|----------|
| OS + system | ~250 MB |
| PostgreSQL | ~200 MB |
| Redis | ~80 MB |
| uvicorn (2 workers) | ~350 MB |
| Celery (2 workers) | ~350 MB |
| **Total** | **~1.2 GB** |

That leaves ~2 GB headroom before touching swap — comfortable. Disk at 20 GB is fine for a DB under ~10 GB of records. For higher load or a larger dataset, request a resize (more RAM first, then vCPUs).

## Services on This Server

### Infrastructure services (do not touch)

| Service | Why kept |
|---------|----------|
| `zabbix-agent` | E2E Networks infra monitoring — reports to `172.16.232.231`. Required by the cloud provider for SLA visibility. |
| `sbm-agent` (R1Soft CDP) | Continuous backup agent managed by E2E. Removing it disables point-in-time recovery for the VM. |
| `qemu-guest-agent` | Required by the hypervisor for snapshot/live-migration support. |
| `sshd`, `chronyd`, `crond`, `rsyslog`, `auditd` | Standard OS services. |

### Removed (cleanup done 2026-06-15)

| Removed | Reason |
|---------|--------|
| `haproxy` | Was already failed at boot (config pointed to `1.1.1.1:80` — a placeholder). Not part of our stack. |
| `haproxy_exporter` | Prometheus exporter for haproxy; pointless without haproxy. |

### Installed

```
docker-ce 26.1.4          # container runtime
docker-compose-plugin     # v2.27.1 — invoked as 'docker compose'
python3.11                # compiled from source (no longer used — superseded by Docker image)
postgresql15              # host install (superseded by Docker volume)
redis                     # host install (superseded by Docker container)
```

## Stack Layout (Docker)

```
Internet
   │
  nginx container :80 (→ 443 after TLS)
   ├── /api/*  /ws/*  /admin/*  /static/* → api container :8000
   └── /*                                 → frontend container :80
         │
  ┌──────┴───────────┬──────────────────────┐
  │                  │                      │
api container     celery container       frontend container
(django/uvicorn)  (celery -A config)     (nginx → React SPA)
  │                  │
  └──────┬───────────┘
         │
  ┌──────┴──────────────────┐
  │                         │
db container              redis container
postgres:15               redis:7
(volume: postgres_data)   (volume: redis_data)
```

## Port Plan

| Port | Service |
|------|---------|
| 22 | SSH (host) |
| 80 | nginx container (external) |
| 443 | nginx container (TLS — not yet configured) |
| 8000 | api container (internal Docker network only) |
| 5432 | db container (internal Docker network only) |
| 6379 | redis container (internal Docker network only) |

## Environment Variables (docker-compose)

The `.env` file in `/opt/hospital-copilot/` is read by both Docker Compose (for `${VAR}` substitution in the YAML) and injected into containers via `env_file: .env`. `DATABASE_URL` and `REDIS_URL` are set by the `environment:` block in `docker-compose.yml` and override anything in `.env`.

```
SECRET_KEY=
DB_PASSWORD=               # used by compose to build DATABASE_URL (host = 'db')
ANTHROPIC_API_KEY=
DEBUG=False
ALLOWED_HOSTS=172.16.232.103,localhost
LOG_LEVEL=INFO
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
```

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Container runtime | Docker + docker-compose v2 |
| Framework | Django 5.1 + DRF |
| ASGI server | uvicorn (via `gunicorn -k uvicorn.workers.UvicornWorker`) |
| Auth | JWT (simplejwt) with token blacklist |
| WebSocket | Django Channels 4 over Redis |
| Task queue | Celery 5 + Redis |
| AI | Anthropic API (Claude) — external call only |
| Database | PostgreSQL 15 (Docker volume) |
| Cache | Redis 7 (Docker container) |
| Reverse proxy | Nginx (Docker container, routes API + WS + static) |
| Frontend | React 18 + Vite 6 + TypeScript (separate repo) |

## Repository Layout

Backend: `https://github.com/samharsh02/hospital-copilot.git`
Frontend: `https://github.com/samharsh02/hospital-copilot-ui.git`

```
hospital-copilot/              ← backend repo (this one)
├── apps/
│   ├── core/          # BaseMixin, SoftDeleteMixin, Hospital, exceptions, helpers — DONE
│   ├── users/         # User model, JWT auth endpoints (register/login/logout/me) — DONE
│   ├── patients/      # Patient domain — TODO
│   ├── workflows/     # Clinical workflows — TODO
│   ├── events/        # Clinical events — TODO
│   ├── escalations/   # Escalation rules — TODO
│   ├── intelligence/  # Claude-powered suggestions — TODO
│   ├── integrations/  # External system connectors — TODO
│   └── communications/# WebSocket / notifications — TODO
├── config/
│   ├── settings/      # base / development / test / production
│   ├── celery.py      # Celery app (invoke as: celery -A config worker)
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── nginx/
│   └── nginx.conf     # nginx routing config for Docker container
├── docs/
│   ├── TODO.md        # implementation plan — keep updated
│   ├── HLD.md         # High Level Design
│   └── LLD.md         # Low Level Design
├── Dockerfile         # backend image (python:3.11-slim)
├── docker-compose.yml # full stack: db, redis, api, celery, frontend, nginx
├── entrypoint.sh      # migrate + start server
├── .env.docker.example# template for docker-compose .env
└── CLAUDE.md          # Claude Code config — must stay at root

frontend/                      ← separate git repo (gitignored here)
├── src/
│   ├── api/           # fetch client + auth API calls
│   ├── store/         # auth store (localStorage JWT)
│   ├── hooks/         # useAuth
│   ├── pages/         # LoginPage, DashboardPage
│   └── types/         # TypeScript interfaces
├── Dockerfile         # multi-stage: node:20 build → nginx:alpine serve
├── nginx.conf         # SPA routing (try_files → index.html)
└── .env.example       # VITE_API_BASE_URL
```

## Deployment

Stack runs via Docker Compose. On the server, repos are at:
- Backend: `/opt/hospital-copilot/`
- Frontend: `/opt/hospital-copilot/frontend/` (cloned inside backend dir)

### First-time setup
```bash
ssh root@172.16.232.103
cd /opt/hospital-copilot
cp .env.docker.example .env   # then fill in SECRET_KEY, DB_PASSWORD
docker compose up -d --build
docker compose exec api python manage.py createsuperuser
```

### Deploy a new backend version
```bash
cd /opt/hospital-copilot
git pull
docker compose build api celery
docker compose up -d --no-deps api celery
```

### Deploy a new frontend version
```bash
cd /opt/hospital-copilot/frontend
git pull
cd ..
docker compose build frontend
docker compose up -d --no-deps frontend
```

### Useful commands
```bash
docker compose ps                            # service status
docker compose logs -f api                   # tail API logs
docker compose exec api python manage.py migrate          # run migrations manually
docker compose exec api python manage.py createsuperuser  # create admin user
docker compose exec db psql -U hospital hospital_copilot  # DB shell
docker compose down                          # stop all containers
docker compose down -v                       # stop + delete volumes (destroys DB!)
```

### Superuser

Username `admin`, password `changeme123!` — **change this immediately** via:
```bash
docker compose exec api python manage.py changepassword admin
```

## Docs

All project documentation lives in `docs/`. Key files:

| File | Purpose |
|------|---------|
| `docs/TODO.md` | Implementation plan — what's done, what's next, what's blocked |
| `docs/HLD.md` | High Level Design — architecture, components, data flow, tech choices |
| `docs/LLD.md` | Low Level Design — database schema, API spec, service contracts, permission matrix |

> `CLAUDE.md` (this file) stays at the project root — Claude Code only auto-loads it from there. All other docs go in `docs/`.

## Implementation Rule

**After every implementation session, `docs/TODO.md` must be updated:**
- Mark completed items with `[x]`
- Remove or correct anything that is no longer accurate
- Add newly discovered tasks or blockers

## Running Tests (local)

```bash
.venv/bin/python -m pytest apps/ -v
```

Tests use in-memory SQLite and `--no-migrations` (syncdb). All 85 tests pass as of 2026-06-15.

## Celery

App is defined in `config/celery.py`, exposed via `config/__init__.py`.
Invoke as `celery -A config worker` — **not** `-A celery` (that circular-imports the root module).
