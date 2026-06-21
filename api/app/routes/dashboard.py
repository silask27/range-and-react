
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.security import get_current_user
from api.app.services.access_service import get_visible_organization_ids, get_visible_user_ids
from api.app.services.analytics_service import get_admin_analytics, get_dashboard_overview

router = APIRouter(prefix='/dashboard', tags=['dashboard'])


def _with_labels(item: dict) -> dict:
    payload = dict(item)
    scenario_id = payload.get('scenario_id')
    villain_id = payload.get('villain_profile_id')
    payload['scenario_display_name'] = SCENARIOS.get(scenario_id).display_name if scenario_id in SCENARIOS else None
    payload['villain_display_name'] = VILLAIN_PROFILES.get(villain_id).meta.display_name if villain_id in VILLAIN_PROFILES else None
    return payload


@router.get('/overview')
def dashboard_overview_route(background_tasks: BackgroundTasks, current_user: UserAccount = Depends(get_current_user)) -> dict:
    overview = get_dashboard_overview(user_id=current_user.user_id, background_tasks=background_tasks)
    coach_summary = None
    if current_user.role in {UserRole.OWNER, UserRole.ADMIN, UserRole.COACH}:
        analytics = get_admin_analytics(
            visible_user_ids=get_visible_user_ids(current_user),
            visible_organization_ids=get_visible_organization_ids(current_user),
            background_tasks=background_tasks,
        )
        coach_summary = analytics.get('summary')
    return {
        **overview,
        'coach_summary': coach_summary,
        'recent_sessions': [_with_labels(item) for item in overview.get('recent_sessions', [])],
        'recent_hands': [_with_labels(item) for item in overview.get('recent_hands', [])],
        'recent_results': [_with_labels(item) for item in overview.get('recent_results', [])],
        'assignments': [_with_labels(item) for item in overview.get('assignments', [])],
    }
