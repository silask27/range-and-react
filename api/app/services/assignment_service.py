from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Iterable
from uuid import uuid4

from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.storage.db import get_connection, json_dumps, json_loads
from api.app.storage.memory_store import store



def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()



def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)



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



def _serialize_assignment_row(row) -> dict[str, Any]:
    return {
        'assignment_id': row['assignment_id'],
        'created_by_user_id': row['created_by_user_id'],
        'target_user_id': row['target_user_id'],
        'organization_id': row['organization_id'] if 'organization_id' in row.keys() else None,
        'title': row['title'],
        'description': row['description'],
        'scenario_id': row['scenario_id'],
        'villain_profile_id': row['villain_profile_id'],
        'repetition_target': int(row['repetition_target']),
        'minimum_overall_score': row['minimum_overall_score'],
        'due_at': row['due_at'],
        'status': row['status'],
        'metadata': json_loads(row['metadata_json']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }



def create_assignment(*, created_by_user_id: str, target_user_id: str, title: str, description: str | None, scenario_id: str | None, villain_profile_id: str | None, repetition_target: int, minimum_overall_score: float | None, due_at: str | None, organization_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    title_clean = (title or '').strip()
    target_user_id = (target_user_id or '').strip()
    organization_id_clean = (organization_id or '').strip() or None
    if not target_user_id:
        raise ValueError('target_user_id is required')
    if not title_clean:
        raise ValueError('title is required')
    if repetition_target <= 0:
        raise ValueError('repetition_target must be at least 1')
    with get_connection() as conn:
        target_exists = conn.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (target_user_id,)).fetchone()
        if target_exists is None:
            raise ValueError('Unknown target_user_id')
        if organization_id_clean:
            membership = conn.execute(
                'SELECT 1 FROM organization_memberships WHERE organization_id = ? AND user_id = ? LIMIT 1',
                (organization_id_clean, target_user_id),
            ).fetchone()
            if membership is None:
                raise ValueError('Target user is not a member of that organization')
    if scenario_id and scenario_id not in SCENARIOS:
        raise ValueError('Unknown scenario_id')
    if villain_profile_id and villain_profile_id not in VILLAIN_PROFILES:
        raise ValueError('Unknown villain_profile_id')
    now = _utcnow_iso()
    assignment_id = str(uuid4())
    metadata_payload = {'source': 'coach_assignment', 'version': 2, **(metadata if isinstance(metadata, dict) else {})}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO assignments (
                assignment_id, created_by_user_id, target_user_id, organization_id, title, description,
                scenario_id, villain_profile_id, repetition_target, minimum_overall_score,
                due_at, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                assignment_id,
                created_by_user_id,
                target_user_id,
                organization_id_clean,
                title_clean,
                (description or '').strip() or None,
                scenario_id,
                villain_profile_id,
                int(repetition_target),
                float(minimum_overall_score) if minimum_overall_score is not None else None,
                due_at,
                json_dumps(metadata_payload),
                now,
                now,
            ),
        )
        row = conn.execute('SELECT * FROM assignments WHERE assignment_id = ?', (assignment_id,)).fetchone()
    if row is None:
        raise RuntimeError('Failed to create assignment')
    return _serialize_assignment_row(row)



def _build_assignment_filters(
    *,
    target_user_id: str | None = None,
    status: str | None = None,
    organization_ids: Iterable[str] | None = None,
    target_user_ids: Iterable[str] | None = None,
    search: str | None = None,
) -> tuple[str, list[Any]]:
    org_ids = _clean_ids(organization_ids)
    scoped_target_user_ids = _clean_ids(target_user_ids)
    clauses: list[str] = []
    params: list[Any] = []
    if target_user_id:
        clauses.append('target_user_id = ?')
        params.append(target_user_id)
    if scoped_target_user_ids:
        placeholders = ', '.join('?' for _ in scoped_target_user_ids)
        clauses.append(f'target_user_id IN ({placeholders})')
        params.extend(scoped_target_user_ids)
    if org_ids:
        placeholders = ', '.join('?' for _ in org_ids)
        clauses.append(f'organization_id IN ({placeholders})')
        params.extend(org_ids)
    if status and status not in {'completed', 'overdue'}:
        clauses.append('status = ?')
        params.append(status)
    search_clean = (search or '').strip().lower()
    if search_clean:
        like = f'%{search_clean}%'
        clauses.append('(lower(title) LIKE ? OR lower(COALESCE(description, \"\")) LIKE ?)')
        params.extend((like, like))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where_sql, params



