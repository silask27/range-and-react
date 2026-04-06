# File: api/app/routes/hands.py
# Summary: API routes for starting, listing, and retrieving hands while returning a
# Screen 3-ready public hand payload with subgroup-aware bucket matrix data.

from __future__ import annotations

from dataclasses import asdict
import random

from fastapi import APIRouter, Body, Depends, HTTPException

from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.models.auth import UserAccount
from api.app.models.state import HandState
from api.app.security import get_current_user
from api.app.services.auth_service import ensure_can_access_owner_resource, user_has_elevated_access
from api.app.services.hand_service import get_hand, start_hand
from api.app.services.session_service import get_session
from api.app.storage.memory_store import store

router = APIRouter(prefix="/hands", tags=["hands"])


def _resolved_seed(seed: int | None) -> int:
    if seed is not None:
        return int(seed)
    return random.SystemRandom().randrange(1, 1_000_000_000)


def _serialize_hand_public(
    hand: HandState,
    *,
    iters: int | None = None,
) -> dict:
    payload = asdict(hand)

    bucket_matrix_view = build_bucket_matrix_view(
        villain_range_combos_live=hand.villain_range_combos_live,
        board=hand.board,
        hero_hand=hand.hero_hand,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        iters=iters,
        seed=int(hand.bucket_seed),
    )

    payload.pop("villain_hand", None)
    payload["hand_id"] = hand.hand_id
    payload["session_id"] = hand.session_id
    payload["villain_hand_revealed"] = False
    payload["bucket_matrix_view"] = bucket_matrix_view

    return payload


@router.get("")
def list_hands_route(
    session_id: str | None = None,
    limit: int = 25,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    user_id = None if user_has_elevated_access(current_user) else current_user.user_id
    hands = store.list_hands(user_id=user_id, session_id=session_id, limit=limit)
    return {"hands": hands}


@router.get("/latest")
def get_latest_hand_route(
    session_id: str,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    try:
        session = get_session(session_id)
        ensure_can_access_owner_resource(session.user_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    hand = store.get_latest_hand_for_session(session_id)
    if hand is None:
        raise HTTPException(status_code=404, detail="No hand found for session")
    return hand


@router.post("/start")
def start_hand_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    session_id = payload.get("session_id")
    raw_seed = payload.get("seed")
    raw_iters = payload.get("iters")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        session = get_session(session_id)
        ensure_can_access_owner_resource(session.user_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    existing_hand_id = payload.get("hand_id")
    if existing_hand_id:
        try:
            existing_hand = get_hand(existing_hand_id)
            ensure_can_access_owner_resource(existing_hand.user_id, current_user)
            return _serialize_hand_public(existing_hand, iters=int(raw_iters) if raw_iters is not None else None)
        except ValueError:
            pass

    seed = int(raw_seed) if raw_seed is not None else _resolved_seed(None)
    iters = int(raw_iters) if raw_iters is not None else None

    try:
        hand = start_hand(
            session_id=session_id,
            seed=seed,
            iters=iters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)


@router.get("/{hand_id}")
def get_hand_route(
    hand_id: str,
    iters: int | None = None,
    seed: int | None = None,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    del seed

    try:
        hand = get_hand(hand_id)
        ensure_can_access_owner_resource(hand.user_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)
