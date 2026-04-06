
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.models.auth import UserAccount
from api.app.security import get_current_user
from api.app.services.assignment_service import build_user_assignment_queue

router = APIRouter(prefix='/assignments', tags=['assignments'])


def _decorate_assignment(item: dict) -> dict:
    payload = dict(item)
    scenario_id = payload.get('scenario_id')
    villain_id = payload.get('villain_profile_id')
    payload['scenario_display_name'] = SCENARIOS[scenario_id].display_name if scenario_id in SCENARIOS else None
    payload['villain_display_name'] = VILLAIN_PROFILES[villain_id].meta.display_name if villain_id in VILLAIN_PROFILES else None
    return payload


@router.get('/my')
def my_assignments_route(current_user: UserAccount = Depends(get_current_user)) -> dict:
    payload = build_user_assignment_queue(user_id=current_user.user_id)
    payload['assignments'] = [_decorate_assignment(item) for item in payload['assignments']]
    return payload