def count_assignments(*, target_user_id: str | None = None, status: str | None = None, organization_ids: Iterable[str] | None = None, target_user_ids: Iterable[str] | None = None, search: str | None = None) -> int:
    where_sql, params = _build_assignment_filters(
        target_user_id=target_user_id,
        status=status,
        organization_ids=organization_ids,
        target_user_ids=target_user_ids,
        search=search,
    )
    with get_connection() as conn:
        row = conn.execute(f'SELECT COUNT(*) AS count FROM assignments {where_sql}', tuple(params)).fetchone()
    return int(row['count'] or 0) if row is not None else 0



def list_assignments(*, target_user_id: str | None = None, status: str | None = None, limit: int = 200, offset: int = 0, organization_ids: Iterable[str] | None = None, target_user_ids: Iterable[str] | None = None, search: str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 5000))
    offset = max(0, int(offset))
    where_sql, params = _build_assignment_filters(
        target_user_id=target_user_id,
        status=status,
        organization_ids=organization_ids,
        target_user_ids=target_user_ids,
        search=search,
    )
    with get_connection() as conn:
        rows = conn.execute(
            f'SELECT * FROM assignments {where_sql} ORDER BY updated_at DESC LIMIT ? OFFSET ?',
            (*params, limit, offset),
        ).fetchall()
    return [_serialize_assignment_row(row) for row in rows]



