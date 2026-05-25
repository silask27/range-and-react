# File: api/app/routes/sessions.py
# Summary: API routes for creating, reading, and updating Screen 1 session setup state.

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException

from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.models.state import SessionState
from api.app.security import get_current_user
from api.app.services.access_service import get_visible_user_ids
from api.app.services.auth_service import ensure_can_access_owner_resource
from api.app.services.session_service import (
    create_session,
    get_session,
    save_starting_range,
    set_session_scenario,
)
from api.app.storage.memory_store import store

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _serialize_session(session: SessionState) -> dict:
    return asdict(session)


@router.get("")
def list_sessions_route(
    limit: int = 25,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    if current_user.role == UserRole.OWNER:
        return {"sessions": store.list_sessions(limit=limit)}

    visible_user_ids = get_visible_user_ids(current_user) or [current_user.user_id]
    return {"sessions": store.list_sessions(user_ids=visible_user_ids, limit=limit)}


@router.post("")
def create_session_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    villain_profile_id = payload.get("villain_profile_id")
    train_timer_seconds = payload.get("train_timer_seconds")

    if not villain_profile_id:
        raise HTTPException(status_code=400, detail="villain_profile_id is required")

    try:
        session = create_session(
            user_id=current_user.user_id,
            villain_profile_id=villain_profile_id,
            train_timer_seconds=train_timer_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_session(session)


@router.get("/{session_id}")
def get_session_route(
    session_id: str,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    try:
        session = get_session(session_id)
        ensure_can_access_owner_resource(session.user_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _serialize_session(session)


@router.post("/{session_id}/scenario")
def set_session_scenario_route(
    session_id: str,
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    scenario_id = payload.get("scenario_id")
    seed = payload.get("seed")

    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id is required")

    try:
        existing = get_session(session_id)
        ensure_can_access_owner_resource(existing.user_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    kwargs = {
        "session_id": session_id,
        "scenario_id": scenario_id,
        "seed": seed,
    }

    if "train_timer_seconds" in payload:
        kwargs["train_timer_seconds"] = payload.get("train_timer_seconds")

    try:
        session = set_session_scenario(**kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_session(session)


@router.post("/{session_id}/starting-range")
def save_starting_range_route(
    session_id: str,
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    actor = payload.get("actor")
    matrix_state = payload.get("matrix_state")

    if actor not in {"hero", "villain"}:
        raise HTTPException(status_code=400, detail="actor is required and must be 'hero' or 'villain'")

    if not isinstance(matrix_state, dict):
        raise HTTPException(
            status_code=400,
            detail="matrix_state is required and must be an object",
        )

    try:
        existing = get_session(session_id)
        ensure_can_access_owner_resource(existing.user_id, current_user)
        session = save_starting_range(
            session_id=session_id,
            actor=actor,
            matrix_state=matrix_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_session(session)
