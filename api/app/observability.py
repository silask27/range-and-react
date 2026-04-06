from __future__ import annotations

import logging

from api.app.config import settings

logger = logging.getLogger(__name__)



def configure_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except Exception as exc:  # pragma: no cover - dependency/import variability
        logger.warning("Sentry SDK could not be imported: %s", exc)
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=max(0.0, settings.sentry_traces_sample_rate),
        profiles_sample_rate=max(0.0, settings.sentry_profiles_sample_rate),
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(event_level=None),
        ],
        send_default_pii=False,
    )
    logger.info("Sentry configured for environment %s", settings.sentry_environment)