def _derive_assignment_progress(*, assignment: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
    matched = int((row or {}).get('matched_hands') or 0)
    qualifying = int((row or {}).get('qualifying_hands') or 0)
    target = int(assignment['repetition_target'])
    percent = round(min(100.0, (qualifying / target) * 100.0), 2) if target > 0 else 0.0
    due_at = _parse_iso(assignment.get('due_at'))
    now = datetime.now(UTC)
    is_overdue = bool(due_at and qualifying < target and due_at < now)
    derived_status = 'completed' if qualifying >= target else 'overdue' if is_overdue else assignment.get('status') or 'active'
    avg_ranging = row.get('avg_ranging_score') if row else None
    avg_response = row.get('avg_response_score') if row else None
    avg_overall = row.get('avg_overall_score') if row else None
    return {
        'matched_hands': matched,
        'qualifying_hands': qualifying,
        'progress_count': qualifying,
        'repetition_target': target,
        'progress_percent': percent,
        'remaining_reps': max(0, target - qualifying),
        'avg_ranging_score': round(float(avg_ranging), 2) if avg_ranging is not None else None,
        'avg_response_score': round(float(avg_response), 2) if avg_response is not None else None,
        'avg_overall_score': round(float(avg_overall), 2) if avg_overall is not None else None,
        'last_completed_at': row.get('last_completed_at') if row else None,
        'status': derived_status,
        'is_overdue': is_overdue,
    }



def _batch_assignment_progress(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not items:
        return {}
    ids = [str(item['assignment_id']) for item in items]
    placeholders = ', '.join('?' for _ in ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                a.assignment_id AS assignment_id,
                COUNT(hr.hand_id) AS matched_hands,
                SUM(
                    CASE
                        WHEN hr.hand_id IS NULL THEN 0
                        WHEN hr.overall_score IS NOT NULL AND (a.minimum_overall_score IS NULL OR hr.overall_score >= a.minimum_overall_score) THEN 1
                        ELSE 0
                    END
                ) AS qualifying_hands,
                AVG(hr.ranging_score) AS avg_ranging_score,
                AVG(hr.response_score) AS avg_response_score,
                AVG(hr.overall_score) AS avg_overall_score,
                MAX(hr.completed_at) AS last_completed_at
            FROM assignments a
            LEFT JOIN hand_results hr
                ON hr.user_id = a.target_user_id
               AND hr.hand_over = 1
               AND hr.completed_at IS NOT NULL
               AND hr.completed_at >= a.created_at
               AND (a.scenario_id IS NULL OR hr.scenario_id = a.scenario_id)
               AND (a.villain_profile_id IS NULL OR hr.villain_profile_id = a.villain_profile_id)
            WHERE a.assignment_id IN ({placeholders})
            GROUP BY a.assignment_id
            """,
            tuple(ids),
        ).fetchall()
    return {str(row['assignment_id']): dict(row) for row in rows}



def count_assignments_with_progress(*, target_user_id: str | None = None, status: str | None = None, organization_ids: Iterable[str] | None = None, target_user_ids: Iterable[str] | None = None, search: str | None = None) -> int:
    if status not in {'completed', 'overdue'}:
        return count_assignments(target_user_id=target_user_id, status=status, organization_ids=organization_ids, target_user_ids=target_user_ids, search=search)
    items = list_assignments_with_progress(target_user_id=target_user_id, status=status, limit=5000, offset=0, organization_ids=organization_ids, target_user_ids=target_user_ids, search=search)
    return len(items)


def list_assignments_with_progress(*, target_user_id: str | None = None, status: str | None = None, limit: int = 200, offset: int = 0, organization_ids: Iterable[str] | None = None, target_user_ids: Iterable[str] | None = None, search: str | None = None) -> list[dict[str, Any]]:
    status_clean = (status or '').strip() or None
    derive_before_paginating = status_clean is not None
    items = list_assignments(
        target_user_id=target_user_id,
        status=None if derive_before_paginating else None,
        limit=5000 if derive_before_paginating else limit,
        offset=0 if derive_before_paginating else offset,
        organization_ids=organization_ids,
        target_user_ids=target_user_ids,
        search=search,
    )
    progress_by_id = _batch_assignment_progress(items)
    out: list[dict[str, Any]] = []
    for item in items:
        progress = _derive_assignment_progress(assignment=item, row=progress_by_id.get(str(item['assignment_id'])))
        payload = dict(item)
        payload['progress'] = progress
        payload['status'] = progress['status']
        if status_clean and payload['status'] != status_clean:
            continue
        out.append(payload)
    if derive_before_paginating:
        start = max(0, int(offset))
        end = start + max(1, min(int(limit), 5000))
        return out[start:end]
    return out



def summarize_assignments(*, target_user_id: str | None = None, organization_ids: Iterable[str] | None = None, target_user_ids: Iterable[str] | None = None) -> dict[str, int]:
    items = list_assignments_with_progress(target_user_id=target_user_id, limit=5000, organization_ids=organization_ids, target_user_ids=target_user_ids)
    summary = {'total': len(items), 'active': 0, 'completed': 0, 'overdue': 0}
    for item in items:
        summary[item['status']] = summary.get(item['status'], 0) + 1
    return summary



def build_suggested_practice(*, user_id: str, limit: int = 4) -> list[dict[str, Any]]:
    records = store.list_hand_results(user_id=user_id, hand_over=True, limit=1000)
    suggestions: list[dict[str, Any]] = []
    if not records:
        return [{
            'title': 'Build your first baseline',
            'description': 'Complete 10 reps in any core scenario so the app can start surfacing your weak spots.',
            'reason': 'No completed hands yet',
            'scenario_id': None,
            'villain_profile_id': None,
            'quick_start_url': '/screen-1',
            'focus': 'baseline',
        }]

    def avg(rows: list[dict[str, Any]], key: str) -> float | None:
        vals = [float(row[key]) for row in rows if row.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    by_scenario: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    by_villain: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    by_pair: dict[tuple[str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_scenario[row.get('scenario_id')].append(row)
        by_villain[row.get('villain_profile_id')].append(row)
        by_pair[(row.get('scenario_id'), row.get('villain_profile_id'))].append(row)

    scenario_rows = [(scenario_id, avg(items, 'overall_score'), len(items), avg(items, 'ranging_score'), avg(items, 'response_score')) for scenario_id, items in by_scenario.items() if scenario_id and len(items) >= 2]
    scenario_rows = [row for row in scenario_rows if row[1] is not None]
    scenario_rows.sort(key=lambda item: (item[1], -item[2]))
    if scenario_rows:
        scenario_id, overall, hands, ranging_avg, response_avg = scenario_rows[0]
        suggestions.append({
            'title': 'Revisit your toughest scenario',
            'description': f"Your lowest scenario average is {SCENARIOS[scenario_id].display_name} over {hands} completed hands.",
            'reason': f'Average Overall Score: {overall}',
            'scenario_id': scenario_id,
            'villain_profile_id': None,
            'quick_start_url': f'/screen-1?scenario_id={scenario_id}',
            'focus': 'scenario',
            'ranging_score': ranging_avg,
            'response_score': response_avg,
        })

    villain_rows = [(villain_id, avg(items, 'overall_score'), len(items), avg(items, 'ranging_score'), avg(items, 'response_score')) for villain_id, items in by_villain.items() if villain_id and len(items) >= 2]
    villain_rows = [row for row in villain_rows if row[1] is not None]
    villain_rows.sort(key=lambda item: (item[1], -item[2]))
    if villain_rows:
        villain_id, overall, hands, ranging_avg, response_avg = villain_rows[0]
        suggestions.append({
            'title': 'Target your toughest villain',
            'description': f"You score lowest against {(VILLAIN_PROFILES[villain_id].meta.display_name if villain_id in VILLAIN_PROFILES else villain_id)} over {hands} completed hands.",
            'reason': f'Average Overall Score: {overall}',
            'scenario_id': None,
            'villain_profile_id': villain_id,
            'quick_start_url': f'/screen-1?villain_profile_id={villain_id}',
            'focus': 'villain',
            'ranging_score': ranging_avg,
            'response_score': response_avg,
        })

    pair_rows = [(scenario_id, villain_id, avg(items, 'overall_score'), len(items), avg(items, 'response_score')) for (scenario_id, villain_id), items in by_pair.items() if scenario_id and villain_id and len(items) >= 2]
    pair_rows = [row for row in pair_rows if row[2] is not None]
    pair_rows.sort(key=lambda item: (item[2], -item[3]))
    if pair_rows:
        scenario_id, villain_id, overall, hands, response_avg = pair_rows[0]
        suggestions.append({
            'title': 'Drill your weakest exact matchup',
            'description': f"Your toughest pairing so far is {(SCENARIOS[scenario_id].display_name if scenario_id in SCENARIOS else scenario_id)} vs {(VILLAIN_PROFILES[villain_id].meta.display_name if villain_id in VILLAIN_PROFILES else villain_id)}.",
            'reason': f'Average Overall Score: {overall} across {hands} hands',
            'scenario_id': scenario_id,
            'villain_profile_id': villain_id,
            'quick_start_url': f'/screen-1?scenario_id={scenario_id}&villain_profile_id={villain_id}',
            'focus': 'pair',
            'response_score': response_avg,
        })

    overall_ranging = avg(records, 'ranging_score')
    overall_response = avg(records, 'response_score')
    if overall_ranging is not None and overall_response is not None:
        if overall_ranging + 7 < overall_response:
            focus_target = scenario_rows[0][0] if scenario_rows else None
            suggestions.append({
                'title': 'Tighten your pruning discipline',
                'description': 'Your ranging score trails your response score. Keep more plausible combos alive before cutting deeper.',
                'reason': f'Avg Villain Ranging {overall_ranging} vs Action Response {overall_response}',
                'scenario_id': focus_target,
                'villain_profile_id': None,
                'quick_start_url': f'/screen-1?scenario_id={focus_target}' if focus_target else '/screen-1',
                'focus': 'ranging',
            })
        elif overall_response + 7 < overall_ranging:
            focus_target = villain_rows[0][0] if villain_rows else None
            suggestions.append({
                'title': 'Sharpen bucket response prediction',
                'description': 'Your response-matrix score trails your range pruning. Focus on the single most likely reaction for each bucket before you act.',
                'reason': f'Avg response {overall_response} vs ranging {overall_ranging}',
                'scenario_id': None,
                'villain_profile_id': focus_target,
                'quick_start_url': f'/screen-1?villain_profile_id={focus_target}' if focus_target else '/screen-1',
                'focus': 'response',
            })

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in suggestions:
        key = (item.get('title'), item.get('scenario_id'), item.get('villain_profile_id'))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:limit]



def build_user_assignment_queue(*, user_id: str, limit: int = 50) -> dict[str, Any]:
    assignments = list_assignments_with_progress(target_user_id=user_id, limit=limit)
    summary = summarize_assignments(target_user_id=user_id)
    suggestions = build_suggested_practice(user_id=user_id, limit=4)
    return {'summary': summary, 'assignments': assignments, 'suggested_practice': suggestions}
