# Launch Checklist

## Configuration
- [ ] Production domains are set for API and web
- [ ] `VRT_DATABASE_URL` points to managed PostgreSQL
- [ ] `ALLOWED_ORIGINS` contains only production web origins
- [ ] `VRT_TRUSTED_HOSTS` contains only production API hosts
- [ ] `VRT_DOCS_ENABLED=false`
- [ ] `VRT_DEBUG_ROUTES_ENABLED=false`
- [ ] `VRT_PASSWORD_RESET_RETURNS_TOKEN=false`
- [ ] `VRT_REQUIRE_SIGNUP_INVITE=true`
- [ ] `VRT_PUBLIC_STATUS_DETAILED_CHECKS=false`
- [ ] `VRT_PUBLIC_STATUS_SHOW_DEMO_DETAILS=false`
- [ ] `VRT_SUPPORT_EMAIL` is real and monitored
- [ ] `VRT_LEGAL_COMPANY_NAME`, `VRT_LEGAL_EFFECTIVE_DATE`, and `VRT_LEGAL_JURISDICTION` are set

## Email and access
- [ ] Resend is configured and sending successfully
- [ ] Password reset emails work end to end
- [ ] Invite emails work end to end
- [ ] Coach/admin can bulk-create invites
- [ ] Public signup is blocked without invites

## Product checks
- [ ] Owner can log in and load admin page
- [ ] Coach can see only their organization members
- [ ] Member can train, finish a hand, and review results
- [ ] Assignments can be created and completed
- [ ] Dashboard and results pages load with real seeded or staging data

## Operational checks
- [ ] `make launch-gate` passes
- [ ] `make preflight` passes
- [ ] `/readyz` reports no required errors
- [ ] `/admin/runtime-checks` reports expected warnings only
- [ ] Sentry is receiving test events
- [ ] PostgreSQL backups are enabled
- [ ] Rollback steps are documented and tested
