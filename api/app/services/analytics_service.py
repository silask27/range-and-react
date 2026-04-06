from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Sequence

from fastapi import BackgroundTasks

from api.app.config import settings
from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.services.assignment_service import build_user_assignment_queue, list_assignments_with_progress
from api.app.storage.db import get_connection, json_dumps, json_loads
from api.app.storage.memory_store import store



def _utcnow() -> datetime:
    return datetime.now(UTC)



def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None



def _label_for(key: str) -> str:
    if key in SCENARIOS:
        return SCENARIOS[key].display_name
    if key in VILLAIN_PROFILES:
        return VILLAIN_PROFILES[key].meta.display_name
    return key



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



def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, 'keys'):
        return {key: row[key] for key in row.keys()}
    return dict(row)



def _scope_key(*, scope_type: str, visible_user_ids: Iterable[str] | None = None, visible_organization_ids: Iterable[str] | None = None, extra: dict[str, Any] | None = None) -> str:
    payload = {
        'scope_type': scope_type,
        'user_ids': _clean_ids(visible_user_ids),
        'organization_ids': _clean_ids(visible_organization_ids),
        'extra': extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()



def _load_snapshot(*, scope_type: str, scope_key: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT payload_json, generated_at, expires_at FROM analytics_snapshots WHERE scope_type = ? AND scope_key = ? LIMIT 1',
            (scope_type, scope_key),
        ).fetchone()
    if row is None:
        return None
    payload = json_loads(row['payload_json'])
    payload['_cache'] = {
        'generated_at': row['generated_at'],
        'expires_at': row['expires_at'],
        'is_fresh': datetime.fromisoformat(row['expires_at']) > _utcnow(),
    }
    return payload



def _save_snapshot(*, scope_type: str, scope_key: str, payload: dict[str, Any], ttl_seconds: int) -> dict[str, Any]:
    now = _utcnow()
    expires_at = now + timedelta(seconds=max(30, int(ttl_seconds)))
    cleaned = dict(payload)
    cleaned.pop('_cache', None)
    with get_connection() as conn:
        conn.execute(
            '''
            INSERT INTO analytics_snapshots (scope_type, scope_key, payload_json, generated_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (scope_type, scope_key)
            DO UPDATE SET payload_json = EXCLUDED.payload_json,
                          generated_at = EXCLUDED.generated_at,
                          expires_at = EXCLUDED.expires_at
            ''',
            (
                scope_type,
                scope_key,
                json_dumps(cleaned),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
    cleaned['_cache'] = {
        'generated_at': now.isoformat(),
        'expires_at': expires_at.isoformat(),
        'is_fresh': True,
    }
    return cleaned



def _build_results_where(*, visible_user_ids: Sequence[str] | None = None, alias: str = 'hr') -> tuple[str, list[Any]]:
    clauses = [f'{alias}.hand_over = 1']
    params: list[Any] = []
    clean_user_ids = _clean_ids(visible_user_ids)
    if clean_user_ids:
        placeholders = ', '.join('?' for _ in clean_user_ids)
        clauses.append(f'{alias}.user_id IN ({placeholders})')
        params.extend(clean_user_ids)
    return ' AND '.join(clauses), params



def _query_summary(*, visible_user_ids: Sequence[str] | None = None) -> dict[str, Any]:
    where_sql, params = _build_results_where(visible_user_ids=visible_user_ids)
    with get_connection() as conn:
        row = conn.execute(
            f'''
            SELECT
                COUNT(*) AS completed_hands,
                AVG(overall_score) AS avg_overall_score,
                AVG(ranging_score) AS avg_ranging_score,
                AVG(response_score) AS avg_response_score
            FROM hand_results hr
            WHERE {where_sql}
            ''',
            tuple(params),
        ).fetchone()
    data = _row_to_dict(row)
    return {
        'completed_hands': int(data.get('completed_hands') or 0),
        'avg_overall_score': round(float(data['avg_overall_score']), 2) if data.get('avg_overall_score') is not None else None,
        'avg_ranging_score': round(float(data['avg_ranging_score']), 2) if data.get('avg_ranging_score') is not None else None,
        'avg_response_score': round(float(data['avg_response_score']), 2) if data.get('avg_response_score') is not None else None,
    }



def _query_trend_points(*, visible_user_ids: Sequence[str] | None = None, limit: int = 12) -> list[dict[str, Any]]:
    where_sql, params = _build_results_where(visible_user_ids=visible_user_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f'''
            SELECT completed_at, updated_at, ranging_score, response_score
            FROM hand_results hr
            WHERE {where_sql}
            ORDER BY COALESCE(completed_at, updated_at) DESC
            LIMIT ?
            ''',
            (*params, max(1, min(int(limit), 24))),
        ).fetchall()
    ordered = list(reversed(rows))
    points: list[dict[str, Any]] = []
    for idx, row in enumerate(ordered):
        timestamp = row['completed_at'] or row['updated_at']
        label = f'Rep {idx + 1}'
        if isinstance(timestamp, str) and timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                label = dt.strftime('%b %d')
            except ValueError:
                pass
        points.append({
            'label': label,
            'ranging_score': row['ranging_score'],
            'response_score': row['response_score'],
        })
    return points



def _query_group_scores(*, column: str, visible_user_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
    where_sql, params = _build_results_where(visible_user_ids=visible_user_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f'''
            SELECT
                COALESCE({column}, 'unknown') AS key,
                COUNT(*) AS hands,
                AVG(overall_score) AS overall_score,
                AVG(ranging_score) AS ranging_score,
                AVG(response_score) AS response_score
            FROM hand_results hr
            WHERE {where_sql}
            GROUP BY COALESCE({column}, 'unknown')
            ORDER BY CASE WHEN AVG(overall_score) IS NULL THEN 1 ELSE 0 END ASC, AVG(overall_score) ASC, COUNT(*) DESC
            ''',
            tuple(params),
        ).fetchall()
    items = []
    for row in rows:
        items.append({
            'key': str(row['key']),
            'label': _label_for(str(row['key'])),
            'hands': int(row['hands'] or 0),
            'overall_score': round(float(row['overall_score']), 2) if row['overall_score'] is not None else None,
            'ranging_score': round(float(row['ranging_score']), 2) if row['ranging_score'] is not None else None,
            'response_score': round(float(row['response_score']), 2) if row['response_score'] is not None else None,
        })
    return items



def _query_pair_scores(*, visible_user_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
    where_sql, params = _build_results_where(visible_user_ids=visible_user_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f'''
            SELECT
                COALESCE(scenario_id, 'unknown') AS scenario_id,
                COALESCE(villain_profile_id, 'unknown') AS villain_profile_id,
                COUNT(*) AS hands,
                AVG(overall_score) AS overall_score,
                AVG(ranging_score) AS ranging_score,
                AVG(response_score) AS response_score
            FROM hand_results hr
            WHERE {where_sql}
            GROUP BY COALESCE(scenario_id, 'unknown'), COALESCE(villain_profile_id, 'unknown')
            ORDER BY CASE WHEN AVG(overall_score) IS NULL THEN 1 ELSE 0 END ASC, AVG(overall_score) ASC, COUNT(*) DESC
            ''',
            tuple(params),
        ).fetchall()
    items = []
    for row in rows:
        scenario_id = str(row['scenario_id'])
        villain_id = str(row['villain_profile_id'])
        items.append({
            'key': f'{scenario_id}::{villain_id}',
            'label': f'{_label_for(scenario_id)} · {_label_for(villain_id)}',
            'hands': int(row['hands'] or 0),
            'overall_score': round(float(row['overall_score']), 2) if row['overall_score'] is not None else None,
            'ranging_score': round(float(row['ranging_score']), 2) if row['ranging_score'] is not None else None,
            'response_score': round(float(row['response_score']), 2) if row['response_score'] is not None else None,
        })
    return items



def _query_user_rows(*, visible_user_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    clean_user_ids = _clean_ids(visible_user_ids)
    if clean_user_ids:
        placeholders = ', '.join('?' for _ in clean_user_ids)
        clauses.append(f'u.user_id IN ({placeholders})')
        params.extend(clean_user_ids)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    with get_connection() as conn:
        rows = conn.execute(
            f'''
            SELECT
                u.user_id,
                u.email,
                u.display_name,
                u.role,
                u.is_active,
                COUNT(hr.hand_id) AS completed_hands,
                AVG(hr.overall_score) AS avg_overall_score,
                AVG(hr.ranging_score) AS avg_ranging_score,
                AVG(hr.response_score) AS avg_response_score
            FROM users u
            LEFT JOIN hand_results hr
                ON hr.user_id = u.user_id
               AND hr.hand_over = 1
            {where_sql}
            GROUP BY u.user_id, u.email, u.display_name, u.role, u.is_active
            ORDER BY u.created_at ASC
            ''',
            tuple(params),
        ).fetchall()
    items = []
    for row in rows:
        items.append({
            'user_id': row['user_id'],
            'display_name': row['display_name'] or row['email'],
            'email': row['email'],
            'role': row['role'],
            'is_active': bool(row['is_active']),
            'completed_hands': int(row['completed_hands'] or 0),
            'avg_overall_score': round(float(row['avg_overall_score']), 2) if row['avg_overall_score'] is not None else None,
            'avg_ranging_score': round(float(row['avg_ranging_score']), 2) if row['avg_ranging_score'] is not None else None,
            'avg_response_score': round(float(row['avg_response_score']), 2) if row['avg_response_score'] is not None else None,
        })
    return items



def _driver_summary(*, metric_key: str, baseline: float | None, scenario_rows: list[dict[str, Any]], villain_rows: list[dict[str, Any]], pair_rows: list[dict[str, Any]]) -> dict[str, str]:
    metric_label = 'ranging_score' if metric_key == 'ranging' else 'response_score'
    if baseline is None:
        return {'low': 'Not enough finished hands yet.', 'high': 'Not enough finished hands yet.'}
    candidates: list[tuple[str, float, int]] = []
    for label, rows in (
        ('Villain', villain_rows),
        ('Scenario', scenario_rows),
        ('Scenario × villain', pair_rows),
    ):
        for row in rows:
            score = row.get(metric_label)
            if score is None or row.get('hands', 0) < 2:
                continue
            candidates.append((f"{label}: {row['label']}", round(float(score) - float(baseline), 2), int(row['hands'])))
    negatives = [item for item in candidates if item[1] < 0]
    positives = [item for item in candidates if item[1] > 0]
    negatives.sort(key=lambda item: item[1])
    positives.sort(key=lambda item: item[1], reverse=True)
    low = negatives[0] if negatives else None
    high = positives[0] if positives else None
    return {
        'low': f"{low[0]} is dragging this score down most ({low[1]:+.0f}, {low[2]} samples)." if low else 'No clear weakness stands out yet.',
        'high': f"{high[0]} is lifting this score most ({high[1]:+.0f}, {high[2]} samples)." if high else 'No clear strength stands out yet.',
    }



def _compute_admin_analytics(*, visible_user_ids: Iterable[str] | None = None, visible_organization_ids: Iterable[str] | None = None) -> dict[str, Any]:
    user_scope = _clean_ids(visible_user_ids) or None
    org_scope = _clean_ids(visible_organization_ids) or None

    summary = _query_summary(visible_user_ids=user_scope)
    scenario_rows = _query_group_scores(column='scenario_id', visible_user_ids=user_scope)
    villain_rows = _query_group_scores(column='villain_profile_id', visible_user_ids=user_scope)
    pair_rows = _query_pair_scores(visible_user_ids=user_scope)
    user_rows = _query_user_rows(visible_user_ids=user_scope)
    assignments = list_assignments_with_progress(limit=2000, organization_ids=org_scope, target_user_ids=user_scope)

    assignments_by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_user[str(assignment['target_user_id'])].append(assignment)

    enriched_user_rows = []
    for user in user_rows:
        overdue = sum(1 for item in assignments_by_user[user['user_id']] if item.get('progress', {}).get('is_overdue'))
        active = sum(1 for item in assignments_by_user[user['user_id']] if item.get('status') == 'active')
        payload = dict(user)
        payload['active_assignments'] = active
        payload['overdue_assignments'] = overdue
        enriched_user_rows.append(payload)

    users_needing_attention = sorted(
        enriched_user_rows,
        key=lambda item: (-item['overdue_assignments'], 999 if item['avg_overall_score'] is None else item['avg_overall_score'], item['display_name']),
    )[:10]
    strongest_users = sorted(
        [row for row in enriched_user_rows if row['completed_hands'] > 0 and row['avg_overall_score'] is not None],
        key=lambda item: (-float(item['avg_overall_score']), -item['completed_hands'], item['display_name']),
    )[:10]

    assignment_status_counts: dict[str, int] = defaultdict(int)
    for assignment in assignments:
        assignment_status_counts[str(assignment.get('status') or 'unknown')] += 1

    return {
        'summary': {
            **summary,
            'users_tracked': len(user_rows),
            'assignments_tracked': len(assignments),
        },
        'trend_points': _query_trend_points(visible_user_ids=user_scope),
        'weakest_scenarios': scenario_rows[:6],
        'strongest_scenarios': sorted([row for row in scenario_rows if row['overall_score'] is not None], key=lambda item: (-float(item['overall_score']), -item['hands'], item['label']))[:6],
        'weakest_villains': villain_rows[:6],
        'strongest_villains': sorted([row for row in villain_rows if row['overall_score'] is not None], key=lambda item: (-float(item['overall_score']), -item['hands'], item['label']))[:6],
        'weakest_pairs': pair_rows[:6],
        'strongest_pairs': sorted([row for row in pair_rows if row['overall_score'] is not None], key=lambda item: (-float(item['overall_score']), -item['hands'], item['label']))[:6],
        'users_needing_attention': users_needing_attention,
        'strongest_users': strongest_users,
        'assignment_status_counts': dict(assignment_status_counts),
        'insight_drivers': {
            'ranging': _driver_summary(metric_key='ranging', baseline=summary['avg_ranging_score'], scenario_rows=scenario_rows, villain_rows=villain_rows, pair_rows=pair_rows),
            'response': _driver_summary(metric_key='response', baseline=summary['avg_response_score'], scenario_rows=scenario_rows, villain_rows=villain_rows, pair_rows=pair_rows),
        },
    }



def build_admin_analytics(*, visible_user_ids: Iterable[str] | None = None, visible_organization_ids: Iterable[str] | None = None) -> dict[str, Any]:
    return _compute_admin_analytics(visible_user_ids=visible_user_ids, visible_organization_ids=visible_organization_ids)



def get_admin_analytics(*, visible_user_ids: Iterable[str] | None = None, visible_organization_ids: Iterable[str] | None = None, background_tasks: BackgroundTasks | None = None, force_refresh: bool = False) -> dict[str, Any]:
    ttl = max(30, int(settings.admin_analytics_cache_ttl_seconds or 300))
    scope_key = _scope_key(scope_type='admin_analytics', visible_user_ids=visible_user_ids, visible_organization_ids=visible_organization_ids)
    cached = None if force_refresh else _load_snapshot(scope_type='admin_analytics', scope_key=scope_key)
    if cached and cached.get('_cache', {}).get('is_fresh'):
        return cached
    if cached and background_tasks is not None:
        background_tasks.add_task(
            _refresh_admin_analytics_snapshot,
            visible_user_ids=_clean_ids(visible_user_ids),
            visible_organization_ids=_clean_ids(visible_organization_ids),
            scope_key=scope_key,
            ttl=ttl,
        )
        cached['_cache']['refresh_scheduled'] = True
        return cached
    fresh = _compute_admin_analytics(visible_user_ids=visible_user_ids, visible_organization_ids=visible_organization_ids)
    return _save_snapshot(scope_type='admin_analytics', scope_key=scope_key, payload=fresh, ttl_seconds=ttl)



def _refresh_admin_analytics_snapshot(*, visible_user_ids: Sequence[str] | None, visible_organization_ids: Sequence[str] | None, scope_key: str, ttl: int) -> None:
    payload = _compute_admin_analytics(visible_user_ids=visible_user_ids, visible_organization_ids=visible_organization_ids)
    _save_snapshot(scope_type='admin_analytics', scope_key=scope_key, payload=payload, ttl_seconds=ttl)



def _compute_dashboard_overview(*, user_id: str) -> dict[str, Any]:
    sessions = store.list_sessions(user_id=user_id, limit=8)
    hands = store.list_hands(user_id=user_id, limit=8)
    results = [item for item in store.list_hand_results(user_id=user_id, limit=50) if item.get('hand_over')]
    assignment_queue = build_user_assignment_queue(user_id=user_id, limit=20)

    active_hands = [item for item in hands if not item.get('hand_over')]
    completed_hands = [item for item in hands if item.get('hand_over')]
    ready_sessions = [item for item in sessions if item.get('is_ready_for_hand_start')]

    scored_ranging = [float(item['ranging_score']) for item in results if item.get('ranging_score') is not None]
    scored_response = [float(item['response_score']) for item in results if item.get('response_score') is not None]
    scored_overall = [float(item['overall_score']) for item in results if item.get('overall_score') is not None]

    return {
        'summary': {
            'total_sessions': len(sessions),
            'ready_sessions': len(ready_sessions),
            'active_hands': len(active_hands),
            'completed_hands': len(completed_hands),
            'results_tracked': len(results),
            'avg_ranging_score': round(sum(scored_ranging) / len(scored_ranging), 2) if scored_ranging else None,
            'avg_response_score': round(sum(scored_response) / len(scored_response), 2) if scored_response else None,
            'avg_overall_score': round(sum(scored_overall) / len(scored_overall), 2) if scored_overall else None,
            'assignments_total': assignment_queue['summary']['total'],
            'assignments_active': assignment_queue['summary']['active'],
            'assignments_overdue': assignment_queue['summary']['overdue'],
        },
        'recent_sessions': sessions,
        'recent_hands': hands,
        'recent_results': results,
        'assignments': assignment_queue['assignments'],
        'suggested_practice': assignment_queue['suggested_practice'],
        'results_scaffolding': {
            'enabled': True,
            'scoring_ready': True,
            'message': 'Ranging accuracy, response-matrix scoring, assignments, and debrief data are now being stored for completed hands.',
        },
    }



def get_dashboard_overview(*, user_id: str, background_tasks: BackgroundTasks | None = None, force_refresh: bool = False) -> dict[str, Any]:
    ttl = max(30, int(settings.dashboard_overview_cache_ttl_seconds or 120))
    scope_key = _scope_key(scope_type='dashboard_overview', visible_user_ids=[user_id])
    cached = None if force_refresh else _load_snapshot(scope_type='dashboard_overview', scope_key=scope_key)
    if cached and cached.get('_cache', {}).get('is_fresh'):
        return cached
    if cached and background_tasks is not None:
        background_tasks.add_task(_refresh_dashboard_overview_snapshot, user_id=user_id, scope_key=scope_key, ttl=ttl)
        cached['_cache']['refresh_scheduled'] = True
        return cached
    fresh = _compute_dashboard_overview(user_id=user_id)
    return _save_snapshot(scope_type='dashboard_overview', scope_key=scope_key, payload=fresh, ttl_seconds=ttl)



def _refresh_dashboard_overview_snapshot(*, user_id: str, scope_key: str, ttl: int) -> None:
    payload = _compute_dashboard_overview(user_id=user_id)
    _save_snapshot(scope_type='dashboard_overview', scope_key=scope_key, payload=payload, ttl_seconds=ttl)
