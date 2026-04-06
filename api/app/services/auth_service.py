from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

from fastapi import HTTPException, status

from api.app.config import settings
from api.app.models.auth import AuthSession, UserAccount
from api.app.models.enums import UserRole
from api.app.services.email_service import send_password_reset_email
from api.app.storage.db import get_connection, json_dumps, json_loads

_PBKDF2_ITERATIONS = 240_000
_TOKEN_TTL_DAYS = int(os.getenv('VRT_AUTH_TOKEN_TTL_DAYS', '30'))
_PASSWORD_RESET_TTL_HOURS = int(os.getenv('VRT_PASSWORD_RESET_TTL_HOURS', '2'))


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or '@' not in normalized:
        raise ValueError('A valid email address is required')
    return normalized


def _normalize_display_name(display_name: str | None, email: str) -> str:
    candidate = (display_name or '').strip()
    if candidate:
        return candidate[:80]
    return email.split('@', 1)[0][:80]


def _hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError('Password must be at least 8 characters long')
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return 'pbkdf2_sha256${}${}${}'.format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode('ascii'),
        base64.b64encode(derived).decode('ascii'),
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_b64, hash_b64 = stored_hash.split('$', 3)
        if scheme != 'pbkdf2_sha256':
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _user_from_row(row) -> UserAccount:
    return UserAccount(
        user_id=row['user_id'],
        email=row['email'],
        display_name=row['display_name'],
        role=UserRole(row['role']),
        is_active=bool(row['is_active']),
    )


