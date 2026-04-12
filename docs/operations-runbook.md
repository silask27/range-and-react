# Operations Runbook

## Runtime preflight
Run this before a staging or production deploy:

```bash
make preflight
```

The preflight checks validate:
- database connectivity
- predictive model artifact/runtime compatibility
- email configuration consistency
- legal/support metadata completeness
- production environment safety checks such as docs/debug exposure, localhost URLs, and invite-only mode

In production, `VRT_STRICT_STARTUP_CHECKS=true` will fail app startup if required checks fail.

## Regression coverage
Run the focused regression suite before shipping backend changes:

```bash
make test-api
```

This suite covers:
- invite-only signup lock-down
- role escalation blocking
- coach organization scoping
- out-of-scope assignment blocking
- authenticated runtime-check access

## Recommended production environment variables
Backend:

```bash
VRT_APP_ENV=production
VRT_DATABASE_URL=postgresql://...
VRT_FRONTEND_URL=https://app.yourdomain.com
ALLOWED_ORIGINS=https://app.yourdomain.com
VRT_TRUSTED_HOSTS=api.yourdomain.com
VRT_DOCS_ENABLED=false
VRT_DEBUG_ROUTES_ENABLED=false
VRT_PASSWORD_RESET_RETURNS_TOKEN=false
VRT_REQUIRE_SIGNUP_INVITE=true
VRT_STRICT_STARTUP_CHECKS=true
VRT_PUBLIC_STATUS_DETAILED_CHECKS=false
VRT_PUBLIC_STATUS_SHOW_DEMO_DETAILS=false
VRT_SUPPORT_EMAIL=support@yourdomain.com
VRT_LEGAL_COMPANY_NAME=Your Company LLC
VRT_LEGAL_EFFECTIVE_DATE=2026-04-06
VRT_LEGAL_JURISDICTION=Missouri, USA
VRT_EMAIL_PROVIDER=resend
VRT_RESEND_API_KEY=re_xxxxx
VRT_EMAIL_FROM=Range & React <noreply@yourdomain.com>
VRT_EMAIL_REPLY_TO=support@yourdomain.com
VRT_SENTRY_DSN=https://...@o0.ingest.sentry.io/0
VRT_SENTRY_ENVIRONMENT=production
VRT_SENTRY_TRACES_SAMPLE_RATE=0.1
VRT_SENTRY_PROFILES_SAMPLE_RATE=0
```

Frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com
NEXT_PUBLIC_SUPPORT_EMAIL=support@yourdomain.com
```

## Health endpoints
- `/livez` or `/healthz`: lightweight liveness check
- `/readyz`: dependency-aware readiness summary
- `/admin/runtime-checks`: authenticated owner/admin-only detailed runtime checks

## Backups
For managed PostgreSQL, enable daily automated backups in the platform provider.

For manual backups:

```bash
pg_dump "$VRT_DATABASE_URL" --format=custom --file=live_range_lab.backup
```

Restore:

```bash
pg_restore --clean --if-exists --no-owner --dbname "$VRT_DATABASE_URL" live_range_lab.backup
```

## Rollback checklist
- keep the previous backend image available
- keep the previous frontend deployment available
- verify `/readyz` after deploy
- verify owner login, coach dashboard load, and one full training hand
- if deploy fails, roll back web and api together if schema/app changes shipped together

## Monitoring
- Configure Sentry DSN for backend exception capture
- Keep request logging enabled in production
- Watch `/readyz` for degraded status after deploys
- Review analytics latency in coach/admin pages after larger member imports
