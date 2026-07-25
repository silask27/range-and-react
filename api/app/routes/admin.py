from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Response

from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.security import require_role
from api.app.services.access_service import (
    ensure_organization_access,
    ensure_user_access,
    get_visible_organization_ids,
    get_visible_user_ids,
    is_platform_admin,
    resolve_default_organization_id_for_user,
    shared_organization_ids,
)
from api.app.services.accountability_service import build_weekly_accountability_digest
from api.app.services.analytics_service import get_admin_analytics, invalidate_admin_analytics, invalidate_dashboard_overview
from api.app.services.assignment_service import count_assignments_with_progress, create_assignment, list_assignments_with_progress, summarize_assignments
from api.app.services.audit_service import count_audit_logs, list_audit_logs, log_audit_event
from api.app.services.cohort_service import (
    add_cohort_members,
    create_assignments_for_cohort,
    create_cohort,
    get_cohort,
    list_cohort_members,
    list_cohorts,
    remove_cohort_member,
    set_cohort_coaches,
)
from api.app.services.data_delivery_service import (
    build_delivery_files,
    cohort_member_summary_csv,
    cohort_summary_csv,
    get_data_delivery_preference,
    mark_data_delivery_sent,
    member_scope_summary_csv,
    org_cohort_summary_csv,
    save_data_delivery_preference,
    send_data_delivery_files,
    split_cohort_ids,
)
from api.app.services.email_service import build_signup_invite_url, email_delivery_enabled, send_accountability_digest_email, send_signup_invite_email
from api.app.services.auth_service import (
    count_users,
    count_users_by_role,
    create_signup_invite,
    create_signup_invite_batch,
    delete_signup_invite,
    delete_user_permanently,
    get_user_by_id,
    link_external_identity,
    list_signup_invite_batches,
    list_signup_invites,
    list_users,
    set_user_active,
    update_signup_invite_batch_delivery_count,
    update_user_role,
)
from api.app.services.organization_service import add_user_to_organization, create_organization, get_organization, list_organizations, update_organization_settings
from api.app.storage.memory_store import store

router = APIRouter(prefix='/admin', tags=['admin'])


def _optional_str(value: object, *, keep_empty: bool = False) -> str | None:
    if value is None:
        return '' if keep_empty else None
    clean = str(value).strip()
    if clean:
        return clean
    return '' if keep_empty else None



def _scope(current_user: UserAccount) -> tuple[list[str] | None, list[str] | None]:
    return get_visible_organization_ids(current_user), get_visible_user_ids(current_user)



def _visible_user_set(current_user: UserAccount) -> set[str] | None:
    user_ids = get_visible_user_ids(current_user)
    return set(user_ids) if user_ids is not None else None



def _filter_recent(items: list[dict], visible_user_ids: set[str] | None) -> list[dict]:
    if visible_user_ids is None:
        return items
    return [item for item in items if item.get('user_id') in visible_user_ids]



def _resolve_assignment_org(current_user: UserAccount, target_user_id: str, requested_organization_id: str | None) -> str | None:
    clean_requested = (requested_organization_id or '').strip() or None
    if is_platform_admin(current_user):
        return clean_requested

    shared_orgs = shared_organization_ids(current_user.user_id, target_user_id)
    if not shared_orgs:
        raise HTTPException(status_code=403, detail='Coaches can only assign work inside their organization')
    if clean_requested:
        if clean_requested not in set(shared_orgs):
            raise HTTPException(status_code=403, detail='That assignment organization is outside your organization scope')
        return clean_requested
    default_org = resolve_default_organization_id_for_user(current_user)
    if default_org and default_org in set(shared_orgs):
        return default_org
    if len(shared_orgs) == 1:
        return shared_orgs[0]
    raise HTTPException(status_code=400, detail='organization_id is required when the coach belongs to multiple organizations')



def _resolve_invite_org(current_user: UserAccount, requested_organization_id: str | None) -> str | None:
    clean_requested = (requested_organization_id or '').strip() or None
    if is_platform_admin(current_user):
        return clean_requested
    if clean_requested:
        return ensure_organization_access(current_user, clean_requested)
    default_org = resolve_default_organization_id_for_user(current_user)
    if default_org:
        return default_org
    raise HTTPException(status_code=400, detail='organization_id is required for coach-created invites')


def _decorate_invite(invite: dict, email_delivery: dict | None = None) -> dict:
    item = dict(invite)
    item['invite_url'] = build_signup_invite_url(item['invite_code'], email=item.get('email'))
    if email_delivery is not None:
        item['email_delivery'] = email_delivery
    return item


def _csv_response(filename: str, content: str) -> Response:
    safe_filename = filename.replace('"', '').replace('\r', '').replace('\n', '')
    return Response(
        content=content,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{safe_filename}"'},
    )


def _organization_label(current_user: UserAccount, organization_ids: list[str] | None) -> str:
    if organization_ids and len(organization_ids) == 1:
        org = get_organization(organization_ids[0])
        if org is not None:
            return str(org.get('name') or 'organization')
    if is_platform_admin(current_user):
        return 'all-organizations'
    return 'organization'


