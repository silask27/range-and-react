# Staging Checklist

## Before sharing a staging/demo URL
- Set a real support email
- Set legal company name and effective date
- Set correct frontend/backend URLs
- Enable demo mode only if you want demo credentials or seeded demo accounts
- Seed demo data with `make demo-seed`
- Run smoke checks with `make smoke-test`
- Run regression coverage with `make test-api`

## Verify manually
- `/status` shows the correct environment and readiness state
- owner, coach, and member logins work
- invite-only signup flow works from an emailed or copied invite link
- forgot-password and reset-password flows work
- dashboard loads recent sessions/hands/results
- assignments page loads and quick-start links open the trainer
- admin page loads analytics, organizations, and audit logs
- results page and at least one hand debrief load successfully

## Before real production launch
- disable public demo credentials
- move from SQLite to managed Postgres
- put API and web behind real domains and HTTPS
- set legal company name, effective date, jurisdiction, and real support email
- keep detailed runtime checks hidden from the public status page
- configure real error monitoring and backups
- run `make launch-gate` and confirm it passes
- run `make preflight` and confirm `/readyz` has no required errors
