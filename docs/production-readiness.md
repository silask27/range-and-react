# Production Readiness Notes

Range & React is designed for organization-owned training programs with one platform owner, organization admins/coaches, and many members. These notes capture the operational expectations that matter for a large coaching partner rollout.

## Access Model

- The platform owner has global control across every organization, admin, coach, member, cohort, invite, report, and access setting.
- Admins and coaches are scoped to their active organization memberships.
- Organization access can be active, trialing, expired, or paused from Admin > Setup. Paused or expired organizations block member/admin/coach sessions and signup invites while preserving owner access.
- Cohorts are managed in Admin as the source of truth. Coach > Assignments uses cohorts as read-only assignment targets so cohort setup is not duplicated.

## Reporting Model

- Reporting offers scheduled organization-level files only:
  - `Cohort Members Summary.csv`
  - `Org Wide Summary.csv`
- Results offers an ad hoc member-level export:
  - `<member_name>-results.csv`
- Member result exports include the member cohort. Cohort member summaries include cohort names and sort by cohort first.

## Scale Expectations

- High-volume paths use indexed joins for organization membership, cohort membership, result history, completed result export, and scheduled delivery scans.
- Member-facing result views stay bounded through existing API limits. Organization/cohort CSVs are intentionally summary shaped so they remain useful when the raw result table grows into millions of rows.
- For a partner with thousands of members, use PostgreSQL in production via `VRT_DATABASE_URL`; SQLite should remain local/demo only.

## Security Expectations

- Auth tokens are server-generated, hashed at rest, expiring, and revocable.
- Passwords are PBKDF2-hashed with per-password salt.
- Role and organization scope are checked on protected routes, and org pause/expiry is enforced during login, token validation, signup preview, and signup completion.
- Security response headers are enabled by middleware, including frame blocking, content sniffing protection, referrer policy, permissions policy, CSP, and production HSTS.
- Audit logs are written for sensitive admin actions such as organization setup, invites, user updates, and data delivery changes.

## Partner Copy Guardrails

Avoid using partner-specific public copy or program names until a formal partnership allows it. For Hungry Horse Poker, avoid public phrases such as Basecamp, "brain turn to mush," "install the thought process," "Real players. Real progress.", "Built for real games.", and "No memorization. No guesswork." General poker strategy language such as range, villain, live poker, preflop, in position, out of position, action prediction, and exploitative tendencies is acceptable.
