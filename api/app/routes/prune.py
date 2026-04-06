# File: api/app/routes/prune.py
# Summary: API routes for starting prune mode and applying subgroup-level remove,
# revert, and save-row actions while returning a Screen 3-ready public hand payload.

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException

from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.models.auth import UserAccount
from api.app.models.state import HandState
from api.app.security import get_current_user
from api.app.services.auth_service import ensure_can_access_owner_resource
from api.app.services.hand_service import get_hand
from api.app.services.prune_service import (
    remove_subgroup_from_current_row,
    revert_current_row,
    save_current_row_and_advance,
    save_full_prune_step_and_continue,
    start_prune_mode,
)

router = APIRouter(prefix="/prune", tags=["prune"])


def _serialize_prune_row_for_ui(
    bucket_name: str | None,
    row_snapshot: dict[str, dict[str, list[list[str]]]] | None,
) -> dict | None:
    if bucket_name is None or row_snapshot is None:
        return None

    subgroups: list[dict] = []
    for subgroup_name, label_map in row_snapshot.items():
        combo_count = sum(len(combos) for combos in label_map.values())
        subgroups.append(
            {
                "subgroup_name": subgroup_name,
                "combo_count": combo_count,
            }
        )

    subgroups.sort(key=lambda item: (-item["combo_count"], item["subgroup_name"]))

    return {
        "bucket_name": bucket_name,
        "subgroups": subgroups,
    }


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

    current_bucket = hand.next_prune_bucket()
    payload["current_prune_bucket"] = current_bucket
    payload["current_prune_row_saved_version"] = _serialize_prune_row_for_ui(
        current_bucket,
        hand.current_prune_row_saved_version(),
    )
    payload["current_prune_row_original"] = _serialize_prune_row_for_ui(
        current_bucket,
        hand.current_prune_row_original(),
    )
    return payload


def _get_authorized_hand(hand_id: str, current_user: UserAccount):
    existing = get_hand(hand_id)
    ensure_can_access_owner_resource(existing.user_id, current_user)
    return existing


@router.post("/start")
def start_prune_mode_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    raw_iters = payload.get("iters")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        _get_authorized_hand(hand_id, current_user)
        hand = start_prune_mode(
            hand_id=hand_id,
            iters=iters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)


@router.post("/remove-subgroup")
def remove_subgroup_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    subgroup_name = payload.get("subgroup_name")
    raw_iters = payload.get("iters")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")
    if not subgroup_name:
        raise HTTPException(status_code=400, detail="subgroup_name is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        _get_authorized_hand(hand_id, current_user)
        hand = remove_subgroup_from_current_row(
            hand_id=hand_id,
            subgroup_name=subgroup_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)


@router.post("/revert")
def revert_current_row_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    raw_iters = payload.get("iters")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        _get_authorized_hand(hand_id, current_user)
        hand = revert_current_row(hand_id=hand_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)


@router.post("/save-row")
def save_current_row_and_advance_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    raw_iters = payload.get("iters")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        _get_authorized_hand(hand_id, current_user)
        hand = save_current_row_and_advance(
            hand_id=hand_id,
            iters=iters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)


@router.post("/save-step")
def save_full_prune_step_and_continue_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    raw_iters = payload.get("iters")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        _get_authorized_hand(hand_id, current_user)
        hand = save_full_prune_step_and_continue(
            hand_id=hand_id,
            iters=iters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)