def _default_delivery_cohort_id(organization_ids: list[str] | None) -> str | None:
    cohorts = list_cohorts(organization_ids=organization_ids)
    return str(cohorts[0]['cohort_id']) if cohorts else None


def _validate_delivery_cohorts(current_user: UserAccount, cohort_id: str | list[str] | None) -> str | None:
    clean_ids = split_cohort_ids(cohort_id)
    if not clean_ids:
        return None
    for clean in clean_ids:
        cohort = get_cohort(clean)
        if cohort is None:
            raise HTTPException(status_code=404, detail='Cohort not found')
        ensure_organization_access(current_user, cohort['organization_id'])
    return ','.join(clean_ids)


def _selected_delivery_files(preference: dict) -> list[str]:
    files = []
    if preference.get('include_member_summary') or preference.get('include_cohort_summary'):
        files.append('member_summary')
    if preference.get('include_org_summary'):
        files.append('org_summary')
    return files


def _queue_invite_email(background_tasks: BackgroundTasks, invite: dict, current_user: UserAccount) -> dict:
    if not invite.get('email') or not email_delivery_enabled():
        delivery = send_signup_invite_email(
            email=invite.get('email'),
            invite_code=invite['invite_code'],
            invited_by_name=current_user.display_name or current_user.email,
            expires_at=invite.get('expires_at'),
        )
        return delivery.to_dict()
    organization_name = None
    if invite.get('organization_id'):
        organization = get_organization(str(invite['organization_id']))
        if organization is not None:
            organization_name = organization.get('name')
    background_tasks.add_task(
        send_signup_invite_email,
        email=invite.get('email'),
        invite_code=invite['invite_code'],
        organization_name=organization_name,
        invited_by_name=current_user.display_name or current_user.email,
        expires_at=invite.get('expires_at'),
    )
    return {'status': 'queued', 'provider': 'resend', 'skipped': False}



