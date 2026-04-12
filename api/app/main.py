# File: api/app/main.py
# Summary: FastAPI application entrypoint that boots the backend, enables CORS, configures
# logging, exposes health/readiness/public-config routes, and registers the core API routers.

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.app.config import settings
from api.app.observability import configure_sentry
from api.app.runtime_checks import assert_startup_ready
from api.app.logging_utils import RequestLoggingMiddleware, SecurityHeadersMiddleware, configure_logging
from api.app.rate_limiter import RateLimitExceeded, SlowAPIMiddleware, limiter, rate_limit_exceeded_handler
from api.app.routes.actions import router as actions_router
from api.app.routes.assignments import router as assignments_router
from api.app.routes.admin import router as admin_router
from api.app.routes.auth import router as auth_router
from api.app.routes.dashboard import router as dashboard_router
from api.app.routes.debug import router as debug_router
from api.app.routes.hands import router as hands_router
from api.app.routes.platform import router as platform_router
from api.app.routes.prune import router as prune_router
from api.app.routes.response_matrix import router as response_matrix_router
from api.app.routes.results import router as results_router
from api.app.routes.reveal import router as reveal_router
from api.app.routes.scenarios import router as scenarios_router
from api.app.routes.sessions import router as sessions_router
from api.app.routes.villains import router as villains_router
from api.app.storage.db import close_database, init_db

configure_logging()
configure_sentry()
init_db()

app = FastAPI(
    title=f"{settings.app_name} API",
    version=settings.app_version,
    description="Backend API for the Range & React poker training app.",
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
if settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(platform_router)
app.include_router(auth_router)
app.include_router(assignments_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(villains_router)
app.include_router(scenarios_router)
app.include_router(sessions_router)
app.include_router(hands_router)
app.include_router(prune_router)
app.include_router(response_matrix_router)
app.include_router(actions_router)
app.include_router(reveal_router)
app.include_router(results_router)
if settings.debug_routes_enabled:
    app.include_router(debug_router)


@app.get("/livez")
def livecheck() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
    }


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return livecheck()


@app.on_event("startup")
def _startup_init_db() -> None:
    init_db()
    assert_startup_ready()


@app.on_event("shutdown")
def _shutdown_close_database() -> None:
    close_database()
