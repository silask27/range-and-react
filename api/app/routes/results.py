from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.app.models.auth import UserAccount
from api.app.security import get_current_user
from api.app.services.access_service import get_visible_organization_ids
from api.app.services.access_service import ensure_user_access
from api.app.services.auth_service import ensure_can_access_owner_resource
from api.app.services.data_delivery_service import member_summary_csv
from api.app.services.hand_service import get_hand
from api.app.services.review_service import (
    build_hand_replay,
    list_review_queue,
    send_flagged_hands_to_coaches,
    set_hand_review_flag,
    update_hand_review_note,
)
from api.app.services.scoring_service import build_hand_debrief, build_results_export_rows, build_results_overview

router = APIRouter(prefix='/results', tags=['results'])


@router.get('/overview')
def results_overview_route(
    user_id: str | None = Query(default=None),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    target_user_id = (user_id or current_user.user_id).strip()
    if target_user_id != current_user.user_id:
        ensure_user_access(current_user, target_user_id)
    return build_results_overview(user_id=target_user_id, limit=limit, offset=offset)


@router.get('/overview.csv')
def results_overview_csv_route(
    user_id: str | None = Query(default=None),
    scenario: str | None = Query(default=None),
    villain: str | None = Query(default=None),
    street: str | None = Query(default=None),
    position: str | None = Query(default=None),
    timer: str | None = Query(default=None),
    limit: int = Query(10000, ge=1, le=10000),
    current_user: UserAccount = Depends(get_current_user),
) -> Response:
    target_user_id = (user_id or current_user.user_id).strip()
    if target_user_id != current_user.user_id:
        ensure_user_access(current_user, target_user_id)
    rows = build_results_export_rows(
        user_id=target_user_id,
        scenario_id=scenario,
        villain_profile_id=villain,
        street=street,
        position=position,
        timer_label=timer,
        limit=limit,
    )


@router.get('/member-summary.csv')
def results_member_summary_csv_route(
    user_id: str | None = Query(default=None),
    current_user: UserAccount = Depends(get_current_user),
) -> Response:
    target_user_id = (user_id or current_user.user_id).strip()
    if target_user_id != current_user.user_id:
        ensure_user_access(current_user, target_user_id)
    filename, content, _ = member_summary_csv(
        user_id=target_user_id,
        visible_organization_ids=get_visible_organization_ids(current_user),
    )
    safe_filename = filename.replace('"', '').replace('\r', '').replace('\n', '')
    return Response(
        content=content,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{safe_filename}"'},
    )
    fieldnames = [
        'completed_at',
        'hand_id',
        'session_id',
        'scenario',
        'villain',
        'position',
        'timer',
        'final_street',
        'streets_played',
        'range_score',
        'action_score',
        'overall_score',
        'review_status',
        'flagged_for_review',
        'sent_to_coaches',
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="range-and-react-results.csv"'},
    )


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


@router.post('/hand/{hand_id}/flag')
def flag_hand_for_review_route(
    hand_id: str,
    payload: dict[str, Any],
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    flagged = bool(payload.get('flagged', True))
    member_note = str(payload.get('member_note') or '').strip() if isinstance(payload, dict) else None
    return {'review': set_hand_review_flag(hand_id, user=current_user, flagged=flagged, member_note=member_note)}


@router.patch('/hand/{hand_id}/review')
def update_hand_review_route(
    hand_id: str,
    payload: dict[str, Any],
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    return {
        'review': update_hand_review_note(
            hand_id,
            user=current_user,
            member_note=payload.get('member_note') if isinstance(payload, dict) else None,
            coach_note=payload.get('coach_note') if isinstance(payload, dict) else None,
            mark_reviewed=bool(payload.get('mark_reviewed')) if isinstance(payload, dict) else False,
        )
    }


@router.post('/review/send')
def send_flagged_hands_route(
    payload: dict[str, Any] | None = None,
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    hand_ids = None
    if isinstance(payload, dict) and isinstance(payload.get('hand_ids'), list):
        hand_ids = [str(value) for value in payload.get('hand_ids') or []]
    return send_flagged_hands_to_coaches(user=current_user, hand_ids=hand_ids)


@router.get('/review-queue')
def review_queue_route(
    current_user: UserAccount = Depends(get_current_user),
    limit: int = Query(250, ge=1, le=500),
) -> dict:
    return list_review_queue(user=current_user, limit=limit)


@router.get('/hand/{hand_id}/replay')
def hand_replay_route(hand_id: str, current_user: UserAccount = Depends(get_current_user)) -> dict:
    return build_hand_replay(hand_id, user=current_user)
