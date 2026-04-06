from __future__ import annotations

from fastapi import APIRouter, Depends

from api.app.config import settings
from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.runtime_checks import run_runtime_checks, summarize_runtime_checks
from api.app.security import require_role
from api.app.services.email_service import email_delivery_enabled
from api.app.storage.db import DATABASE_BACKEND

router = APIRouter(tags=["platform"])


@router.get("/readyz")
def readiness_check() -> dict:
    checks = run_runtime_checks()
    summary = summarize_runtime_checks(checks)
    database_status = next((check.status for check in checks if check.name == "database"), "unknown")
    sentry_status = next((check.status for check in checks if check.name == "sentry"), "unknown")
    payload = {
        "status": summary["status"],
        "service": settings.app_name,
        "environment": settings.app_env,
        "database": database_status,
        "database_backend": DATABASE_BACKEND,
        "email_provider": settings.email_provider or 'disabled',
        "email_delivery": 'ok' if email_delivery_enabled() else 'disabled',
        "sentry": sentry_status,
        "strict_startup_checks": settings.strict_startup_checks,
        "version": settings.app_version,
        "error_count": summary["error_count"],
        "warning_count": summary["warning_count"],
        "detail_visibility": 'full' if settings.public_status_detailed_checks else 'summary',
    }
    if settings.public_status_detailed_checks:
        payload["checks"] = summary["checks"]
    return payload


@router.get("/platform/public-config")
def public_config() -> dict:
    demo_accounts = []
    if settings.demo_mode_enabled and settings.public_status_show_demo_details:
        demo_accounts = [
            {"label": "Owner demo", "email": settings.demo_owner_email, "role": "owner"},
            {"label": "Coach demo", "email": settings.demo_coach_email, "role": "coach"},
            {"label": "Member demo", "email": settings.demo_member_email, "role": "member"},
        ]
        if settings.demo_public_credentials:
            for item in demo_accounts:
                item["password"] = settings.demo_seed_password

    return {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
        "frontend_url": settings.frontend_url,
        "support_email": settings.support_email,
        "features": {
            "standalone_accounts": not settings.require_signup_invite,
            "invite_only_access": settings.require_signup_invite,
            "external_member_linking_ready": True,
            "assignments": True,
            "results": True,
            "admin_dashboard": True,
            "coach_analytics": True,
            "audit_logs": True,
            "organizations": True,
            "account_management": True,
            "password_reset": True,
            "invite_acceptance": True,
            "email_delivery": email_delivery_enabled(),
            "demo_seed_flow": True,
        },
        "legal": {
            "privacy_path": "/privacy",
            "terms_path": "/terms",
            "status_path": "/status",
            "company_name": settings.legal_company_name,
            "effective_date": settings.legal_effective_date,
            "jurisdiction": settings.legal_jurisdiction,
            "support_email": settings.support_email,
        },
        "ops": {
            "public_status_detailed_checks": settings.public_status_detailed_checks,
            "public_status_show_demo_details": settings.public_status_show_demo_details,
        },
        "demo": {
            "enabled": settings.demo_mode_enabled,
            "public_credentials": settings.demo_public_credentials and settings.public_status_show_demo_details,
            "organization_name": settings.demo_org_name,
            "accounts": demo_accounts,
            "seed_command": "python -m api.scripts.seed_demo_data --reset" if settings.public_status_show_demo_details else None,
        },
    }


@router.get("/admin/runtime-checks")
def admin_runtime_checks_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    checks = run_runtime_checks()
    summary = summarize_runtime_checks(checks)
    return {
        "status": summary["status"],
        "environment": settings.app_env,
        "version": settings.app_version,
        "error_count": summary["error_count"],
        "warning_count": summary["warning_count"],
        "checks": summary["checks"],
        "requested_by": current_user.user_id,
    }
