from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.services.analytics_service import build_cohort_summary_export_rows, build_member_results_export_rows
from api.app.services.cohort_service import get_cohort
from api.app.services.email_service import EmailDeliveryResult, send_csv_delivery_email
from api.app.storage.db import get_connection

CADENCE_OPTIONS = {'weekly', 'biweekly', 'monthly'}
DELIVERY_FILE_KEYS = {'member_summary', 'cohort_summary', 'org_summary'}

MEMBER_SUMMARY_FIELDNAMES = [
    'member_id',
    'display_name',
    'email',
    'organizations',
    'is_active',
    'reps_done',
    'current_range_score',
    'current_action_score',
    'current_overall_score',
    'worst_opponent',
    'worst_opponent_hands',
    'worst_opponent_overall_score',
    'active_assignments',
    'completed_assignments',
    'overdue_assignments',
]

COHORT_SUMMARY_FIELDNAMES = [
    'cohort_id',
    'organization',
    'cohort',
    'assigned_coaches',
    'assigned_coach_emails',
    'member_count',
    'completed_hands',
    'avg_range_score',
    'avg_action_score',
    'avg_overall_score',
    'last_completed_at',
    'assignment_count',
    'active_assignments',
    'completed_assignments',
    'overdue_assignments',
    'completed_reps',
    'target_reps',
    'rep_completion_rate',
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


def _cadence_delta(cadence: str) -> timedelta:
    if cadence == 'biweekly':
        return timedelta(days=14)
    if cadence == 'monthly':
        return timedelta(days=30)
    return timedelta(days=7)


def next_send_at_for_cadence(cadence: str, *, from_dt: datetime | None = None) -> str:
    anchor = from_dt or _utcnow()
    return _iso(anchor + _cadence_delta(cadence))


def slugify_filename(value: str | None, fallback: str) -> str:
    clean = re.sub(r'[^a-z0-9]+', '-', (value or '').strip().lower()).strip('-')
    return clean or fallback


def write_csv(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def member_summary_csv(
    *,
    user_id: str,
    visible_organization_ids: Iterable[str] | None = None,
) -> tuple[str, str, int]:
    rows = build_member_results_export_rows(
        visible_user_ids=[user_id],
        visible_organization_ids=visible_organization_ids,
    )
    display_name = rows[0].get('display_name') if rows else 'member'
    filename = f"{slugify_filename(str(display_name or ''), 'member')}-member-summary.csv"
    return filename, write_csv(rows, MEMBER_SUMMARY_FIELDNAMES), len(rows)


def member_scope_summary_csv(
    *,
    organization_label: str | None,
    visible_user_ids: Iterable[str] | None = None,
    visible_organization_ids: Iterable[str] | None = None,
) -> tuple[str, str, int]:
    rows = build_member_results_export_rows(
        visible_user_ids=visible_user_ids,
        visible_organization_ids=visible_organization_ids,
    )
    filename = f"{slugify_filename(organization_label, 'organization')}-member-summary.csv"
    return filename, write_csv(rows, MEMBER_SUMMARY_FIELDNAMES), len(rows)


def cohort_summary_csv(
    *,
    cohort_id: str,
    visible_user_ids: Iterable[str] | None = None,
    visible_organization_ids: Iterable[str] | None = None,
) -> tuple[str, str, int]:
    rows = [
        row for row in build_cohort_summary_export_rows(
            visible_user_ids=visible_user_ids,
            visible_organization_ids=visible_organization_ids,
        )
        if row.get('cohort_id') == cohort_id
    ]
    cohort = get_cohort(cohort_id)
    filename = f"{slugify_filename(cohort.get('name') if cohort else None, 'cohort')}-cohort-summary.csv"
    return filename, write_csv(rows, COHORT_SUMMARY_FIELDNAMES), len(rows)


def org_cohort_summary_csv(
    *,
    organization_label: str | None,
    visible_user_ids: Iterable[str] | None = None,
    visible_organization_ids: Iterable[str] | None = None,
) -> tuple[str, str, int]:
    rows = build_cohort_summary_export_rows(
        visible_user_ids=visible_user_ids,
        visible_organization_ids=visible_organization_ids,
    )
    filename = f"{slugify_filename(organization_label, 'organization')}-cohort-summary.csv"
    return filename, write_csv(rows, COHORT_SUMMARY_FIELDNAMES), len(rows)


def _default_preference(user: UserAccount, cohort_id: str | None = None) -> dict[str, Any]:
    is_org_lead = user.role in {UserRole.OWNER, UserRole.ADMIN}
    return {
        'cadence': 'weekly',
        'include_member_summary': False,
        'include_cohort_summary': True,
        'include_org_summary': is_org_lead,
        'cohort_id': cohort_id,
        'last_sent_at': None,
        'next_send_at': next_send_at_for_cadence('weekly'),
        'updated_at': None,
    }


def get_data_delivery_preference(user: UserAccount, *, default_cohort_id: str | None = None) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT cadence, include_member_summary, include_cohort_summary, include_org_summary, cohort_id, last_sent_at, next_send_at, updated_at
            FROM data_delivery_preferences
            WHERE user_id = ?
            ''',
            (user.user_id,),
        ).fetchone()
    if row is None:
        return _default_preference(user, default_cohort_id)
    return {
        'cadence': row['cadence'],
        'include_member_summary': bool(row['include_member_summary']),
        'include_cohort_summary': bool(row['include_cohort_summary']),
        'include_org_summary': bool(row['include_org_summary']),
        'cohort_id': row['cohort_id'] or default_cohort_id,
        'last_sent_at': row['last_sent_at'],
        'next_send_at': row['next_send_at'] or next_send_at_for_cadence(str(row['cadence'] or 'weekly')),
        'updated_at': row['updated_at'],
    }


def save_data_delivery_preference(
    user: UserAccount,
    *,
    cadence: str,
    include_member_summary: bool,
    include_cohort_summary: bool,
    include_org_summary: bool,
    cohort_id: str | None,
) -> dict[str, Any]:
    cadence_clean = str(cadence or '').strip().lower()
    if cadence_clean not in CADENCE_OPTIONS:
        raise ValueError('cadence must be weekly, biweekly, or monthly')
    now_dt = _utcnow()
    now = _iso(now_dt)
    next_send_at = next_send_at_for_cadence(cadence_clean, from_dt=now_dt)
    with get_connection() as conn:
        conn.execute(
            '''
            INSERT INTO data_delivery_preferences (
                user_id, cadence, include_member_summary, include_cohort_summary, include_org_summary,
                cohort_id, last_sent_at, next_send_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                cadence = excluded.cadence,
                include_member_summary = excluded.include_member_summary,
                include_cohort_summary = excluded.include_cohort_summary,
                include_org_summary = excluded.include_org_summary,
                cohort_id = excluded.cohort_id,
                next_send_at = excluded.next_send_at,
                updated_at = excluded.updated_at
            ''',
            (
                user.user_id,
                cadence_clean,
                1 if include_member_summary else 0,
                1 if include_cohort_summary else 0,
                1 if include_org_summary else 0,
                cohort_id,
                next_send_at,
                now,
                now,
            ),
        )
    return get_data_delivery_preference(user, default_cohort_id=cohort_id)


def mark_data_delivery_sent(user_id: str, *, cadence: str, sent_at: datetime | None = None) -> None:
    sent_dt = sent_at or _utcnow()
    sent_iso = _iso(sent_dt)
    next_send_at = next_send_at_for_cadence(cadence, from_dt=sent_dt)
    with get_connection() as conn:
        conn.execute(
            '''
            UPDATE data_delivery_preferences
            SET last_sent_at = ?, next_send_at = ?, updated_at = ?
            WHERE user_id = ?
            ''',
            (sent_iso, next_send_at, sent_iso, user_id),
        )


def list_due_data_delivery_preferences(*, as_of: datetime | None = None, limit: int = 100) -> list[dict[str, Any]]:
    now = _iso(as_of or _utcnow())
    with get_connection() as conn:
        rows = conn.execute(
            '''
            SELECT
                p.user_id,
                p.cadence,
                p.include_member_summary,
                p.include_cohort_summary,
                p.include_org_summary,
                p.cohort_id,
                p.last_sent_at,
                p.next_send_at,
                p.updated_at,
                u.email,
                u.display_name,
                u.role,
                u.is_active
            FROM data_delivery_preferences p
            JOIN users u ON u.user_id = p.user_id
            WHERE u.is_active = 1
              AND (p.include_member_summary = 1 OR p.include_cohort_summary = 1 OR p.include_org_summary = 1)
              AND COALESCE(p.next_send_at, p.updated_at, p.created_at) <= ?
            ORDER BY COALESCE(p.next_send_at, p.updated_at, p.created_at) ASC
            LIMIT ?
            ''',
            (now, limit),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            role = UserRole(row['role'])
        except ValueError:
            continue
        out.append({
            'user': UserAccount(
                user_id=row['user_id'],
                email=row['email'],
                display_name=row['display_name'],
                role=role,
                is_active=bool(row['is_active']),
            ),
            'preference': {
                'cadence': row['cadence'],
                'include_member_summary': bool(row['include_member_summary']),
                'include_cohort_summary': bool(row['include_cohort_summary']),
                'include_org_summary': bool(row['include_org_summary']),
                'cohort_id': row['cohort_id'],
                'last_sent_at': row['last_sent_at'],
                'next_send_at': row['next_send_at'],
                'updated_at': row['updated_at'],
            },
        })
    return out


def build_delivery_files(
    *,
    user: UserAccount,
    selected_files: Iterable[str],
    cohort_id: str | None,
    organization_label: str | None,
    visible_user_ids: Iterable[str] | None = None,
    visible_organization_ids: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    requested = {str(item).strip() for item in selected_files if str(item).strip()}
    files: list[dict[str, str]] = []
    if 'member_summary' in requested:
        if user.role == UserRole.MEMBER:
            filename, content, _ = member_summary_csv(user_id=user.user_id, visible_organization_ids=visible_organization_ids)
        else:
            filename, content, _ = member_scope_summary_csv(
                organization_label=organization_label,
                visible_user_ids=visible_user_ids,
                visible_organization_ids=visible_organization_ids,
            )
        files.append({'filename': filename, 'content': content})
    if 'cohort_summary' in requested and cohort_id:
        filename, content, _ = cohort_summary_csv(
            cohort_id=cohort_id,
            visible_user_ids=visible_user_ids,
            visible_organization_ids=visible_organization_ids,
        )
        files.append({'filename': filename, 'content': content})
    if 'org_summary' in requested:
        filename, content, _ = org_cohort_summary_csv(
            organization_label=organization_label,
            visible_user_ids=visible_user_ids,
            visible_organization_ids=visible_organization_ids,
        )
        files.append({'filename': filename, 'content': content})
    return files


def send_data_delivery_files(
    *,
    user: UserAccount,
    files: list[dict[str, str]],
    cadence: str,
) -> EmailDeliveryResult:
    return send_csv_delivery_email(
        email=user.email,
        display_name=user.display_name or user.email,
        files=files,
        cadence=cadence,
    )
