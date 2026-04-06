# File: api/app/routes/reveal.py
# Summary: API route for revealing villain hole cards after the hand is over.

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.app.models.auth import UserAccount
from api.app.security import get_current_user
from api.app.services.auth_service import ensure_can_access_owner_resource
from api.app.services.hand_service import get_hand
from api.app.services.reveal_service import reveal_villain_hand

router = APIRouter(prefix="/reveal", tags=["reveal"])


@router.get("/{hand_id}")
def reveal_villain_hand_route(
    hand_id: str,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    try:
        hand = get_hand(hand_id)
        ensure_can_access_owner_resource(hand.user_id, current_user)
        return reveal_villain_hand(hand_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
