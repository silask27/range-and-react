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
    bucket_matrix_view_override: dict | None = None,
) -> dict:
    payload = asdict(hand)

    bucket_matrix_view = bucket_matrix_view_override or build_bucket_matrix_view(
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


def _live_combo_count(hand: HandState) -> int:
    return sum(len(combos) for combos in hand.villain_range_combos_live.values())


def _valid_bucket_matrix_override(
    hand: HandState,
    bucket_matrix_view: object,
    *,
    previous_board: list[str] | None = None,
) -> dict | None:
    if not isinstance(bucket_matrix_view, dict):
        return None
    if previous_board is not None and list(previous_board) != list(hand.board):
        return None

    total_live_combos = bucket_matrix_view.get("total_live_combos")
    if total_live_combos != _live_combo_count(hand):
        return None

    rows = bucket_matrix_view.get("rows")
    if not isinstance(rows, list):
        return None
    row_combo_total = 0
    for row in rows:
        if not isinstance(row, dict):
            return None
        combo_count = row.get("combo_count")
        if not isinstance(combo_count, int):
            return None
        row_combo_total += combo_count
    if row_combo_total != total_live_combos:
        return None

    return bucket_matrix_view


def _bucket_matrix_after_removed_subgroup(
    hand: HandState,
    bucket_matrix_view: dict | None,
    bucket_name: str | None,
    subgroup_name: str,
) -> dict | None:
    if not bucket_matrix_view or not bucket_name:
        return None

    total_live_combos = _live_combo_count(hand)
    rows = bucket_matrix_view.get("rows")
    if not isinstance(rows, list):
        return None

    updated_rows: list[dict] = []
    removed_any = False
    for row in rows:
        if not isinstance(row, dict):
            return None

        row_copy = dict(row)
        raw_subgroups = row.get("subgroups")
        subgroups = [dict(item) for item in raw_subgroups] if isinstance(raw_subgroups, list) else []
        if row_copy.get("bucket_name") == bucket_name and any(item.get("subgroup_name") == subgroup_name for item in subgroups):
            removed_any = True
            next_subgroups = [
                item for item in subgroups if item.get("subgroup_name") != subgroup_name
            ]
            next_hands: list[dict] = []
            for subgroup in next_subgroups:
                for hand_entry in subgroup.get("hands", []) or []:
                    if isinstance(hand_entry, dict):
                        next_hands.append(dict(hand_entry))

            next_combo_count = sum(int(item.get("combo_count") or 0) for item in next_subgroups)
            row_copy["subgroups"] = next_subgroups
            row_copy["hands"] = next_hands
            row_copy["combo_count"] = next_combo_count
            row_copy["holdings_count"] = len(next_hands)
        else:
            row_combo_count = row_copy.get("combo_count")
            if not isinstance(row_combo_count, int):
                return None
            next_combo_count = row_combo_count

        row_copy["bucket_percent"] = round((next_combo_count / total_live_combos) * 100, 2) if total_live_combos else 0
        updated_rows.append(row_copy)

    if not removed_any:
        return None

    if sum(int(row.get("combo_count") or 0) for row in updated_rows) != total_live_combos:
        return None

    return {
        **bucket_matrix_view,
        "total_live_combos": total_live_combos,
        "rows": updated_rows,
    }


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
    bucket_matrix_view = payload.get("bucket_matrix_view")
    elapsed_ms = payload.get("elapsed_ms")
    raw_iters = payload.get("iters")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")
    if not subgroup_name:
        raise HTTPException(status_code=400, detail="subgroup_name is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        existing = _get_authorized_hand(hand_id, current_user)
        bucket_name_before_remove = existing.next_prune_bucket()
        bucket_matrix_before_remove = _valid_bucket_matrix_override(
            existing,
            bucket_matrix_view,
        )
        hand = remove_subgroup_from_current_row(
            hand_id=hand_id,
            subgroup_name=subgroup_name,
            bucket_matrix_view_snapshot=bucket_matrix_view if isinstance(bucket_matrix_view, dict) else None,
            elapsed_ms=int(elapsed_ms) if elapsed_ms is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(
        hand,
        iters=iters,
        bucket_matrix_view_override=_bucket_matrix_after_removed_subgroup(
            hand,
            bucket_matrix_before_remove,
            bucket_name_before_remove,
            str(subgroup_name),
        ),
    )


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
    bucket_matrix_view = payload.get("bucket_matrix_view")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        existing = _get_authorized_hand(hand_id, current_user)
        hand = save_current_row_and_advance(
            hand_id=hand_id,
            iters=iters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(
        hand,
        iters=iters,
        bucket_matrix_view_override=_valid_bucket_matrix_override(
            hand,
            bucket_matrix_view,
            previous_board=list(existing.board),
        ),
    )


@router.post("/save-step")
def save_full_prune_step_and_continue_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    raw_iters = payload.get("iters")
    bucket_matrix_view = payload.get("bucket_matrix_view")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        existing = _get_authorized_hand(hand_id, current_user)
        hand = save_full_prune_step_and_continue(
            hand_id=hand_id,
            iters=iters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(
        hand,
        iters=iters,
        bucket_matrix_view_override=_valid_bucket_matrix_override(
            hand,
            bucket_matrix_view,
            previous_board=list(existing.board),
        ),
    )
