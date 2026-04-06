from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response

from api.app.config import settings
from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.rate_limiter import limiter
from api.app.security import get_current_user
from api.app.services.audit_service import log_audit_event
from api.app.services.email_service import send_welcome_email
from api.app.services.auth_service import (
    authenticate_user,
    change_password,
    create_auth_session,
    create_owner_if_none,
    create_user,
    create_user_from_signup_invite,
    export_user_bundle,
    get_active_signup_invite_preview,
    list_external_identities,
    owner_exists,
    request_password_reset,
    reset_password_with_token,
    revoke_auth_token,
    set_user_active,
    update_display_name,
)
from api.app.services.organization_service import list_user_organizations

router = APIRouter(prefix='/auth', tags=['auth'])


def _serialize_user(user: UserAccount) -> dict:
    payload = asdict(user)
    payload['role'] = user.role.value
    return payload


def _send_welcome_for_user(user: UserAccount) -> dict:
    organizations = list_user_organizations(user.user_id)
    org_names = [org['name'] for org in organizations if org.get('name')]
    delivery = send_welcome_email(email=user.email, display_name=user.display_name, organization_names=org_names)
    return delivery.to_dict()


@router.get('/owner-exists')
def owner_exists_route() -> dict:
    return {'owner_exists': owner_exists()}


@router.get('/signup-invites/{invite_code}')
@limiter.limit('30/hour')
def signup_invite_preview_route(request: Request, response: Response, invite_code: str) -> dict:
    del request
    try:
        invite = get_active_signup_invite_preview(invite_code=invite_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {'invite': invite}


@router.post('/bootstrap-owner')
@limiter.limit('3/hour')
def bootstrap_owner_route(request: Request, response: Response, payload: dict = Body(...)) -> dict:
    del request
    email = str(payload.get('email') or '').strip()
    password = str(payload.get('password') or '')
    display_name = str(payload.get('display_name') or '').strip() or None

    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password are required')

    try:
        user = create_owner_if_none(email=email, password=password, display_name=display_name)
        session = create_auth_session(user)
        log_audit_event(action_type='owner_bootstrapped', actor=user, target_user_id=user.user_id, metadata={'email': user.email})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {'token': session.token, 'user': _serialize_user(session.user), 'welcome_email_delivery': _send_welcome_for_user(session.user)}


@router.post('/signup')
@limiter.limit('10/hour')
def signup_route(request: Request, response: Response, payload: dict = Body(...)) -> dict:
    del request
    email = str(payload.get('email') or '').strip()
    password = str(payload.get('password') or '')
    display_name = str(payload.get('display_name') or '').strip() or None
    invite_code = str(payload.get('invite_code') or '').strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password are required')
    if settings.require_signup_invite and not invite_code:
        raise HTTPException(status_code=400, detail='invite_code is required')

    try:
        if invite_code:
            user = create_user_from_signup_invite(
                invite_code=invite_code,
                email=email,
                password=password,
                display_name=display_name,
            )
        else:
            user = create_user(
                email=email,
                password=password,
                display_name=display_name,
                role=UserRole.MEMBER,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session = create_auth_session(user)
    log_audit_event(action_type='user_signed_up', actor=user, target_user_id=user.user_id, metadata={'email': user.email, 'role': user.role.value})
    return {'token': session.token, 'user': _serialize_user(session.user), 'welcome_email_delivery': _send_welcome_for_user(session.user)}


@router.post('/login')
@limiter.limit('10/minute')
def login_route(request: Request, response: Response, payload: dict = Body(...)) -> dict:
    del request
    email = str(payload.get('email') or '').strip()
    password = str(payload.get('password') or '')

    if not email or not password:
        raise HTTPException(status_code=400, detail='email and password are required')

    try:
        user = authenticate_user(email=email, password=password)
        session = create_auth_session(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {'token': session.token, 'user': _serialize_user(session.user)}


@router.post('/logout')
def logout_route(
    authorization: str | None = Header(default=None),
    current_user: UserAccount = Depends(get_current_user),
) -> dict:
    if authorization:
        _, _, token = authorization.partition(' ')
        if token.strip():
            revoke_auth_token(token.strip())
    log_audit_event(action_type='user_logged_out', actor=current_user, target_user_id=current_user.user_id)
    return {'ok': True}


@router.get('/me')
def me_route(current_user: UserAccount = Depends(get_current_user)) -> dict:
    return {
        'user': _serialize_user(current_user),
        'external_identities': list_external_identities(current_user.user_id),
        'organizations': list_user_organizations(current_user.user_id),
    }


@router.patch('/profile')
def update_profile_route(payload: dict = Body(...), current_user: UserAccount = Depends(get_current_user)) -> dict:
    try:
        updated = update_display_name(user_id=current_user.user_id, display_name=payload.get('display_name'))
        log_audit_event(action_type='profile_updated', actor=updated, target_user_id=updated.user_id, metadata={'display_name': updated.display_name})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'user': _serialize_user(updated)}


@router.post('/change-password')
def change_password_route(payload: dict = Body(...), current_user: UserAccount = Depends(get_current_user)) -> dict:
    current_password = str(payload.get('current_password') or '')
    new_password = str(payload.get('new_password') or '')
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail='current_password and new_password are required')
    try:
        change_password(user_id=current_user.user_id, current_password=current_password, new_password=new_password)
        log_audit_event(action_type='password_changed', actor=current_user, target_user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'ok': True, 'message': 'Password updated. Please log in again.'}


@router.post('/request-password-reset')
@limiter.limit('5/hour')
def request_password_reset_route(request: Request, response: Response, payload: dict = Body(...)) -> dict:
    del request
    email = str(payload.get('email') or '')
    if not email:
        raise HTTPException(status_code=400, detail='email is required')
    try:
        result = request_password_reset(email=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post('/reset-password')
@limiter.limit('10/hour')
def reset_password_route(request: Request, response: Response, payload: dict = Body(...)) -> dict:
    del request
    reset_token = str(payload.get('reset_token') or '')
    new_password = str(payload.get('new_password') or '')
    if not reset_token or not new_password:
        raise HTTPException(status_code=400, detail='reset_token and new_password are required')
    try:
        reset_password_with_token(reset_token=reset_token, new_password=new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'ok': True, 'message': 'Password reset complete. You can log in with your new password.'}


@router.post('/deactivate')
def deactivate_account_route(payload: dict = Body(default={}), current_user: UserAccount = Depends(get_current_user)) -> dict:
    confirm = bool(payload.get('confirm'))
    if not confirm:
        raise HTTPException(status_code=400, detail='confirm=true is required to deactivate the account')
    try:
        updated = set_user_active(user_id=current_user.user_id, is_active=False)
        log_audit_event(action_type='account_deactivated', actor=current_user, target_user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'user': updated}


@router.get('/export')
def export_account_route(current_user: UserAccount = Depends(get_current_user)) -> dict:
    try:
        payload = export_user_bundle(current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return payload
