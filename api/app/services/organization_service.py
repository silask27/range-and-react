from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable
from uuid import uuid4

from api.app.storage.db import get_connection, json_dumps, json_loads



def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()



def _slugify(value: str) -> str:
    value = ''.join(ch.lower() if ch.isalnum() else '-' for ch in value.strip())
    while '--' in value:
        value = value.replace('--', '-')
    return value.strip('-')[:80]



def _clean_ids(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or '').strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out



def _serialize_org_row(row) -> dict[str, Any]:
    metadata = json_loads(row['metadata_json'])
    access_status = organization_access_status(metadata)
    return {
        'organization_id': row['organization_id'],
        'name': row['name'],
        'slug': row['slug'],
        'external_provider': row['external_provider'],
        'external_org_id': row['external_org_id'],
        'metadata': metadata,
        'access_status': access_status,
        'trial_ends_at': metadata.get('trial_ends_at'),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            raw = f'{raw}T23:59:59+00:00'
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).astimezone(UTC)
    except ValueError:
        return None


def organization_access_status(metadata: dict[str, Any] | None) -> str:
    data = metadata or {}
    explicit_status = str(data.get('access_status') or 'active').strip().lower()
    if explicit_status == 'paused':
        return 'paused'
    trial_ends_at = _parse_iso_date(data.get('trial_ends_at'))
    if trial_ends_at is not None and trial_ends_at < datetime.now(UTC):
        return 'trial_expired'
    if trial_ends_at is not None:
        return 'trial'
    return 'active'


def organization_has_access(metadata: dict[str, Any] | None) -> bool:
    return organization_access_status(metadata) in {'active', 'trial'}


def user_has_active_organization_access(user_id: str) -> bool:
    organizations = list_user_organizations(user_id)
    if not organizations:
        return True
    return any(organization_has_access(org.get('metadata')) for org in organizations)


