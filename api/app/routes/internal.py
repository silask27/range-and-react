from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from api.app.config import settings
from api.app.services.access_service import get_visible_organization_ids, get_visible_user_ids
from api.app.services.data_delivery_service import (
    build_delivery_files,
    list_due_data_delivery_preferences,
    mark_data_delivery_sent,
    send_data_delivery_files,
)
from api.app.services.email_service import email_delivery_enabled
from api.app.services.organization_service import get_organization

router = APIRouter(prefix='/internal', tags=['internal'])


def _require_cron_secret(secret: str | None) -> None:
    expected = settings.data_delivery_cron_secret
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Data delivery cron secret is not configured')
    if secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Invalid cron secret')


def _organization_label(organization_ids: list[str] | None) -> str:
    if organization_ids and len(organization_ids) == 1:
        org = get_organization(organization_ids[0])
        if org is not None:
            return str(org.get('name') or 'organization')
    return 'all-organizations' if organization_ids is None else 'organization'


def _selected_files(preference: dict) -> list[str]:
    files = []
    if preference.get('include_member_summary') or preference.get('include_cohort_summary'):
        files.append('member_summary')
    if preference.get('include_org_summary'):
        files.append('org_summary')
    return files


@router.post('/data-delivery/run-due')
def internal_run_due_data_delivery_route(x_cron_secret: str | None = Header(default=None)) -> dict:
    _require_cron_secret(x_cron_secret)
    due_items = list_due_data_delivery_preferences()
    attempted = 0
    sent = 0
    skipped = 0
    failed = 0
    deliveries: list[dict] = []

    for item in due_items:
        user = item['user']
        preference = item['preference']
        org_scope = get_visible_organization_ids(user)
        user_scope = get_visible_user_ids(user)
        files = build_delivery_files(
            user=user,
            selected_files=_selected_files(preference),
            cohort_id=preference.get('cohort_id'),
            organization_label=_organization_label(org_scope),
            visible_user_ids=user_scope,
            visible_organization_ids=org_scope,
        )
        if not files:
            skipped += 1
            deliveries.append({'user_id': user.user_id, 'status': 'skipped', 'detail': 'No deliverable files'})
            continue

        attempted += 1
        delivery = send_data_delivery_files(
            user=user,
            files=files,
            cadence=str(preference.get('cadence') or 'weekly'),
        )
        if delivery.status == 'sent':
            sent += 1
            mark_data_delivery_sent(user.user_id, cadence=str(preference.get('cadence') or 'weekly'))
        elif delivery.skipped and not email_delivery_enabled():
            skipped += 1
        else:
            failed += 1
        deliveries.append({
            'user_id': user.user_id,
            'status': delivery.status,
            'files': [file['filename'] for file in files],
            'detail': delivery.detail,
        })

    return {
        'due_count': len(due_items),
        'attempted': attempted,
        'sent': sent,
        'skipped': skipped,
        'failed': failed,
        'email_delivery_enabled': email_delivery_enabled(),
        'deliveries': deliveries,
    }