@router.get('/overview')
def admin_overview_route(background_tasks: BackgroundTasks, current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    org_scope, user_scope = _scope(current_user)
    visible_user_ids = set(user_scope) if user_scope is not None else None
    user_counts = count_users_by_role(organization_ids=org_scope, user_ids=user_scope)
    recent_sessions = _filter_recent(store.list_sessions(limit=50), visible_user_ids)[:10]
    recent_hands = _filter_recent(store.list_hands(limit=50), visible_user_ids)[:10]
    recent_results = _filter_recent(store.list_hand_results(hand_over=True, limit=50), visible_user_ids)[:10]
    assignment_summary = summarize_assignments(organization_ids=org_scope, target_user_ids=user_scope)
    analytics = get_admin_analytics(visible_user_ids=user_scope, visible_organization_ids=org_scope, background_tasks=background_tasks)

    return {
        'summary': {
            'users': user_counts,
            'recent_sessions_count': len(recent_sessions),
            'recent_hands_count': len(recent_hands),
            'recent_results_count': len(recent_results),
            'assignments': assignment_summary,
        },
        'recent_sessions': recent_sessions,
        'recent_hands': recent_hands,
        'recent_results': recent_results,
        'user_performance': [
            {
                'user_id': item['user_id'],
                'display_name': item['display_name'],
                'email': item['email'],
                'role': item['role'],
                'is_active': item['is_active'],
                'completed_hands': item['completed_hands'],
                'avg_overall_score': item['avg_overall_score'],
            }
            for item in analytics.get('users_needing_attention', [])[:12]
        ],
        'analytics_cache': analytics.get('_cache'),
    }


@router.get('/accountability-digest')
def admin_accountability_digest_route(
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
    days: int = Query(7, ge=1, le=31),
) -> dict:
    org_scope, user_scope = _scope(current_user)
    return {
        'digest': build_weekly_accountability_digest(
            visible_user_ids=user_scope,
            visible_organization_ids=org_scope,
            days=days,
        )
    }


@router.post('/accountability-digest/send')
def admin_send_accountability_digest_route(
    background_tasks: BackgroundTasks,
    payload: dict | None = Body(default=None),
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
) -> dict:
    org_scope, user_scope = _scope(current_user)
    days = int((payload or {}).get('days') or 7)
    digest = build_weekly_accountability_digest(
        visible_user_ids=user_scope,
        visible_organization_ids=org_scope,
        days=days,
    )
    background_tasks.add_task(
        send_accountability_digest_email,
        email=current_user.email,
        display_name=current_user.display_name or current_user.email,
        digest=digest,
    )
    return {
        'queued': email_delivery_enabled(),
        'recipient_count': 1,
        'digest': digest,
    }


@router.get('/users')
def admin_users_route(
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> dict:
    org_scope, user_scope = _scope(current_user)
    return {
        'users': list_users(limit=limit, offset=offset, user_ids=user_scope, organization_ids=org_scope, search=search, role=role, is_active=is_active),
        'meta': {
            'limit': limit,
            'offset': offset,
            'total': count_users(user_ids=user_scope, organization_ids=org_scope, search=search, role=role, is_active=is_active),
        },
    }


def _target_user_for_maintenance(current_user: UserAccount, target_user_id: str) -> UserAccount:
    target_user_id_clean = str(target_user_id or '').strip()
    if not target_user_id_clean:
        raise HTTPException(status_code=400, detail='user_id is required')
    target = get_user_by_id(target_user_id_clean)
    if target is None:
        raise HTTPException(status_code=404, detail='User not found')
    if target.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail='You cannot manage your own account from this table')
    if current_user.role != UserRole.OWNER:
        ensure_user_access(current_user, target.user_id)
    if current_user.role == UserRole.COACH:
        if target.role != UserRole.MEMBER:
            raise HTTPException(status_code=403, detail='Coaches can only manage member accounts in their organization')
    if current_user.role == UserRole.ADMIN and target.role == UserRole.OWNER:
        raise HTTPException(status_code=403, detail='Admins cannot manage owner accounts')
    return target


@router.post('/users/{user_id}/role')
def admin_update_user_role_route(user_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    target = _target_user_for_maintenance(current_user, user_id)
    role_raw = str(payload.get('role') or '').strip().lower()
    try:
        role = UserRole(role_raw)
        if current_user.role == UserRole.COACH and role != UserRole.MEMBER:
            raise HTTPException(status_code=403, detail='Coaches can only keep organization users as members')
        if current_user.role == UserRole.ADMIN and role == UserRole.OWNER:
            raise HTTPException(status_code=403, detail='Admins cannot assign owner access')
        updated = update_user_role(user_id=target.user_id, role=role)
        log_audit_event(action_type='user_role_updated', actor=current_user, target_user_id=target.user_id, metadata={'role': role.value})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'user': updated}


@router.post('/users/{user_id}/active')
def admin_update_user_active_route(user_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    target = _target_user_for_maintenance(current_user, user_id)
    is_active = bool(payload.get('is_active'))
    try:
        updated = set_user_active(user_id=target.user_id, is_active=is_active)
        log_audit_event(action_type='user_active_status_updated', actor=current_user, target_user_id=target.user_id, metadata={'is_active': is_active})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'user': updated}


@router.delete('/users/{user_id}')
def admin_delete_user_route(user_id: str, current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    target = _target_user_for_maintenance(current_user, user_id)
    try:
        deleted = delete_user_permanently(user_id=target.user_id)
        log_audit_event(action_type='user_deleted', actor=current_user, target_user_id=None, metadata={'deleted_user_id': target.user_id, 'email': deleted['email'], 'role': deleted['role']})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'deleted_user': deleted}


@router.post('/users/{user_id}/external-identities')
def admin_link_external_identity_route(user_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    if current_user.role != UserRole.OWNER:
        ensure_user_access(current_user, user_id)
    provider = str(payload.get('provider') or '').strip()
    external_user_id = str(payload.get('external_user_id') or '').strip()
    if not provider or not external_user_id:
        raise HTTPException(status_code=400, detail='provider and external_user_id are required')
    try:
        link_external_identity(
            user_id=user_id,
            provider=provider,
            external_user_id=external_user_id,
            external_email=payload.get('external_email'),
            metadata=payload.get('metadata') if isinstance(payload.get('metadata'), dict) else None,
        )
        log_audit_event(action_type='external_identity_linked', actor=current_user, target_user_id=user_id, metadata={'provider': provider, 'external_user_id': external_user_id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'ok': True}


@router.get('/signup-invites')
def admin_signup_invites_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)), limit: int = Query(100, ge=1, le=2500)) -> dict:
    org_scope, _ = _scope(current_user)
    invites = [_decorate_invite(invite) for invite in list_signup_invites(limit=limit, include_consumed=False, organization_ids=org_scope)]
    return {'invites': invites}


@router.get('/signup-invite-batches')
def admin_signup_invite_batches_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)), limit: int = Query(100, ge=1, le=500)) -> dict:
    org_scope, _ = _scope(current_user)
    return {'batches': list_signup_invite_batches(limit=limit, organization_ids=org_scope)}


