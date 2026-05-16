# File: api/app/routes/response_matrix.py
# Summary: API route for validating and saving the Screen 3 response matrix, then
# returning the updated public hand payload with subgroup-aware bucket rows.

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException

from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.models.auth import UserAccount
from api.app.models.state import HandState
from api.app.security import get_current_user
from api.app.services.auth_service import ensure_can_access_owner_resource
from api.app.services.hand_service import get_hand
from api.app.services.response_matrix_service import save_response_matrix

router = APIRouter(prefix="/response-matrix", tags=["response-matrix"])


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


@router.post("/save")
def save_response_matrix_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_id = payload.get("hand_id")
    selections = payload.get("selections")
    row_order = payload.get("row_order")
    fill_sequence = payload.get("fill_sequence")
    bucket_matrix_view = payload.get("bucket_matrix_view")
    raw_iters = payload.get("iters")
    allow_partial = bool(payload.get("allow_partial", False))
    save_reason = payload.get("save_reason")

    if not hand_id:
        raise HTTPException(status_code=400, detail="hand_id is required")
    if selections is None:
        raise HTTPException(status_code=400, detail="selections is required")

    iters = int(raw_iters) if raw_iters is not None else None

    try:
        existing = get_hand(hand_id)
        ensure_can_access_owner_resource(existing.user_id, current_user)
        hand = save_response_matrix(
            hand_id=hand_id,
            selections=selections,
            row_order=row_order if isinstance(row_order, list) else None,
            fill_sequence=fill_sequence if isinstance(fill_sequence, list) else None,
            bucket_matrix_view_snapshot=bucket_matrix_view if isinstance(bucket_matrix_view, dict) else None,
            iters=iters,
            allow_partial=allow_partial,
            save_reason=str(save_reason) if save_reason is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_hand_public(hand, iters=iters)