def create_user(
    *,
    email: str,
    password: str,
    display_name: str | None,
    role: UserRole = UserRole.MEMBER,
) -> UserAccount:
    normalized_email = _normalize_email(email)
    resolved_display_name = _normalize_display_name(display_name, normalized_email)
    password_hash = _hash_password(password)
    now = _iso(_utcnow())

    with get_connection() as conn:
        existing = conn.execute(
            'SELECT user_id FROM users WHERE lower(trim(email)) = ? LIMIT 1',
            (normalized_email,),
        ).fetchone()
        if existing is not None:
            raise ValueError('An account with that email already exists')

        user_id = str(uuid4())
        conn.execute(
            '''
            INSERT INTO users (user_id, email, password_hash, display_name, role, is_active, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, '{}')
            ''',
            (user_id, normalized_email, password_hash, resolved_display_name, role.value, now, now),
        )
        row = conn.execute(
            'SELECT user_id, email, display_name, role, is_active FROM users WHERE user_id = ?',
            (user_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError('Failed to create user')
    return _user_from_row(row)


def create_owner_if_none(*, email: str, password: str, display_name: str | None) -> UserAccount:
    with get_connection() as conn:
        existing_owner = conn.execute(
            'SELECT user_id FROM users WHERE role = ?',
            (UserRole.OWNER.value,),
        ).fetchone()
    if existing_owner is not None:
        raise ValueError('An owner account already exists')
    return create_user(email=email, password=password, display_name=display_name, role=UserRole.OWNER)





def _serialize_signup_invite(row) -> dict[str, Any]:
    expires_at = row['expires_at']
    consumed_at = row['consumed_at']
    is_expired = False
    if expires_at:
        is_expired = _parse_iso(expires_at) <= _utcnow()
    return {
        'invite_id': row['invite_id'],
        'invite_code': row['invite_code'],
        'email': row['email'],
        'role': row['role'],
        'organization_id': row['organization_id'],
        'membership_role': row['membership_role'],
        'created_by_user_id': row['created_by_user_id'],
        'expires_at': expires_at,
        'consumed_at': consumed_at,
        'consumed_by_user_id': row['consumed_by_user_id'],
        'metadata': json_loads(row['metadata_json']),
        'created_at': row['created_at'],
        'status': 'consumed' if consumed_at else ('expired' if is_expired else 'active'),
    }



def create_signup_invite(
    *,
    created_by_user_id: str,
    email: str | None,
    role: UserRole = UserRole.MEMBER,
    organization_id: str | None = None,
    membership_role: str = 'member',
    expires_in_days: int = 14,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if role == UserRole.OWNER:
        raise ValueError('Owner accounts cannot be created through invites')

    normalized_email = _normalize_email(email) if email else None
    membership_role_clean = (membership_role or 'member').strip().lower() or 'member'
    now = _utcnow()
    expires_at = _iso(now + timedelta(days=max(1, min(int(expires_in_days), 90))))
    invite_code = secrets.token_urlsafe(18)
    invite_id = str(uuid4())

    with get_connection() as conn:
        creator_exists = conn.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (created_by_user_id,)).fetchone()
        if creator_exists is None:
            raise ValueError('Unknown created_by_user_id')
        if organization_id:
            org_exists = conn.execute('SELECT 1 FROM organizations WHERE organization_id = ? LIMIT 1', (organization_id,)).fetchone()
            if org_exists is None:
                raise ValueError('Unknown organization_id')
        conn.execute(
            '''
            INSERT INTO signup_invites (
                invite_id, invite_code, created_by_user_id, email, role, organization_id,
                membership_role, expires_at, consumed_at, consumed_by_user_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            ''',
            (
                invite_id,
                invite_code,
                created_by_user_id,
                normalized_email,
                role.value,
                organization_id,
                membership_role_clean,
                expires_at,
                json_dumps(metadata or {}),
                _iso(now),
            ),
        )
        row = conn.execute('SELECT * FROM signup_invites WHERE invite_id = ?', (invite_id,)).fetchone()

    if row is None:
        raise RuntimeError('Failed to create invite')
    return _serialize_signup_invite(row)



def list_signup_invites(*, limit: int = 100, include_consumed: bool = True, organization_ids: Iterable[str] | None = None, created_by_user_id: str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    org_ids = [str(value).strip() for value in (organization_ids or []) if str(value).strip()]
    clauses: list[str] = []
    params: list[Any] = []
    if not include_consumed:
        clauses.append('consumed_at IS NULL')
    if org_ids:
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'organization_id IN ({placeholders})')
        params.extend(org_ids)
    if created_by_user_id:
        clauses.append('created_by_user_id = ?')
        params.append(str(created_by_user_id).strip())
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    query = f'SELECT * FROM signup_invites{where_sql} ORDER BY created_at DESC LIMIT ?'
    with get_connection() as conn:
        rows = conn.execute(query, (*params, limit)).fetchall()
    return [_serialize_signup_invite(row) for row in rows]




def get_active_signup_invite_preview(*, invite_code: str) -> dict[str, Any]:
    code = (invite_code or '').strip()
    if not code:
        raise ValueError('invite_code is required')
    now = _utcnow()
    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT i.invite_id, i.invite_code, i.email, i.role, i.organization_id, i.membership_role, i.expires_at,
                   i.consumed_at, i.created_at, o.name AS organization_name
            FROM signup_invites i
            LEFT JOIN organizations o ON o.organization_id = i.organization_id
            WHERE i.invite_code = ?
            LIMIT 1
            ''',
            (code,),
        ).fetchone()
    if row is None:
        raise ValueError('Invalid invite code')
    if row['consumed_at']:
        raise ValueError('That invite has already been used')
    if row['expires_at'] and _parse_iso(row['expires_at']) <= now:
        raise ValueError('That invite has expired')
    return {
        'invite_code': row['invite_code'],
        'email': row['email'],
        'role': row['role'],
        'organization_id': row['organization_id'],
        'organization_name': row['organization_name'],
        'membership_role': row['membership_role'],
        'expires_at': row['expires_at'],
        'created_at': row['created_at'],
    }


def create_user_from_signup_invite(
    *,
    invite_code: str,
    email: str,
    password: str,
    display_name: str | None,
) -> UserAccount:
    normalized_email = _normalize_email(email)
    resolved_display_name = _normalize_display_name(display_name, normalized_email)
    password_hash = _hash_password(password)
    code = (invite_code or '').strip()
    if not code:
        raise ValueError('invite_code is required')
    now = _utcnow()

    with get_connection() as conn:
        row = conn.execute('SELECT * FROM signup_invites WHERE invite_code = ? LIMIT 1', (code,)).fetchone()
        if row is None:
            raise ValueError('Invalid invite code')
        if row['consumed_at']:
            raise ValueError('That invite has already been used')
        if row['expires_at'] and _parse_iso(row['expires_at']) <= now:
            raise ValueError('That invite has expired')
        invited_email = row['email']
        if invited_email and invited_email != normalized_email:
            raise ValueError('This invite is tied to a different email address')

        existing = conn.execute(
            'SELECT user_id FROM users WHERE lower(trim(email)) = ? LIMIT 1',
            (normalized_email,),
        ).fetchone()
        if existing is not None:
            raise ValueError('An account with that email already exists')

        user_id = str(uuid4())
        timestamp = _iso(now)
        role = UserRole(row['role'])
        conn.execute(
            '''
            INSERT INTO users (user_id, email, password_hash, display_name, role, is_active, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, '{}')
            ''',
            (user_id, normalized_email, password_hash, resolved_display_name, role.value, timestamp, timestamp),
        )

        organization_id = row['organization_id']
        if organization_id:
            conn.execute(
                '''
                INSERT INTO organization_memberships (
                    organization_membership_id, organization_id, user_id, membership_role, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (organization_id, user_id)
                DO UPDATE SET membership_role = EXCLUDED.membership_role
                ''',
                (str(uuid4()), organization_id, user_id, row['membership_role'] or 'member', timestamp),
            )

        conn.execute(
            'UPDATE signup_invites SET consumed_at = ?, consumed_by_user_id = ? WHERE invite_id = ?',
            (timestamp, user_id, row['invite_id']),
        )
        user_row = conn.execute(
            'SELECT user_id, email, display_name, role, is_active FROM users WHERE user_id = ?',
            (user_id,),
        ).fetchone()

    if user_row is None:
        raise RuntimeError('Failed to create user from invite')
    return _user_from_row(user_row)

def authenticate_user(*, email: str, password: str) -> UserAccount:
    normalized_email = _normalize_email(email)
    with get_connection() as conn:
        row = conn.execute(
            'SELECT user_id, email, display_name, role, is_active, password_hash FROM users WHERE lower(trim(email)) = ? ORDER BY created_at ASC LIMIT 1',
            (normalized_email,),
        ).fetchone()

    if row is None or not _verify_password(password, row['password_hash']):
        raise ValueError('Invalid email or password')
    if not bool(row['is_active']):
        raise ValueError('This account is inactive')
    return UserAccount(
        user_id=row['user_id'],
        email=row['email'],
        display_name=row['display_name'],
        role=UserRole(row['role']),
        is_active=bool(row['is_active']),
    )


def create_auth_session(user: UserAccount) -> AuthSession:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = _utcnow()
    expires_at = now + timedelta(days=_TOKEN_TTL_DAYS)

    with get_connection() as conn:
        conn.execute(
            '''
            INSERT INTO auth_tokens (token_hash, user_id, expires_at, created_at, last_used_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (token_hash, user.user_id, _iso(expires_at), _iso(now), _iso(now)),
        )

    return AuthSession(token=token, user=user)


def revoke_auth_token(token: str) -> None:
    with get_connection() as conn:
        conn.execute('DELETE FROM auth_tokens WHERE token_hash = ?', (_hash_token(token),))


def revoke_all_auth_tokens_for_user(user_id: str) -> None:
    with get_connection() as conn:
        conn.execute('DELETE FROM auth_tokens WHERE user_id = ?', (user_id,))


def get_user_by_token(token: str) -> UserAccount:
    token_hash = _hash_token(token)
    now = _utcnow()
    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT u.user_id, u.email, u.display_name, u.role, u.is_active, t.expires_at
            FROM auth_tokens t
            JOIN users u ON u.user_id = t.user_id
            WHERE t.token_hash = ?
            ''',
            (token_hash,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')

        expires_at = _parse_iso(row['expires_at'])
        if expires_at <= now:
            conn.execute('DELETE FROM auth_tokens WHERE token_hash = ?', (token_hash,))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired')

        if not bool(row['is_active']):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Account is inactive')

        conn.execute(
            'UPDATE auth_tokens SET last_used_at = ? WHERE token_hash = ?',
            (_iso(now), token_hash),
        )

    return UserAccount(
        user_id=row['user_id'],
        email=row['email'],
        display_name=row['display_name'],
        role=UserRole(row['role']),
        is_active=bool(row['is_active']),
    )


def get_user_by_id(user_id: str) -> UserAccount | None:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT user_id, email, display_name, role, is_active FROM users WHERE user_id = ?',
            (user_id,),
        ).fetchone()
    return _user_from_row(row) if row is not None else None


def user_has_elevated_access(user: UserAccount) -> bool:
    return user.role in {UserRole.OWNER, UserRole.ADMIN, UserRole.COACH}


def ensure_can_access_owner_resource(owner_user_id: str | None, current_user: UserAccount) -> None:
    if owner_user_id is None:
        return
    if owner_user_id == current_user.user_id:
        return
    if user_has_elevated_access(current_user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You do not have access to this resource')


def owner_exists() -> bool:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT 1 FROM users WHERE role = ? LIMIT 1',
            (UserRole.OWNER.value,),
        ).fetchone()
    return row is not None


def link_external_identity(
    *,
    user_id: str,
    provider: str,
    external_user_id: str,
    external_email: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    provider_clean = provider.strip().lower()
    external_user_id_clean = external_user_id.strip()
    if not provider_clean or not external_user_id_clean:
        raise ValueError('provider and external_user_id are required')
    now = _iso(_utcnow())
    with get_connection() as conn:
        conn.execute(
            '''
            INSERT INTO external_identities (
                external_identity_id, user_id, provider, external_user_id, external_email, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (provider, external_user_id)
            DO UPDATE SET user_id = EXCLUDED.user_id,
                          external_email = EXCLUDED.external_email,
                          metadata_json = EXCLUDED.metadata_json
            ''',
            (
                str(uuid4()),
                user_id,
                provider_clean,
                external_user_id_clean,
                external_email,
                json_dumps(metadata or {}),
                now,
            ),
        )


def list_external_identities(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT provider, external_user_id, external_email, metadata_json, created_at FROM external_identities WHERE user_id = ? ORDER BY created_at ASC',
            (user_id,),
        ).fetchall()
    return [
        {
            'provider': row['provider'],
            'external_user_id': row['external_user_id'],
            'external_email': row['external_email'],
            'metadata': json_loads(row['metadata_json']),
            'created_at': row['created_at'],
        }
        for row in rows
    ]


def _build_user_filters(*, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None, search: str | None = None, role: str | None = None, is_active: bool | None = None) -> tuple[str, str, list[Any]]:
    org_ids = [str(value).strip() for value in (organization_ids or []) if str(value).strip()]
    scoped_user_ids = [str(value).strip() for value in (user_ids or []) if str(value).strip()]
    clauses: list[str] = []
    params: list[Any] = []
    join_sql = ''
    if org_ids:
        join_sql += ' JOIN organization_memberships m ON m.user_id = u.user_id'
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'm.organization_id IN ({placeholders})')
        params.extend(org_ids)
    if scoped_user_ids:
        placeholders = ', '.join('?' for _ in scoped_user_ids)
        clauses.append(f'u.user_id IN ({placeholders})')
        params.extend(scoped_user_ids)
    search_clean = (search or '').strip().lower()
    if search_clean:
        like = f'%{search_clean}%'
        clauses.append('(lower(u.email) LIKE ? OR lower(COALESCE(u.display_name, "")) LIKE ?)')
        params.extend((like, like))
    role_clean = (role or '').strip().lower()
    if role_clean:
        clauses.append('u.role = ?')
        params.append(role_clean)
    if is_active is not None:
        clauses.append('u.is_active = ?')
        params.append(1 if is_active else 0)
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    return join_sql, where_sql, params


def count_users(*, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None, search: str | None = None, role: str | None = None, is_active: bool | None = None) -> int:
    join_sql, where_sql, params = _build_user_filters(organization_ids=organization_ids, user_ids=user_ids, search=search, role=role, is_active=is_active)
    query = f'SELECT COUNT(DISTINCT u.user_id) AS count FROM users u{join_sql}{where_sql}'
    with get_connection() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
    return int(row['count'] or 0) if row is not None else 0


def list_users(*, limit: int = 100, offset: int = 0, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None, search: str | None = None, role: str | None = None, is_active: bool | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    join_sql, where_sql, params = _build_user_filters(organization_ids=organization_ids, user_ids=user_ids, search=search, role=role, is_active=is_active)
    select_sql = 'SELECT DISTINCT u.user_id, u.email, u.display_name, u.role, u.is_active, u.created_at, u.updated_at, u.deactivated_at'
    query = f'{select_sql} FROM users u{join_sql}{where_sql} ORDER BY u.created_at ASC LIMIT ? OFFSET ?'
    with get_connection() as conn:
        rows = conn.execute(query, (*params, limit, offset)).fetchall()
    return [
        {
            'user_id': row['user_id'],
            'email': row['email'],
            'display_name': row['display_name'],
            'role': row['role'],
            'is_active': bool(row['is_active']),
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'deactivated_at': row['deactivated_at'],
        }
        for row in rows
    ]


def update_user_role(*, user_id: str, role: UserRole) -> dict[str, Any]:
    now = _iso(_utcnow())
    with get_connection() as conn:
        conn.execute('UPDATE users SET role = ?, updated_at = ? WHERE user_id = ?', (role.value, now, user_id))
        row = conn.execute('SELECT user_id, email, display_name, role, is_active, created_at, updated_at, deactivated_at FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown user_id')
    return {
        'user_id': row['user_id'],
        'email': row['email'],
        'display_name': row['display_name'],
        'role': row['role'],
        'is_active': bool(row['is_active']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'deactivated_at': row['deactivated_at'],
    }


def set_user_active(*, user_id: str, is_active: bool) -> dict[str, Any]:
    now = _iso(_utcnow())
    deactivated_at = None if is_active else now
    with get_connection() as conn:
        conn.execute(
            'UPDATE users SET is_active = ?, deactivated_at = ?, updated_at = ? WHERE user_id = ?',
            (1 if is_active else 0, deactivated_at, now, user_id),
        )
        row = conn.execute(
            'SELECT user_id, email, display_name, role, is_active, created_at, updated_at, deactivated_at FROM users WHERE user_id = ?',
            (user_id,),
        ).fetchone()
    if row is None:
        raise ValueError('Unknown user_id')
    if not is_active:
        revoke_all_auth_tokens_for_user(user_id)
    return {
        'user_id': row['user_id'],
        'email': row['email'],
        'display_name': row['display_name'],
        'role': row['role'],
        'is_active': bool(row['is_active']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'deactivated_at': row['deactivated_at'],
    }


def update_display_name(*, user_id: str, display_name: str | None) -> UserAccount:
    now = _iso(_utcnow())
    clean = (display_name or '').strip()[:80] or None
    with get_connection() as conn:
        conn.execute('UPDATE users SET display_name = ?, updated_at = ? WHERE user_id = ?', (clean, now, user_id))
        row = conn.execute('SELECT user_id, email, display_name, role, is_active FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown user_id')
    return _user_from_row(row)


def change_password(*, user_id: str, current_password: str, new_password: str) -> None:
    with get_connection() as conn:
        row = conn.execute('SELECT password_hash FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown user_id')
    if not _verify_password(current_password, row['password_hash']):
        raise ValueError('Current password is incorrect')
    _set_password(user_id=user_id, new_password=new_password)


def _set_password(*, user_id: str, new_password: str) -> None:
    password_hash = _hash_password(new_password)
    now = _iso(_utcnow())
    with get_connection() as conn:
        conn.execute('UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?', (password_hash, now, user_id))
    revoke_all_auth_tokens_for_user(user_id)


def request_password_reset(*, email: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    reset_token: str | None = None
    now = _utcnow()
    expires_at = now + timedelta(hours=_PASSWORD_RESET_TTL_HOURS)
    display_name: str | None = None
    with get_connection() as conn:
        row = conn.execute('SELECT user_id, email, display_name, is_active FROM users WHERE lower(trim(email)) = ? ORDER BY created_at ASC LIMIT 1', (normalized_email,)).fetchone()
        if row is None or not bool(row['is_active']):
            return {'ok': True, 'message': 'If that email exists, we sent a password reset link.'}
        token = secrets.token_urlsafe(32)
        reset_token = token
        display_name = row['display_name']
        conn.execute('DELETE FROM password_reset_tokens WHERE user_id = ?', (row['user_id'],))
        conn.execute(
            'INSERT INTO password_reset_tokens (reset_token_hash, user_id, expires_at, created_at, consumed_at) VALUES (?, ?, ?, ?, NULL)',
            (_hash_token(token), row['user_id'], _iso(expires_at), _iso(now)),
        )
    delivery = send_password_reset_email(
        email=normalized_email,
        reset_token=reset_token,
        expires_at=_iso(expires_at),
        display_name=display_name,
    )
    payload: dict[str, Any] = {
        'ok': True,
        'message': 'If that email exists, we sent a password reset link.',
        'delivery': delivery.to_dict(),
    }
    if settings.password_reset_returns_token:
        payload['reset_token'] = reset_token
        payload['expires_at'] = _iso(expires_at)
    return payload


def reset_password_with_token(*, reset_token: str, new_password: str) -> None:
    token_hash = _hash_token((reset_token or '').strip())
    now = _utcnow()
    with get_connection() as conn:
        row = conn.execute(
            'SELECT user_id, expires_at, consumed_at FROM password_reset_tokens WHERE reset_token_hash = ?',
            (token_hash,),
        ).fetchone()
        if row is None:
            raise ValueError('Invalid password reset token')
        if row['consumed_at']:
            raise ValueError('Password reset token has already been used')
        if _parse_iso(row['expires_at']) <= now:
            raise ValueError('Password reset token has expired')
        conn.execute('UPDATE password_reset_tokens SET consumed_at = ? WHERE reset_token_hash = ?', (_iso(now), token_hash))
    _set_password(user_id=row['user_id'], new_password=new_password)


def export_user_bundle(user_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        user_row = conn.execute(
            'SELECT user_id, email, display_name, role, is_active, created_at, updated_at, deactivated_at FROM users WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        if user_row is None:
            raise ValueError('Unknown user_id')
        sessions = [json_loads(row['payload_json']) for row in conn.execute('SELECT payload_json FROM sessions WHERE user_id = ? ORDER BY created_at ASC', (user_id,)).fetchall()]
        hands = [json_loads(row['payload_json']) for row in conn.execute('SELECT payload_json FROM hands WHERE user_id = ? ORDER BY created_at ASC', (user_id,)).fetchall()]
        hand_results = [
            {
                'hand_id': row['hand_id'],
                'session_id': row['session_id'],
                'scenario_id': row['scenario_id'],
                'villain_profile_id': row['villain_profile_id'],
                'status': row['status'],
                'street': row['street'],
                'ui_gate': row['ui_gate'],
                'hand_over': bool(row['hand_over']),
                'total_live_combos': row['total_live_combos'],
                'started_at': row['started_at'],
                'updated_at': row['updated_at'],
                'completed_at': row['completed_at'],
                'ranging_score': row['ranging_score'],
                'response_score': row['response_score'],
                'overall_score': row['overall_score'],
                'metadata': json_loads(row['metadata_json']),
            }
            for row in conn.execute(
                'SELECT * FROM hand_results WHERE user_id = ? ORDER BY started_at ASC',
                (user_id,),
            ).fetchall()
        ]
        assignments = [
            {
                'assignment_id': row['assignment_id'],
                'title': row['title'],
                'description': row['description'],
                'scenario_id': row['scenario_id'],
                'villain_profile_id': row['villain_profile_id'],
                'repetition_target': row['repetition_target'],
                'minimum_overall_score': row['minimum_overall_score'],
                'due_at': row['due_at'],
                'status': row['status'],
                'metadata': json_loads(row['metadata_json']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }
            for row in conn.execute('SELECT * FROM assignments WHERE target_user_id = ? ORDER BY created_at ASC', (user_id,)).fetchall()
        ]
    return {
        'user': {
            'user_id': user_row['user_id'],
            'email': user_row['email'],
            'display_name': user_row['display_name'],
            'role': user_row['role'],
            'is_active': bool(user_row['is_active']),
            'created_at': user_row['created_at'],
            'updated_at': user_row['updated_at'],
            'deactivated_at': user_row['deactivated_at'],
        },
        'external_identities': list_external_identities(user_id),
        'sessions': sessions,
        'hands': hands,
        'hand_results': hand_results,
        'assignments': assignments,
    }


def count_users_by_role(*, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None) -> dict[str, int]:
    counts = {role.value: 0 for role in UserRole}
    org_ids = [str(value).strip() for value in (organization_ids or []) if str(value).strip()]
    scoped_user_ids = [str(value).strip() for value in (user_ids or []) if str(value).strip()]
    clauses: list[str] = []
    params: list[Any] = []
    join_sql = ''
    from_sql = ' FROM users u'
    if org_ids:
        join_sql += ' JOIN organization_memberships m ON m.user_id = u.user_id'
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'm.organization_id IN ({placeholders})')
        params.extend(org_ids)
    if scoped_user_ids:
        placeholders = ', '.join('?' for _ in scoped_user_ids)
        clauses.append(f'u.user_id IN ({placeholders})')
        params.extend(scoped_user_ids)
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    query = f'SELECT u.role, COUNT(DISTINCT u.user_id) AS count{from_sql}{join_sql}{where_sql} GROUP BY u.role'
    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    for row in rows:
        counts[str(row['role'])] = int(row['count'])
    counts['total'] = sum(value for key, value in counts.items() if key != 'total')
    return counts
