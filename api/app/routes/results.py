from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.app.models.auth import UserAccount
from api.app.security import get_current_user
from api.app.services.auth_service import ensure_can_access_owner_resource
from api.app.services.hand_service import get_hand
from api.app.services.scoring_service import build_hand_debrief, build_results_overview

router = APIRouter(prefix='/results', tags=['results'])


@router.get('/overview')
def results_overview_route(current_user: UserAccount = Depends(get_current_user)) -> dict:
    return build_results_overview(user_id=current_user.user_id)


@router.get('/hand/{hand_id}')
def hand_debrief_route(hand_id: str, current_user: UserAccount = Depends(get_current_user)) -> dict:
    try:
        hand = get_hand(hand_id)
        ensure_can_access_owner_resource(hand.user_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not hand.hand_over:
        raise HTTPException(status_code=400, detail='Hand must be complete before debrief is available.')

    return build_hand_debrief(hand)
