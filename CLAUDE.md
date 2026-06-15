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
python3.11     # compiled from source at /usr/local/bin/python3.11
postgresql15   # running, DB: hospital_copilot
redis          # running on 127.0.0.1:6379
gunicorn       # process manager for uvicorn workers
```

### Still to install

```
nginx          # reverse proxy / TLS — not yet configured
```

## Stack Layout

```
Internet
   │
  Nginx :443 (TLS) / :80 (redirect)
   │
  uvicorn :8000  ← Django ASGI (HTTP + WebSocket)
   │
  ┌─────────────┬──────────────┐
  │             │              │
PostgreSQL    Redis         Celery workers
  :5432        :6379
```

## Port Plan

| Port | Service |
|------|---------|
| 22 | SSH |
| 80 | Nginx (redirect to 443) |
| 443 | Nginx (TLS, proxies to uvicorn) |
| 8000 | uvicorn (internal only, not exposed) |
| 5432 | PostgreSQL (localhost only) |
| 6379 | Redis (localhost only) |

## Environment Variables Required

```
SECRET_KEY=
DATABASE_URL=postgres://hospital:PASSWORD@localhost:5432/hospital_copilot
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=
DEBUG=False
ALLOWED_HOSTS=172.16.232.103
LOG_LEVEL=INFO
```

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.1 + DRF |
| ASGI server | uvicorn (via `gunicorn -k uvicorn.workers.UvicornWorker`) |
| Auth | JWT (simplejwt) with token blacklist |
| WebSocket | Django Channels 4 over Redis |
| Task queue | Celery 5 + Redis |
| AI | Anthropic API (Claude) — external call only |
| Database | PostgreSQL 15 |
| Cache | Redis |
| Reverse proxy | Nginx |

## Repository Layout

```
hospital-copilot/
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
└── TODO.md            # implementation plan — keep updated
```

## Deployment

The server is **fully set up** as of 2026-06-15. To deploy a new version:

```bash
# On the server
cd /opt/hospital-copilot
git pull
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py migrate
systemctl restart hospital-copilot hospital-copilot-celery
```

### Systemd services

| Service | Command |
|---------|---------|
| `hospital-copilot` | gunicorn + uvicorn workers, port 8000 |
| `hospital-copilot-celery` | celery -A config worker, 2 threads |
| `postgresql-15` | managed by PGDG init |
| `redis` | managed by Remi init |

All four services auto-start on boot. Logs: `/var/log/hospital-copilot/`.

### Python build notes

Python 3.11.9 was compiled from source (CentOS 7 has no pre-built 3.11).
- OpenSSL 1.1.1k via `openssl11-devel` from EPEL, symlinked to `/usr/local/ssl11/`
- Installed to `/usr/local/bin/python3.11`
- Source left in `/tmp/Python-3.11.9` (can be removed to reclaim ~200 MB)

### Superuser

Username `admin`, password `changeme123!` — **change this immediately** via:
```bash
ssh root@172.16.232.103
cd /opt/hospital-copilot
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py changepassword admin
```

## Implementation Rule

**After every implementation session, `TODO.md` must be updated:**
- Mark completed items with `[x]`
- Remove or correct anything that is no longer accurate
- Add newly discovered tasks or blockers
- The file lives at the repo root: `TODO.md`

## Running Tests (local)

```bash
.venv/bin/python -m pytest apps/ -v
```

Tests use in-memory SQLite and `--no-migrations` (syncdb). All 85 tests pass as of 2026-06-15.

## Celery

App is defined in `config/celery.py`, exposed via `config/__init__.py`.
Invoke as `celery -A config worker` — **not** `-A celery` (that circular-imports the root module).
