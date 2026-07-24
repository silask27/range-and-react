from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

from api.app.models.enums import UserRole
from api.app.services.email_service import build_signup_invite_url
from api.app.services.organization_service import organization_has_access
from api.app.storage.db import DatabaseConnection, get_connection, json_dumps, json_loads


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(UTC)


def normalize_join_code(code: str) -> str:
    return ''.join(ch for ch in str(code or '').upper() if ch.isalnum())


def _hash_join_code(code: str) -> str:
    normalized = normalize_join_code(code)
    if not normalized:
        raise ValueError('join_code is required')
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _generate_join_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(16)).decode('ascii').rstrip('=')
    grouped = '-'.join(raw[index:index + 4] for index in range(0, len(raw), 4))
    return f'RNR-{grouped}'


def _clean_org_ids(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or '').strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _status_for_row(row) -> str:
    if not bool(row['is_active']) or row['revoked_at']:
        return 'revoked'
    expires_at = _parse_iso(row['expires_at'])
    if expires_at is not None and expires_at <= _utcnow():
        return 'expired'
    max_uses = row['max_uses']
    if max_uses is not None and int(row['use_count'] or 0) >= int(max_uses):
        return 'used_up'
    return 'active'


def _serialize_join_code(row, *, plain_code: str | None = None) -> dict[str, Any]:
    payload = {
        'join_code_id': row['join_code_id'],
        'organization_id': row['organization_id'],
        'membership_role': row['membership_role'],
        'is_active': bool(row['is_active']),
        'max_uses': row['max_uses'],
        'use_count': row['use_count'],
        'expires_at': row['expires_at'],
        'last_four': row['last_four'],
        'last_used_at': row['last_used_at'],
        'revoked_at': row['revoked_at'],
        'metadata': json_loads(row['metadata_json']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'status': _status_for_row(row),
    }
    if plain_code:
        payload['join_code'] = plain_code
        payload['join_url'] = build_signup_invite_url(plain_code)
    return payload


def list_organization_join_codes(*, organization_ids: Iterable[str] | None = None, active_only: bool = False) -> list[dict[str, Any]]:
    org_ids = _clean_org_ids(organization_ids)
    if organization_ids is not None and not org_ids:
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if org_ids:
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'organization_id IN ({placeholders})')
        params.extend(org_ids)
    if active_only:
        clauses.append('is_active = 1')
        clauses.append('revoked_at IS NULL')
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    with get_connection() as conn:
        rows = conn.execute(
            f'''
            SELECT *
            FROM organization_join_codes
            {where_sql}
            ORDER BY created_at DESC
            ''',
            tuple(params),
        ).fetchall()
    return [_serialize_join_code(row) for row in rows]


def rotate_organization_join_code(
    *,
    organization_id: str,
    created_by_user_id: str,
    expires_in_days: int = 30,
    max_uses: int | None = None,
) -> dict[str, Any]:
    org_id = str(organization_id or '').strip()
    creator_id = str(created_by_user_id or '').strip()
    if not org_id:
        raise ValueError('organization_id is required')
    if not creator_id:
        raise ValueError('created_by_user_id is required')

    bounded_days = max(1, min(int(expires_in_days or 30), 365))
    max_uses_clean = None if max_uses in {None, ''} else max(1, min(int(max_uses), 10000))
    now = _utcnow()
    now_iso = _iso(now)
    expires_at = _iso(now + timedelta(days=bounded_days))

    for _ in range(5):
        plain_code = _generate_join_code()
        normalized = normalize_join_code(plain_code)
        join_code_id = str(uuid4())
        try:
            with get_connection() as conn:
                org = conn.execute('SELECT 1 FROM organizations WHERE organization_id = ? LIMIT 1', (org_id,)).fetchone()
                if org is None:
                    raise ValueError('Unknown organization_id')
                creator = conn.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (creator_id,)).fetchone()
                if creator is None:
                    raise ValueError('Unknown created_by_user_id')
                conn.execute(
                    '''
                    UPDATE organization_join_codes
                    SET is_active = 0, revoked_at = ?, updated_at = ?
                    WHERE organization_id = ? AND is_active = 1 AND revoked_at IS NULL
                    ''',
                    (now_iso, now_iso, org_id),
                )
                conn.execute(
                    '''
                    INSERT INTO organization_join_codes (
                        join_code_id, organization_id, code_hash, created_by_user_id, membership_role,
                        is_active, max_uses, use_count, expires_at, last_four, last_used_at,
                        revoked_at, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'member', 1, ?, 0, ?, ?, NULL, NULL, '{}', ?, ?)
                    ''',
                    (
                        join_code_id,
                        org_id,
                        _hash_join_code(plain_code),
                        creator_id,
                        max_uses_clean,
                        expires_at,
                        normalized[-4:],
                        now_iso,
                        now_iso,
                    ),
                )
                row = conn.execute('SELECT * FROM organization_join_codes WHERE join_code_id = ?', (join_code_id,)).fetchone()
            if row is None:
                raise RuntimeError('Failed to create organization join code')
            return _serialize_join_code(row, plain_code=plain_code)
        except Exception as exc:
            if 'UNIQUE' in str(exc).upper() and 'CODE_HASH' in str(exc).upper():
                continue
            raise
    raise RuntimeError('Failed to generate a unique organization join code')


