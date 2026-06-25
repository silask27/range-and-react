from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(raw: str | None, fallback: list[str]) -> list[str]:
    if raw is None:
        return fallback
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or fallback


def _app_env() -> str:
    return os.getenv("VRT_APP_ENV", "development").strip().lower()


def _is_production() -> bool:
    return _app_env() == "production"


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("VRT_APP_NAME", "Range & React")
    app_env: str = os.getenv("VRT_APP_ENV", "development")
    app_version: str = os.getenv("VRT_APP_VERSION", "0.7.0")
    frontend_url: str = os.getenv("VRT_FRONTEND_URL", "http://127.0.0.1:3000")
    support_email: str = os.getenv("VRT_SUPPORT_EMAIL", "support@rangeandreact.com")
    legal_company_name: str = os.getenv("VRT_LEGAL_COMPANY_NAME", os.getenv("VRT_APP_NAME", "Range & React")).strip() or os.getenv("VRT_APP_NAME", "Range & React")
    legal_effective_date: str = os.getenv("VRT_LEGAL_EFFECTIVE_DATE", "2026-04-06").strip() or "2026-04-06"
    legal_jurisdiction: str = os.getenv("VRT_LEGAL_JURISDICTION", "Missouri, USA").strip() or "Missouri, USA"
    public_status_detailed_checks: bool = _get_bool("VRT_PUBLIC_STATUS_DETAILED_CHECKS", not _is_production())
    public_status_show_demo_details: bool = _get_bool("VRT_PUBLIC_STATUS_SHOW_DEMO_DETAILS", not _is_production())
    email_provider: str = os.getenv("VRT_EMAIL_PROVIDER", "").strip().lower()
    resend_api_key: str = os.getenv("VRT_RESEND_API_KEY", "").strip()
    email_from: str = os.getenv("VRT_EMAIL_FROM", "").strip()
    email_reply_to: str = os.getenv("VRT_EMAIL_REPLY_TO", "").strip()
    welcome_email_enabled: bool = _get_bool("VRT_WELCOME_EMAIL_ENABLED", True)
    signup_invite_accept_path: str = os.getenv("VRT_SIGNUP_INVITE_ACCEPT_PATH", "/login").strip() or "/login"
    password_reset_path: str = os.getenv("VRT_PASSWORD_RESET_PATH", "/reset-password").strip() or "/reset-password"
    docs_enabled: bool = _get_bool("VRT_DOCS_ENABLED", not _is_production())
    debug_routes_enabled: bool = _get_bool("VRT_DEBUG_ROUTES_ENABLED", not _is_production())
    log_level: str = os.getenv("VRT_LOG_LEVEL", "INFO").upper()
    log_json: bool = _get_bool("VRT_LOG_JSON", False)
    request_log_enabled: bool = _get_bool("VRT_REQUEST_LOG_ENABLED", True)
    sentry_dsn: str = os.getenv("VRT_SENTRY_DSN", "").strip()
    sentry_environment: str = os.getenv("VRT_SENTRY_ENVIRONMENT", os.getenv("VRT_APP_ENV", "development")).strip() or os.getenv("VRT_APP_ENV", "development")
    sentry_traces_sample_rate: float = float(os.getenv("VRT_SENTRY_TRACES_SAMPLE_RATE", "0"))
    sentry_profiles_sample_rate: float = float(os.getenv("VRT_SENTRY_PROFILES_SAMPLE_RATE", "0"))
    strict_startup_checks: bool = _get_bool("VRT_STRICT_STARTUP_CHECKS", _is_production())
    password_reset_returns_token: bool = _get_bool("VRT_PASSWORD_RESET_RETURNS_TOKEN", not _is_production())
    require_signup_invite: bool = _get_bool("VRT_REQUIRE_SIGNUP_INVITE", _is_production())
    trusted_hosts: list[str] = None  # type: ignore[assignment]
    trust_proxy_headers: bool = _get_bool("VRT_TRUST_PROXY_HEADERS", False)
    admin_analytics_cache_ttl_seconds: int = int(os.getenv("VRT_ADMIN_ANALYTICS_CACHE_TTL_SECONDS", "300"))
    dashboard_overview_cache_ttl_seconds: int = int(os.getenv("VRT_DASHBOARD_OVERVIEW_CACHE_TTL_SECONDS", "120"))
    auth_cookie_name: str = os.getenv("VRT_AUTH_COOKIE_NAME", "rr_auth").strip() or "rr_auth"
    auth_cookie_secure: bool = _get_bool("VRT_AUTH_COOKIE_SECURE", _is_production())
    auth_cookie_samesite: str = os.getenv("VRT_AUTH_COOKIE_SAMESITE", "none" if _is_production() else "lax").strip().lower() or ("none" if _is_production() else "lax")
    auth_cookie_ttl_days: int = int(os.getenv("VRT_AUTH_TOKEN_TTL_DAYS", "30"))

    demo_mode_enabled: bool = _get_bool("VRT_DEMO_MODE_ENABLED", False)
    demo_public_credentials: bool = _get_bool("VRT_DEMO_PUBLIC_CREDENTIALS", False)
    demo_org_name: str = os.getenv("VRT_DEMO_ORG_NAME", "Range & React Demo")
    demo_owner_email: str = os.getenv("VRT_DEMO_OWNER_EMAIL", "owner@demo.local")
    demo_coach_email: str = os.getenv("VRT_DEMO_COACH_EMAIL", "coach@demo.local")
    demo_member_email: str = os.getenv("VRT_DEMO_MEMBER_EMAIL", "member@demo.local")
    demo_seed_password: str = os.getenv("VRT_DEMO_SEED_PASSWORD", "DemoPass123!")

    allowed_origins: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        fallback = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://rangeandreact.com",
            "https://www.rangeandreact.com",
        ]
        object.__setattr__(self, "allowed_origins", _split_csv(os.getenv("ALLOWED_ORIGINS"), fallback))
        trusted_host_fallback = ["localhost", "127.0.0.1", "testserver"] if not _is_production() else []
        object.__setattr__(self, "trusted_hosts", _split_csv(os.getenv("VRT_TRUSTED_HOSTS"), trusted_host_fallback))


settings = Settings()
