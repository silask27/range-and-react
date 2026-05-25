from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable
from uuid import uuid4

from api.app.models.auth import UserAccount
from api.app.storage.db import get_connection, json_dumps, json_loads



def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()



def log_audit_event(*, action_type: str, actor: UserAccount | None, target_user_id: str | None = None, organization_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    action_clean = (action_type or '').strip().lower()
    if not action_clean:
        raise ValueError('action_type is required')
    now = _utcnow_iso()
    audit_log_id = str(uuid4())
    with get_connection() as conn:
        conn.execute(
            '''
            INSERT INTO audit_logs (
                audit_log_id, actor_user_id, actor_role, target_user_id, organization_id, action_type, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                audit_log_id,
                actor.user_id if actor else None,
                actor.role.value if actor else None,
                target_user_id,
                organization_id,
                action_clean,
                json_dumps(metadata or {}),
                now,
            ),
        )
        row = conn.execute('SELECT * FROM audit_logs WHERE audit_log_id = ?', (audit_log_id,)).fetchone()
    if row is None:
        raise RuntimeError('Failed to create audit log')
    return _serialize_audit_row(row)



def _serialize_audit_row(row) -> dict[str, Any]:
    return {
        'audit_log_id': row['audit_log_id'],
        'actor_user_id': row['actor_user_id'],
        'actor_role': row['actor_role'],
        'target_user_id': row['target_user_id'],
        'organization_id': row['organization_id'],
        'action_type': row['action_type'],
        'metadata': json_loads(row['metadata_json']),
        'created_at': row['created_at'],
    }



def _build_audit_filters(*, target_user_id: str | None = None, action_type: str | None = None, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None, search: str | None = None) -> tuple[str, list[Any]]:
    org_ids = [str(value).strip() for value in (organization_ids or []) if str(value).strip()]
    scoped_user_ids = [str(value).strip() for value in (user_ids or []) if str(value).strip()]
    clauses: list[str] = []
    params: list[Any] = []
    if target_user_id:
        clauses.append('target_user_id = ?')
        params.append(target_user_id)
    if action_type:
        clauses.append('action_type = ?')
        params.append(action_type.strip().lower())
    if org_ids:
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'(organization_id IN ({placeholders}))')
        params.extend(org_ids)
    elif scoped_user_ids:
        placeholders = ', '.join('?' for _ in scoped_user_ids)
        clauses.append(f'(target_user_id IN ({placeholders}) OR actor_user_id IN ({placeholders}))')
        params.extend(scoped_user_ids)
        params.extend(scoped_user_ids)
    search_clean = (search or '').strip().lower()
    if search_clean:
        like = f'%{search_clean}%'
        clauses.append('(lower(action_type) LIKE ? OR lower(COALESCE(metadata_json, "")) LIKE ?)')
        params.extend((like, like))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where_sql, params


def count_audit_logs(*, target_user_id: str | None = None, action_type: str | None = None, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None, search: str | None = None) -> int:
    where_sql, params = _build_audit_filters(target_user_id=target_user_id, action_type=action_type, organization_ids=organization_ids, user_ids=user_ids, search=search)
    with get_connection() as conn:
        row = conn.execute(f'SELECT COUNT(*) AS count FROM audit_logs {where_sql}', tuple(params)).fetchone()
    return int(row['count'] or 0) if row is not None else 0


def list_audit_logs(*, limit: int = 100, offset: int = 0, target_user_id: str | None = None, action_type: str | None = None, organization_ids: Iterable[str] | None = None, user_ids: Iterable[str] | None = None, search: str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    where_sql, params = _build_audit_filters(target_user_id=target_user_id, action_type=action_type, organization_ids=organization_ids, user_ids=user_ids, search=search)
    with get_connection() as conn:
        rows = conn.execute(
            f'SELECT * FROM audit_logs {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (*params, limit, offset),
        ).fetchall()
    return [_serialize_audit_row(row) for row in rows]