@router.post('/signup-invites')
def admin_create_signup_invite_route(background_tasks: BackgroundTasks, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    email = (str(payload.get('email') or '').strip() or None)
    role_raw = str(payload.get('role') or UserRole.MEMBER.value).strip().lower()
    requested_org_id = (str(payload.get('organization_id') or '').strip() or None)
    membership_role = str(payload.get('membership_role') or 'member').strip().lower() or 'member'
    expires_in_days = int(payload.get('expires_in_days') or 14)

    try:
        role = UserRole(role_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid account type') from exc

    if current_user.role == UserRole.COACH and role != UserRole.MEMBER:
        raise HTTPException(status_code=403, detail='Coaches can only create member invites')
    if role == UserRole.OWNER:
        raise HTTPException(status_code=400, detail='Owner invites are not allowed')

    organization_id = _resolve_invite_org(current_user, requested_org_id)
    membership_role = membership_role if organization_id else 'member'
    if current_user.role == UserRole.COACH:
        membership_role = 'member'

    try:
        invite = create_signup_invite(
            created_by_user_id=current_user.user_id,
            email=email,
            role=role,
            organization_id=organization_id,
            membership_role=membership_role,
            expires_in_days=expires_in_days,
            metadata=payload.get('metadata') if isinstance(payload.get('metadata'), dict) else None,
        )
        log_audit_event(
            action_type='signup_invite_created',
            actor=current_user,
            target_user_id=None,
            organization_id=organization_id,
            metadata={'invite_id': invite['invite_id'], 'email': invite['email'], 'role': invite['role']},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    email_delivery = _queue_invite_email(background_tasks, invite, current_user)
    return {'invite': _decorate_invite(invite, email_delivery)}


@router.delete('/signup-invites/{invite_id}')
def admin_delete_signup_invite_route(invite_id: str, current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    org_scope, _ = _scope(current_user)
    invite_lookup = {item['invite_id']: item for item in list_signup_invites(limit=2500, organization_ids=org_scope)}
    invite = invite_lookup.get(str(invite_id).strip())
    if invite is None:
        raise HTTPException(status_code=404, detail='Invite not found in your scope')
    try:
        deleted = delete_signup_invite(invite_id=invite_id)
        log_audit_event(action_type='signup_invite_deleted', actor=current_user, organization_id=deleted.get('organization_id'), metadata={'invite_id': deleted['invite_id'], 'email': deleted.get('email'), 'role': deleted.get('role')})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'deleted_invite': _decorate_invite(deleted)}


@router.post('/signup-invites/bulk')
def admin_create_signup_invites_bulk_route(background_tasks: BackgroundTasks, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    requested_org_id = (str(payload.get('organization_id') or '').strip() or None)
    role_raw = str(payload.get('role') or UserRole.MEMBER.value).strip().lower()
    membership_role = str(payload.get('membership_role') or role_raw).strip().lower() or role_raw
    expires_in_days = int(payload.get('expires_in_days') or 14)
    raw_emails = payload.get('emails')
    emails: list[str] = []
    if isinstance(raw_emails, str):
        emails = [item.strip() for item in raw_emails.replace(',', '\n').splitlines() if item.strip()]
    elif isinstance(raw_emails, list):
        emails = [str(item).strip() for item in raw_emails if str(item).strip()]
    if not emails:
        raise HTTPException(status_code=400, detail='emails are required')

    try:
        role = UserRole(role_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid account type') from exc
    if current_user.role == UserRole.COACH and role != UserRole.MEMBER:
        raise HTTPException(status_code=403, detail='Coaches can only create member invites')
    if role == UserRole.OWNER:
        raise HTTPException(status_code=400, detail='Owner invites are not allowed')

    organization_id = _resolve_invite_org(current_user, requested_org_id)
    membership_role = membership_role if organization_id else 'member'
    if current_user.role == UserRole.COACH:
        membership_role = 'member'

    label = _optional_str(payload.get('label'))
    metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else None
    try:
        result = create_signup_invite_batch(
            created_by_user_id=current_user.user_id,
            emails=emails,
            role=role,
            organization_id=organization_id,
            membership_role=membership_role,
            expires_in_days=expires_in_days,
            label=label,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    decorated_invites = []
    delivery_count = 0
    for invite in result['invites']:
        email_delivery = _queue_invite_email(background_tasks, invite, current_user)
        if email_delivery.get('status') in {'queued', 'sent'}:
            delivery_count += 1
        decorated_invites.append(_decorate_invite(invite, email_delivery))
        log_audit_event(
            action_type='signup_invite_created',
            actor=current_user,
            target_user_id=None,
            organization_id=organization_id,
            metadata={'invite_id': invite['invite_id'], 'batch_id': result['batch']['batch_id'], 'email': invite['email'], 'role': invite['role'], 'bulk': True},
        )

    batch = update_signup_invite_batch_delivery_count(batch_id=result['batch']['batch_id'], email_delivery_queued_count=delivery_count)
    log_audit_event(
        action_type='signup_invite_batch_created',
        actor=current_user,
        target_user_id=None,
        organization_id=organization_id,
        metadata={'batch_id': batch['batch_id'], 'created_count': len(decorated_invites), 'failed_count': len(result['failures'])},
    )
    return {'batch': batch, 'invites': decorated_invites, 'failures': result['failures'], 'created_count': len(decorated_invites)}


@router.get('/assignments')
def admin_assignments_route(
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    search: str | None = None,
) -> dict:
    org_scope, user_scope = _scope(current_user)
    return {
        'assignments': list_assignments_with_progress(limit=limit, offset=offset, status=status, search=search, organization_ids=org_scope, target_user_ids=user_scope),
        'meta': {
            'limit': limit,
            'offset': offset,
            'total': count_assignments_with_progress(status=status, search=search, organization_ids=org_scope, target_user_ids=user_scope),
        },
    }


@router.get('/cohorts')
def admin_cohorts_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    org_scope, _ = _scope(current_user)
    return {'cohorts': list_cohorts(organization_ids=org_scope)}


@router.post('/cohorts')
def admin_create_cohort_route(payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    organization_id = _resolve_invite_org(current_user, (str(payload.get('organization_id') or '').strip() or None))
    if not organization_id:
        raise HTTPException(status_code=400, detail='organization_id is required')
    try:
        cohort = create_cohort(
            organization_id=organization_id,
            name=str(payload.get('name') or '').strip(),
            description=payload.get('description'),
            created_by_user_id=current_user.user_id,
            metadata=payload.get('metadata') if isinstance(payload.get('metadata'), dict) else None,
        )
        raw_coach_user_ids = payload.get('coach_user_ids')
        if isinstance(raw_coach_user_ids, list):
            coach_user_ids = [str(value) for value in raw_coach_user_ids]
            for coach_user_id in coach_user_ids:
                ensure_user_access(current_user, coach_user_id)
            set_cohort_coaches(cohort_id=cohort['cohort_id'], user_ids=coach_user_ids)
            cohort = get_cohort(cohort['cohort_id']) or cohort
        raw_user_ids = payload.get('user_ids')
        if isinstance(raw_user_ids, list) and raw_user_ids:
            user_ids = [str(value) for value in raw_user_ids]
            for user_id in user_ids:
                ensure_user_access(current_user, user_id)
            add_cohort_members(cohort_id=cohort['cohort_id'], user_ids=user_ids)
            cohort = get_cohort(cohort['cohort_id']) or cohort
        log_audit_event(action_type='cohort_created', actor=current_user, organization_id=organization_id, metadata={'cohort_id': cohort['cohort_id'], 'name': cohort['name']})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'cohort': cohort}


@router.patch('/cohorts/{cohort_id}/coaches')
def admin_set_cohort_coaches_route(cohort_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail='Cohort not found')
    ensure_organization_access(current_user, cohort['organization_id'])
    raw_user_ids = payload.get('user_ids')
    user_ids = [str(value) for value in raw_user_ids] if isinstance(raw_user_ids, list) else []
    for user_id in user_ids:
        ensure_user_access(current_user, user_id)
    try:
        result = set_cohort_coaches(cohort_id=cohort_id, user_ids=user_ids)
        log_audit_event(action_type='cohort_coaches_updated', actor=current_user, organization_id=cohort['organization_id'], metadata={'cohort_id': cohort_id, 'coach_count': len(user_ids)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get('/cohorts/{cohort_id}/members')
def admin_cohort_members_route(cohort_id: str, current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail='Cohort not found')
    ensure_organization_access(current_user, cohort['organization_id'])
    try:
        members = list_cohort_members(cohort_id=cohort_id, active_only=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {'cohort': cohort, 'members': members}


@router.post('/cohorts/{cohort_id}/members')
def admin_add_cohort_members_route(cohort_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail='Cohort not found')
    ensure_organization_access(current_user, cohort['organization_id'])
    raw_user_ids = payload.get('user_ids')
    user_ids = [str(value) for value in raw_user_ids] if isinstance(raw_user_ids, list) else ([str(payload.get('user_id'))] if payload.get('user_id') else [])
    for user_id in user_ids:
        ensure_user_access(current_user, user_id)
    try:
        result = add_cohort_members(cohort_id=cohort_id, user_ids=user_ids)
        log_audit_event(action_type='cohort_members_added', actor=current_user, organization_id=cohort['organization_id'], metadata={'cohort_id': cohort_id, 'added_count': len(result['added_user_ids'])})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.delete('/cohorts/{cohort_id}/members/{user_id}')
def admin_remove_cohort_member_route(cohort_id: str, user_id: str, current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail='Cohort not found')
    ensure_organization_access(current_user, cohort['organization_id'])
    ensure_user_access(current_user, user_id)
    try:
        result = remove_cohort_member(cohort_id=cohort_id, user_id=user_id)
        log_audit_event(action_type='cohort_member_removed', actor=current_user, target_user_id=user_id, organization_id=cohort['organization_id'], metadata={'cohort_id': cohort_id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post('/cohorts/{cohort_id}/assignments')
def admin_create_cohort_assignment_route(cohort_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail='Cohort not found')
    ensure_organization_access(current_user, cohort['organization_id'])
    try:
        result = create_assignments_for_cohort(
            cohort_id=cohort_id,
            created_by=current_user,
            title=str(payload.get('title') or '').strip(),
            description=payload.get('description'),
            scenario_id=(str(payload.get('scenario_id')).strip() or None) if payload.get('scenario_id') not in {None, ''} else None,
            villain_profile_id=(str(payload.get('villain_profile_id')).strip() or None) if payload.get('villain_profile_id') not in {None, ''} else None,
            repetition_target=int(payload.get('repetition_target') or 0),
            minimum_overall_score=float(payload['minimum_overall_score']) if payload.get('minimum_overall_score') not in {None, ''} else None,
            due_at=(str(payload.get('due_at')).strip() or None) if payload.get('due_at') is not None else None,
        )
        log_audit_event(action_type='cohort_assignment_created', actor=current_user, organization_id=cohort['organization_id'], metadata={'cohort_id': cohort_id, 'created_count': result['created_count'], 'title': payload.get('title')})
        for assignment in result.get('assignments') or []:
            invalidate_dashboard_overview(user_id=assignment['target_user_id'])
        org_scope, user_scope = _scope(current_user)
        invalidate_admin_analytics(visible_user_ids=user_scope, visible_organization_ids=org_scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post('/assignments')
def admin_create_assignment_route(payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    target_user_id = str(payload.get('target_user_id') or '').strip()
    if current_user.role == UserRole.COACH:
        ensure_user_access(current_user, target_user_id)
    organization_id = _resolve_assignment_org(current_user, target_user_id, (str(payload.get('organization_id') or '').strip() or None))
    try:
        assignment = create_assignment(
            created_by_user_id=current_user.user_id,
            target_user_id=target_user_id,
            organization_id=organization_id,
            title=str(payload.get('title') or '').strip(),
            description=payload.get('description'),
            scenario_id=(str(payload.get('scenario_id')).strip() or None) if payload.get('scenario_id') is not None else None,
            villain_profile_id=(str(payload.get('villain_profile_id')).strip() or None) if payload.get('villain_profile_id') is not None else None,
            repetition_target=int(payload.get('repetition_target') or 0),
            minimum_overall_score=float(payload['minimum_overall_score']) if payload.get('minimum_overall_score') not in {None, ''} else None,
            due_at=(str(payload.get('due_at')).strip() or None) if payload.get('due_at') is not None else None,
        )
        log_audit_event(action_type='assignment_created', actor=current_user, target_user_id=assignment['target_user_id'], organization_id=assignment.get('organization_id'), metadata={'assignment_id': assignment['assignment_id'], 'title': assignment['title']})
        invalidate_dashboard_overview(user_id=assignment['target_user_id'])
        if current_user.role in {UserRole.OWNER, UserRole.ADMIN}:
            invalidate_admin_analytics()
        else:
            org_scope, user_scope = _scope(current_user)
            invalidate_admin_analytics(visible_user_ids=user_scope, visible_organization_ids=org_scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'assignment': assignment}


@router.get('/audit-logs')
def admin_audit_logs_route(
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action_type: str | None = None,
    search: str | None = None,
) -> dict:
    org_scope, user_scope = _scope(current_user)
    return {
        'audit_logs': list_audit_logs(limit=limit, offset=offset, action_type=action_type, search=search, organization_ids=org_scope, user_ids=user_scope),
        'meta': {
            'limit': limit,
            'offset': offset,
            'total': count_audit_logs(action_type=action_type, search=search, organization_ids=org_scope, user_ids=user_scope),
        },
    }


@router.get('/analytics')
def admin_analytics_route(
    background_tasks: BackgroundTasks,
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
    refresh: bool = Query(default=False),
    cohort_id: str | None = Query(default=None),
) -> dict:
    org_scope, user_scope = _scope(current_user)
    clean_cohort_id = (cohort_id or '').strip() or None
    if clean_cohort_id:
        cohort = get_cohort(clean_cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail='Cohort not found.')
        ensure_organization_access(current_user, str(cohort['organization_id']))
        cohort_user_ids = [
            str(member['user_id'])
            for member in list_cohort_members(cohort_id=clean_cohort_id, active_only=True)
            if member.get('role') == UserRole.MEMBER.value
        ]
        if user_scope is not None:
            visible = set(user_scope)
            cohort_user_ids = [user_id for user_id in cohort_user_ids if user_id in visible]
        user_scope = cohort_user_ids
        org_scope = [str(cohort['organization_id'])]
    return get_admin_analytics(visible_user_ids=user_scope, visible_organization_ids=org_scope, background_tasks=background_tasks, force_refresh=refresh)


@router.get('/member-results.csv')
def admin_member_results_csv_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> Response:
    org_scope, user_scope = _scope(current_user)
    filename, content, _ = member_scope_summary_csv(
        organization_label=_organization_label(current_user, org_scope),
        visible_user_ids=user_scope,
        visible_organization_ids=org_scope,
    )
    return _csv_response(filename, content)


@router.get('/cohort-members-summary.csv')
def admin_cohort_members_summary_csv_route(
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
    cohort_ids: list[str] | None = Query(default=None),
) -> Response:
    org_scope, user_scope = _scope(current_user)
    clean_cohort_ids = split_cohort_ids(cohort_ids)
    if not clean_cohort_ids:
        default_cohort_id = _default_delivery_cohort_id(org_scope)
        clean_cohort_ids = [default_cohort_id] if default_cohort_id else []
    clean = _validate_delivery_cohorts(current_user, clean_cohort_ids)
    if not clean:
        raise HTTPException(status_code=400, detail='Select at least one cohort before downloading cohort members summary')
    filename, content, _ = cohort_member_summary_csv(
        cohort_ids=split_cohort_ids(clean),
        organization_label=_organization_label(current_user, org_scope),
        visible_user_ids=user_scope,
        visible_organization_ids=org_scope,
    )
    return _csv_response(filename, content)


@router.get('/cohort-summary.csv')
def admin_cohort_summary_csv_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> Response:
    org_scope, user_scope = _scope(current_user)
    filename, content, _ = org_cohort_summary_csv(
        organization_label=_organization_label(current_user, org_scope),
        visible_user_ids=user_scope,
        visible_organization_ids=org_scope,
    )
    return _csv_response(filename, content)


@router.get('/cohorts/{cohort_id}/summary.csv')
def admin_single_cohort_summary_csv_route(
    cohort_id: str,
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
) -> Response:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail='Cohort not found')
    ensure_organization_access(current_user, cohort['organization_id'])
    org_scope, user_scope = _scope(current_user)
    filename, content, _ = cohort_summary_csv(
        cohort_id=cohort_id,
        visible_user_ids=user_scope,
        visible_organization_ids=org_scope,
    )
    return _csv_response(filename, content)


@router.get('/data-delivery-preferences')
def admin_data_delivery_preferences_route(
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
) -> dict:
    org_scope, _ = _scope(current_user)
    return {
        'preference': get_data_delivery_preference(
            current_user,
            default_cohort_id=_default_delivery_cohort_id(org_scope),
        )
    }


@router.patch('/data-delivery-preferences')
def admin_update_data_delivery_preferences_route(
    payload: dict = Body(...),
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
) -> dict:
    cohort_id = _validate_delivery_cohorts(current_user, payload.get('cohort_id'))
    try:
        preference = save_data_delivery_preference(
            current_user,
            cadence=str(payload.get('cadence') or 'weekly'),
            include_member_summary=bool(payload.get('include_member_summary')),
            include_cohort_summary=False,
            include_org_summary=bool(payload.get('include_org_summary')),
            cohort_id=cohort_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'preference': preference}


@router.post('/data-delivery/send')
def admin_send_data_delivery_route(
    background_tasks: BackgroundTasks,
    payload: dict | None = Body(default=None),
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
) -> dict:
    org_scope, user_scope = _scope(current_user)
    preference = get_data_delivery_preference(
        current_user,
        default_cohort_id=_default_delivery_cohort_id(org_scope),
    )
    if isinstance(payload, dict) and payload:
        preference = {
            **preference,
            'cadence': str(payload.get('cadence') or preference.get('cadence') or 'weekly'),
            'include_member_summary': bool(payload.get('include_member_summary', preference.get('include_member_summary'))),
            'include_cohort_summary': bool(payload.get('include_cohort_summary', preference.get('include_cohort_summary'))),
            'include_org_summary': bool(payload.get('include_org_summary', preference.get('include_org_summary'))),
            'cohort_id': payload.get('cohort_id', preference.get('cohort_id')),
        }
    cohort_id = _validate_delivery_cohorts(current_user, preference.get('cohort_id'))
    files = build_delivery_files(
        user=current_user,
        selected_files=_selected_delivery_files(preference),
        cohort_id=cohort_id,
        organization_label=_organization_label(current_user, org_scope),
        visible_user_ids=user_scope,
        visible_organization_ids=org_scope,
    )
    if not files:
        raise HTTPException(status_code=400, detail='Select at least one CSV file to deliver')
    if email_delivery_enabled():
        background_tasks.add_task(
            send_data_delivery_files,
            user=current_user,
            files=files,
            cadence=str(preference.get('cadence') or 'weekly'),
        )
        mark_data_delivery_sent(current_user.user_id, cadence=str(preference.get('cadence') or 'weekly'))
        delivery = {'status': 'queued', 'provider': 'resend', 'skipped': False}
    else:
        delivery = send_data_delivery_files(
            user=current_user,
            files=files,
            cadence=str(preference.get('cadence') or 'weekly'),
        ).to_dict()
        if delivery.get('status') == 'sent':
            mark_data_delivery_sent(current_user.user_id, cadence=str(preference.get('cadence') or 'weekly'))
    return {
        'queued': email_delivery_enabled(),
        'recipient_count': 1,
        'files': [{'filename': item['filename']} for item in files],
        'delivery': delivery,
    }


@router.post('/cohort-summary/send')
def admin_send_cohort_summary_route(
    background_tasks: BackgroundTasks,
    payload: dict | None = Body(default=None),
    current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH)),
) -> dict:
    org_scope, user_scope = _scope(current_user)
    days = int((payload or {}).get('days') or 7)
    recipient_count = 0
    skipped_cohorts = 0
    for cohort in list_cohorts(organization_ids=org_scope):
        ensure_organization_access(current_user, cohort['organization_id'])
        members = [
            member for member in list_cohort_members(cohort_id=cohort['cohort_id'], active_only=True)
            if member.get('role') == UserRole.MEMBER.value and (user_scope is None or member['user_id'] in set(user_scope))
        ]
        coaches = cohort.get('coaches') or []
        if not coaches:
            skipped_cohorts += 1
            continue
        member_ids = [member['user_id'] for member in members]
        digest = build_weekly_accountability_digest(
            visible_user_ids=member_ids,
            visible_organization_ids=[cohort['organization_id']],
            days=days,
        )
        digest['cohort'] = {
            'cohort_id': cohort['cohort_id'],
            'name': cohort['name'],
            'member_count': len(members),
        }
        for coach in coaches:
            email = str(coach.get('email') or '').strip()
            if not email:
                continue
            background_tasks.add_task(
                send_accountability_digest_email,
                email=email,
                display_name=coach.get('display_name') or email,
                digest=digest,
            )
            recipient_count += 1
    return {
        'queued': email_delivery_enabled(),
        'recipient_count': recipient_count,
        'skipped_cohorts': skipped_cohorts,
    }


@router.get('/organizations')
def admin_organizations_route(current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    org_scope, _ = _scope(current_user)
    return {'organizations': list_organizations(limit=100, organization_ids=org_scope)}


@router.post('/organizations')
def admin_create_organization_route(payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER))) -> dict:
    metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
    for key in (
        'logo_url',
        'brand_name',
        'brand_accent',
        'invite_landing_copy',
        'coach_roster_note',
        'support_email',
        'access_status',
        'trial_starts_at',
        'trial_ends_at',
        'license_model',
        'monthly_minimum_cents',
        'included_active_users',
        'additional_user_cents',
    ):
        value = str(payload.get(key) or '').strip()
        if value:
            metadata[key] = value
    try:
        org = create_organization(
            name=str(payload.get('name') or '').strip(),
            slug=(str(payload.get('slug')).strip() or None) if payload.get('slug') is not None else None,
            external_provider=(str(payload.get('external_provider')).strip() or None) if payload.get('external_provider') is not None else None,
            external_org_id=(str(payload.get('external_org_id')).strip() or None) if payload.get('external_org_id') is not None else None,
            metadata=metadata,
        )
        log_audit_event(action_type='organization_created', actor=current_user, organization_id=org['organization_id'], metadata={'name': org['name'], 'slug': org['slug']})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'organization': org}


@router.patch('/organizations/{organization_id}')
def admin_update_organization_route(
    organization_id: str,
    payload: dict = Body(...),
    current_user: UserAccount = Depends(require_role(UserRole.OWNER)),
) -> dict:
    metadata_updates = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
    for key in (
        'logo_url',
        'brand_name',
        'brand_accent',
        'invite_landing_copy',
        'coach_roster_note',
        'support_email',
        'access_status',
        'trial_starts_at',
        'trial_ends_at',
        'license_model',
        'monthly_minimum_cents',
        'included_active_users',
        'additional_user_cents',
    ):
        if key in payload:
            metadata_updates[key] = str(payload.get(key) or '').strip()
    try:
        org = update_organization_settings(
            organization_id=organization_id,
            name=_optional_str(payload.get('name')) if 'name' in payload else None,
            slug=_optional_str(payload.get('slug')) if 'slug' in payload else None,
            external_provider=_optional_str(payload.get('external_provider'), keep_empty=True) if 'external_provider' in payload else None,
            external_org_id=_optional_str(payload.get('external_org_id'), keep_empty=True) if 'external_org_id' in payload else None,
            metadata_updates=metadata_updates,
        )
        log_audit_event(
            action_type='organization_settings_updated',
            actor=current_user,
            organization_id=organization_id,
            metadata={
                'access_status': org.get('access_status'),
                'trial_ends_at': org.get('trial_ends_at'),
                'name': org.get('name'),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'organization': org}


@router.post('/organizations/{organization_id}/members')
def admin_add_org_member_route(organization_id: str, payload: dict = Body(...), current_user: UserAccount = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.COACH))) -> dict:
    scoped_org_id = ensure_organization_access(current_user, organization_id)
    user_id = str(payload.get('user_id') or '').strip()
    membership_role = str(payload.get('membership_role') or 'member').strip().lower() or 'member'
    if not user_id:
        raise HTTPException(status_code=400, detail='user_id is required')
    if current_user.role != UserRole.OWNER:
        ensure_user_access(current_user, user_id)
    if current_user.role == UserRole.COACH and membership_role != 'member':
        raise HTTPException(status_code=403, detail='Coaches can only add members to their organization')
    try:
        membership = add_user_to_organization(organization_id=scoped_org_id, user_id=user_id, membership_role=membership_role)
        log_audit_event(action_type='organization_member_added', actor=current_user, target_user_id=user_id, organization_id=scoped_org_id, metadata={'membership_role': membership_role})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'membership': membership}
