# File: api/app/routes/debug.py
# Summary: Temporary debug routes for mutating in-memory hand state during backend development and manual testing.

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from api.app.models.enums import UIGate
from api.app.storage.memory_store import store

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/hands/{hand_id}/gate")
def set_hand_gate_route(
    hand_id: str,
    payload: dict = Body(...),
) -> dict:
    gate_value = payload.get("ui_gate")
    if not gate_value:
        raise HTTPException(status_code=400, detail="ui_gate is required")

    try:
        gate = UIGate(gate_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ui_gate: {gate_value}",
        ) from exc

    try:
        updated = store.update_hand(hand_id, {"ui_gate": gate})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "hand_id": hand_id,
        "ui_gate": updated["ui_gate"].value if hasattr(updated["ui_gate"], "value") else updated["ui_gate"],
    }


@router.post("/hands/{hand_id}/mark-over")
def mark_hand_over_route(hand_id: str) -> dict:
    """
    Debug-only helper to mark a hand as over so reveal flow can be tested.
    """
    try:
        updated = store.update_hand(
            hand_id,
            {
                "hand_over": True,
                "ui_gate": UIGate.HAND_OVER,
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "hand_id": hand_id,
        "hand_over": updated["hand_over"],
        "ui_gate": updated["ui_gate"].value if hasattr(updated["ui_gate"], "value") else updated["ui_gate"],
    }