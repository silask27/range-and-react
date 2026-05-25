# Range & React

Range & React is a full-stack poker training platform for building a repeatable live-poker thought process around:
- tracking villain range street by street
- pruning without incorrectly removing the true hand
- predicting likely villain responses by bucket
- reviewing scored debriefs and assignment progress over time

This snapshot includes:
- standalone user accounts with roles
- persistent session/hand storage
- results scoring and debriefs
- assignments and coach/admin workflows
- audit logging, account lifecycle controls, and coach analytics
- organization + external-member scaffolding for future white-label/member-sync use
- launch-hardening basics such as status pages, environment config, and deployment scaffolding
- demo-mode seeding for a pitch-ready staging environment

## Stack
- Frontend: Next.js
- Backend: FastAPI
- Database: SQLite by default, or PostgreSQL via `VRT_DATABASE_URL`

## Quick start

### Backend (SQLite fallback)
```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.app.main:app --reload --port 8000
```

### Backend (PostgreSQL)
Set `VRT_DATABASE_URL` before starting the API, for example:
```bash
export VRT_DATABASE_URL=postgresql://range_and_react:range_and_react@127.0.0.1:5432/range_and_react
uvicorn api.app.main:app --reload --port 8000
```

### Frontend
```bash
cd web
npm install
npm run dev
```

Frontend default URL: `http://127.0.0.1:3000`

Backend default URL: `http://127.0.0.1:8000`

## Make targets
From the repo root:

```bash
make api-install
make web-install
make demo-seed
make smoke-test
make test-api
make launch-gate
make docker-up
```

## Demo/staging flow
To create a pitch-ready local environment:

```bash
cp api/.env.example api/.env
cp web/.env.local.example web/.env.local
make demo-seed
```

Then log in with the seeded demo accounts shown on `/login` when demo mode is enabled.

### Demo credentials behavior
The login page only exposes demo credentials when **both** of these are true:
- `VRT_DEMO_MODE_ENABLED=true`
- `VRT_DEMO_PUBLIC_CREDENTIALS=true`

That keeps the feature generic for white-label/pitch environments without hardcoding the app to any one coaching business.

## Demo docs
- `docs/demo-walkthrough.md`
- `docs/staging-checklist.md`
- `docs/operations-runbook.md`

## Environment files
Copy the examples before running in a real environment.

- `api/.env.example`
- `web/.env.local.example`

## Email delivery (Resend)
Password reset, invite delivery, and welcome emails use Resend when these backend env vars are set:

```bash
VRT_EMAIL_PROVIDER=resend
VRT_RESEND_API_KEY=re_xxxxx
VRT_EMAIL_FROM=Range & React <noreply@yourdomain.com>
VRT_EMAIL_REPLY_TO=support@yourdomain.com
VRT_WELCOME_EMAIL_ENABLED=true
```

Without those values, the API still works, but email delivery is skipped and invite creation falls back to copyable invite links in the coach/admin UI. In production, also set:

```bash
VRT_PASSWORD_RESET_RETURNS_TOKEN=false
VRT_ADMIN_ANALYTICS_CACHE_TTL_SECONDS=300
VRT_DASHBOARD_OVERVIEW_CACHE_TTL_SECONDS=120
```

The admin analytics and member dashboard now use short-lived cached snapshots backed by the database, so larger coach/member pools do not recompute every overview from scratch on each request.

## SQLite → PostgreSQL migration
If you already have local data in SQLite, bootstrap PostgreSQL first and then run:

```bash
PYTHONPATH=. .venv/bin/python -m api.scripts.migrate_sqlite_to_postgres \
  --source-path ./data/villain_range_trainer.db \
  --target-url postgresql://range_and_react:range_and_react@127.0.0.1:5432/range_and_react \
  --reset-target
```

The script creates the target schema, optionally clears the target tables, and copies application records table-by-table.

## Deployment scaffolding
This snapshot includes:
- `api/Dockerfile`
- `web/Dockerfile`
- `docker-compose.yml`
- `docker-compose.demo.yml`

These are a starting point for staging or demo deployment. Harden secrets, domains, and storage paths before production launch.

## Launch notes
Before public launch, replace placeholder values for:
- support email
- privacy and terms content
- brand name / white-label text
- production URLs and allowed origins
- durable production database configuration (`VRT_DATABASE_URL`, pool sizing, backups)
- production email delivery (`VRT_EMAIL_PROVIDER`, `VRT_RESEND_API_KEY`, `VRT_EMAIL_FROM`)
- `VRT_PASSWORD_RESET_RETURNS_TOKEN=false` in production
- public demo credentials settings


## Ops and reliability hardening
This snapshot now includes:
- runtime preflight checks via `make preflight`
- optional Sentry integration (`VRT_SENTRY_DSN`)
- security headers and trusted-host support
- Docker health checks for the API
- fail-fast startup validation when `VRT_STRICT_STARTUP_CHECKS=true`

Use `docs/operations-runbook.md` as the deployment/backup/rollback reference.

## Final launch gate
Run this before shipping a new staging or production build:

```bash
make launch-gate
```

That runs the API smoke test, the targeted regression suite, and the runtime preflight in one pass.