def revoke_active_organization_join_code(*, organization_id: str) -> dict[str, Any] | None:
    org_id = str(organization_id or '').strip()
    if not org_id:
        raise ValueError('organization_id is required')
    now_iso = _iso(_utcnow())
    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT *
            FROM organization_join_codes
            WHERE organization_id = ? AND is_active = 1 AND revoked_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            ''',
            (org_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            '''
            UPDATE organization_join_codes
            SET is_active = 0, revoked_at = ?, updated_at = ?
            WHERE join_code_id = ?
            ''',
            (now_iso, now_iso, row['join_code_id']),
        )
        updated = conn.execute('SELECT * FROM organization_join_codes WHERE join_code_id = ?', (row['join_code_id'],)).fetchone()
    return _serialize_join_code(updated) if updated is not None else None


def find_active_join_code_for_signup(conn: DatabaseConnection, code: str, *, now: datetime | None = None):
    normalized = normalize_join_code(code)
    if not normalized:
        raise ValueError('join_code is required')
    row = conn.execute(
        '''
        SELECT c.*, o.name AS organization_name, o.metadata_json AS organization_metadata_json
        FROM organization_join_codes c
        JOIN organizations o ON o.organization_id = c.organization_id
        WHERE c.code_hash = ?
        LIMIT 1
        ''',
        (_hash_join_code(normalized),),
    ).fetchone()
    if row is None:
        raise ValueError('Invalid invite code')
    if not bool(row['is_active']) or row['revoked_at']:
        raise ValueError('That organization join code is no longer active')
    current_time = now or _utcnow()
    expires_at = _parse_iso(row['expires_at'])
    if expires_at is not None and expires_at <= current_time:
        raise ValueError('That organization join code has expired')
    max_uses = row['max_uses']
    if max_uses is not None and int(row['use_count'] or 0) >= int(max_uses):
        raise ValueError('That organization join code has reached its use limit')
    if not organization_has_access(json_loads(row['organization_metadata_json'])):
        raise ValueError('This organization is paused or its trial has expired')
    return row


def get_active_organization_join_code_preview(*, join_code: str) -> dict[str, Any]:
    now = _utcnow()
    with get_connection() as conn:
        row = find_active_join_code_for_signup(conn, join_code, now=now)
    return {
        'invite_code': join_code,
        'code_type': 'organization_join_code',
        'email': None,
        'role': UserRole.MEMBER.value,
        'organization_id': row['organization_id'],
        'organization_name': row['organization_name'],
        'membership_role': 'member',
        'expires_at': row['expires_at'],
        'created_at': row['created_at'],
    }


def mark_join_code_used(conn: DatabaseConnection, *, join_code_id: str, used_at: datetime) -> None:
    timestamp = _iso(used_at)
    conn.execute(
        '''
        UPDATE organization_join_codes
        SET use_count = use_count + 1, last_used_at = ?, updated_at = ?
        WHERE join_code_id = ?
        ''',
        (timestamp, timestamp, join_code_id),
    )
