from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.app.config import settings
from api.app.engine.villain_decision import validate_model_runtime
from api.app.services.email_service import email_delivery_enabled
from api.app.storage.db import DATABASE_BACKEND, get_connection


@dataclass(frozen=True)
class RuntimeCheckResult:
    name: str
    status: str
    detail: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1")
_PLACEHOLDER_EMAIL_MARKERS = ("example.com", "support@example.com")
_PLACEHOLDER_COMPANY_NAMES = ("live range lab", "villain range trainer")


def _check_database() -> RuntimeCheckResult:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return RuntimeCheckResult("database", "ok", f"Connected via {DATABASE_BACKEND}")
    except Exception as exc:  # pragma: no cover - exercised through readiness/runtime usage
        return RuntimeCheckResult("database", "error", f"Database connectivity failed: {exc}")


def _check_model_runtime() -> RuntimeCheckResult:
    try:
        validate_model_runtime()
        return RuntimeCheckResult("predictive_models", "ok", "Model artifacts and runtime dependencies are ready")
    except Exception as exc:  # pragma: no cover - exercised through readiness/runtime usage
        return RuntimeCheckResult("predictive_models", "error", f"Model runtime check failed: {exc}")


def _check_email_delivery() -> RuntimeCheckResult:
    if not settings.email_provider:
        return RuntimeCheckResult("email_delivery", "warn", "Email provider disabled", required=False)
    if email_delivery_enabled():
        return RuntimeCheckResult("email_delivery", "ok", f"Email delivery configured via {settings.email_provider}", required=False)
    return RuntimeCheckResult(
        "email_delivery",
        "error",
        "Email provider is set but required credentials are incomplete",
        required=False,
    )


def _check_sentry() -> RuntimeCheckResult:
    if not settings.sentry_dsn:
        return RuntimeCheckResult("sentry", "warn", "Sentry DSN not configured", required=False)
    return RuntimeCheckResult("sentry", "ok", "Sentry DSN configured", required=False)


def _check_legal_metadata() -> RuntimeCheckResult:
    issues: list[str] = []
    company_name = settings.legal_company_name.strip()
    if not company_name:
        issues.append("company name is blank")
    elif company_name.strip().lower() in _PLACEHOLDER_COMPANY_NAMES:
        issues.append("company name still uses a placeholder/project name")

    if not settings.legal_effective_date.strip():
        issues.append("effective date is blank")

    if any(marker in settings.support_email.lower() for marker in _PLACEHOLDER_EMAIL_MARKERS):
        issues.append("support email still uses a placeholder value")

    if issues:
        return RuntimeCheckResult(
            "legal_metadata",
            "warn",
            "Legal/support metadata needs review: " + "; ".join(issues),
            required=False,
        )
    return RuntimeCheckResult("legal_metadata", "ok", "Legal/support metadata looks production-ready", required=False)


def _check_production_runtime() -> list[RuntimeCheckResult]:
    if settings.app_env.strip().lower() != "production":
        return []

    checks: list[RuntimeCheckResult] = []
    if DATABASE_BACKEND != "postgresql":
        checks.append(RuntimeCheckResult("production_database", "error", "Production should use PostgreSQL, not SQLite"))
    else:
        checks.append(RuntimeCheckResult("production_database", "ok", "PostgreSQL configured for production"))

    if settings.docs_enabled:
        checks.append(RuntimeCheckResult("production_docs", "error", "API docs should be disabled in production"))
    else:
        checks.append(RuntimeCheckResult("production_docs", "ok", "API docs disabled in production"))

    if settings.debug_routes_enabled:
        checks.append(RuntimeCheckResult("production_debug_routes", "error", "Debug routes should be disabled in production"))
    else:
        checks.append(RuntimeCheckResult("production_debug_routes", "ok", "Debug routes disabled in production"))

    if settings.password_reset_returns_token:
        checks.append(
            RuntimeCheckResult(
                "production_password_reset_tokens",
                "error",
                "Password reset tokens must not be returned in API responses in production",
            )
        )
    else:
        checks.append(RuntimeCheckResult("production_password_reset_tokens", "ok", "Password reset responses are production-safe"))

    if not settings.require_signup_invite:
        checks.append(RuntimeCheckResult("production_signup_mode", "warn", "Invite-only signup is disabled", required=False))
    else:
        checks.append(RuntimeCheckResult("production_signup_mode", "ok", "Invite-only signup enabled", required=False))

    if any(marker in settings.frontend_url.lower() for marker in _LOCAL_HOST_MARKERS):
        checks.append(RuntimeCheckResult("production_frontend_url", "error", "Frontend URL still points to localhost"))
    else:
        checks.append(RuntimeCheckResult("production_frontend_url", "ok", "Frontend URL looks production-ready"))

    if not settings.trusted_hosts:
        checks.append(RuntimeCheckResult("production_trusted_hosts", "warn", "Trusted hosts are not configured", required=False))
    else:
        checks.append(RuntimeCheckResult("production_trusted_hosts", "ok", f"Trusted hosts configured: {settings.trusted_hosts}", required=False))

    localhost_origins = [origin for origin in settings.allowed_origins if any(marker in origin.lower() for marker in _LOCAL_HOST_MARKERS)]
    if localhost_origins:
        checks.append(RuntimeCheckResult("production_allowed_origins", "error", f"Allowed origins include localhost entries: {localhost_origins}"))
    else:
        checks.append(RuntimeCheckResult("production_allowed_origins", "ok", "Allowed origins look production-ready"))

    if settings.public_status_detailed_checks:
        checks.append(
            RuntimeCheckResult(
                "production_public_status_detail",
                "warn",
                "Public status endpoint exposes detailed runtime checks; disable for public production pages",
                required=False,
            )
        )
    else:
        checks.append(RuntimeCheckResult("production_public_status_detail", "ok", "Public status endpoint hides detailed checks", required=False))

    if any(marker in settings.support_email.lower() for marker in _PLACEHOLDER_EMAIL_MARKERS):
        checks.append(RuntimeCheckResult("production_support_email", "warn", "Support email still uses a placeholder value", required=False))
    else:
        checks.append(RuntimeCheckResult("production_support_email", "ok", "Support email looks production-ready", required=False))

    return checks


def run_runtime_checks() -> list[RuntimeCheckResult]:
    checks = [
        _check_database(),
        _check_model_runtime(),
        _check_email_delivery(),
        _check_sentry(),
        _check_legal_metadata(),
    ]
    checks.extend(_check_production_runtime())
    return checks



def summarize_runtime_checks(checks: list[RuntimeCheckResult]) -> dict[str, Any]:
    errors = [check for check in checks if check.status == "error"]
    warnings = [check for check in checks if check.status == "warn"]
    return {
        "status": "ok" if not errors else "degraded",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "checks": [check.to_dict() for check in checks],
    }



def assert_startup_ready() -> None:
    checks = run_runtime_checks()
    errors = [check for check in checks if check.status == "error" and check.required]
    if errors and settings.strict_startup_checks:
        joined = "; ".join(f"{check.name}: {check.detail}" for check in errors)
        raise RuntimeError(f"Startup preflight failed: {joined}")