def update_organization_settings(
    *,
    organization_id: str,
    name: str | None = None,
    slug: str | None = None,
    external_provider: str | None = None,
    external_org_id: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean = str(organization_id or '').strip()
    if not clean:
        raise ValueError('organization_id is required')
    now = _utcnow_iso()
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM organizations WHERE organization_id = ? LIMIT 1', (clean,)).fetchone()
        if row is None:
            raise ValueError('Unknown organization_id')
        current_metadata = json_loads(row['metadata_json'])
        next_metadata = dict(current_metadata)
        for key, value in (metadata_updates or {}).items():
            clean_key = str(key or '').strip()
            if not clean_key:
                continue
            if value is None or value == '':
                next_metadata.pop(clean_key, None)
            else:
                next_metadata[clean_key] = value
        name_clean = str(name if name is not None else row['name']).strip()
        if not name_clean:
            raise ValueError('name is required')
        slug_clean = _slugify(slug if slug is not None else row['slug'])
        if not slug_clean:
            raise ValueError('slug is required')
        existing = conn.execute(
            'SELECT 1 FROM organizations WHERE slug = ? AND organization_id <> ? LIMIT 1',
            (slug_clean, clean),
        ).fetchone()
        if existing is not None:
            raise ValueError('An organization with that slug already exists')
        conn.execute(
            '''
            UPDATE organizations
            SET name = ?, slug = ?, external_provider = ?, external_org_id = ?, metadata_json = ?, updated_at = ?
            WHERE organization_id = ?
            ''',
            (
                name_clean,
                slug_clean,
                (str(external_provider).strip() or None) if external_provider is not None else row['external_provider'],
                (str(external_org_id).strip() or None) if external_org_id is not None else row['external_org_id'],
                json_dumps(next_metadata),
                now,
                clean,
            ),
        )
        updated = conn.execute('SELECT * FROM organizations WHERE organization_id = ? LIMIT 1', (clean,)).fetchone()
    if updated is None:
        raise RuntimeError('Failed to update organization')
    return _serialize_org_row(updated)



def create_organization(*, name: str, slug: str | None = None, external_provider: str | None = None, external_org_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    name_clean = (name or '').strip()
    if not name_clean:
        raise ValueError('name is required')
    slug_clean = _slugify(slug or name_clean)
    if not slug_clean:
        raise ValueError('slug is required')
    now = _utcnow_iso()
    organization_id = str(uuid4())
    with get_connection() as conn:
        existing = conn.execute('SELECT 1 FROM organizations WHERE slug = ? LIMIT 1', (slug_clean,)).fetchone()
        if existing is not None:
            raise ValueError('An organization with that slug already exists')
        conn.execute(
            '''
            INSERT INTO organizations (
                organization_id, name, slug, external_provider, external_org_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (organization_id, name_clean, slug_clean, external_provider, external_org_id, json_dumps(metadata or {}), now, now),
        )
        row = conn.execute('SELECT * FROM organizations WHERE organization_id = ?', (organization_id,)).fetchone()
    if row is None:
        raise RuntimeError('Failed to create organization')
    return _serialize_org_row(row)



def get_organization(organization_id: str) -> dict[str, Any] | None:
    clean = str(organization_id or '').strip()
    if not clean:
        return None
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM organizations WHERE organization_id = ? LIMIT 1', (clean,)).fetchone()
    return _serialize_org_row(row) if row is not None else None



def list_organizations(*, limit: int = 100, organization_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    org_ids = _clean_ids(organization_ids)
    if organization_ids is not None and not org_ids:
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if org_ids:
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'organization_id IN ({placeholders})')
        params.extend(org_ids)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    with get_connection() as conn:
        rows = conn.execute(f'SELECT * FROM organizations {where_sql} ORDER BY created_at ASC LIMIT ?', (*params, limit)).fetchall()
    orgs = [_serialize_org_row(row) for row in rows]
    for org in orgs:
        org['members'] = list_organization_members(org['organization_id'])
    return orgs



def add_user_to_organization(*, organization_id: str, user_id: str, membership_role: str = 'member') -> dict[str, Any]:
    org_id_clean = (organization_id or '').strip()
    user_id_clean = (user_id or '').strip()
    role_clean = (membership_role or 'member').strip().lower()
    if not org_id_clean or not user_id_clean:
        raise ValueError('organization_id and user_id are required')
    now = _utcnow_iso()
    with get_connection() as conn:
        org_exists = conn.execute('SELECT 1 FROM organizations WHERE organization_id = ? LIMIT 1', (org_id_clean,)).fetchone()
        if org_exists is None:
            raise ValueError('Unknown organization_id')
        user_exists = conn.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (user_id_clean,)).fetchone()
        if user_exists is None:
            raise ValueError('Unknown user_id')
        conn.execute(
            '''
            INSERT INTO organization_memberships (
                organization_membership_id, organization_id, user_id, membership_role, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (organization_id, user_id)
            DO UPDATE SET membership_role = EXCLUDED.membership_role
            ''',
            (str(uuid4()), org_id_clean, user_id_clean, role_clean, now),
        )
    return {
        'organization_id': org_id_clean,
        'user_id': user_id_clean,
        'membership_role': role_clean,
        'created_at': now,
    }



def list_organization_members(organization_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            '''
            SELECT m.organization_id, m.user_id, m.membership_role, m.created_at,
                   u.email, u.display_name, u.role, u.is_active
            FROM organization_memberships m
            JOIN users u ON u.user_id = m.user_id
            WHERE m.organization_id = ?
            ORDER BY m.created_at ASC
            ''',
            (organization_id,),
        ).fetchall()
    return [
        {
            'organization_id': row['organization_id'],
            'user_id': row['user_id'],
            'membership_role': row['membership_role'],
            'created_at': row['created_at'],
            'email': row['email'],
            'display_name': row['display_name'],
            'user_role': row['role'],
            'is_active': bool(row['is_active']),
        }
        for row in rows
    ]



def list_user_organizations(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            '''
            SELECT o.*, m.membership_role
            FROM organization_memberships m
            JOIN organizations o ON o.organization_id = m.organization_id
            WHERE m.user_id = ?
            ORDER BY o.created_at ASC
            ''',
            (user_id,),
        ).fetchall()
    out = []
    for row in rows:
        item = _serialize_org_row(row)
        item['membership_role'] = row['membership_role']
        out.append(item)
    return out
