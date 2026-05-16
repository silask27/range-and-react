# File: api/app/storage/memory_store.py
# Summary: Persistent database-backed store for session and hand payloads. The public
# interface intentionally matches the original in-memory store so existing services
# can move to durable storage without large rewrites.

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from api.app.models.betting import ActionEvent, ActionHistory, BettingRoundState
from api.app.models.enums import ActionType, Player, Street, UIGate
from api.app.storage.db import get_connection, json_dumps, json_loads


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_action_event(event: ActionEvent) -> dict[str, Any]:
    return {
        'street': event.street.value,
        'actor': event.actor.value,
        'action': event.action.value,
        'amount': float(event.amount),
        'note': event.note,
        'forced': bool(event.forced),
    }


def _serialize_payload(value: Any) -> Any:
    if is_dataclass(value):
        if isinstance(value, ActionHistory):
            return {'events': [_serialize_action_event(event) for event in value.events]}
        if isinstance(value, BettingRoundState):
            return asdict(value)
        if isinstance(value, ActionEvent):
            return _serialize_action_event(value)
        return {key: _serialize_payload(val) for key, val in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_serialize_payload(item) for item in value]
    if isinstance(value, list):
        return [_serialize_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_payload(val) for key, val in value.items()}
    return value


def _deserialize_betting_round(data: dict[str, Any]) -> BettingRoundState:
    return BettingRoundState(
        current_bet=float(data.get('current_bet', 0.0)),
        hero_contrib=float(data.get('hero_contrib', 0.0)),
        villain_contrib=float(data.get('villain_contrib', 0.0)),
        last_raise_size=float(data.get('last_raise_size', 0.0)),
        folded=bool(data.get('folded', False)),
    )


def _deserialize_history(data: dict[str, Any]) -> ActionHistory:
    events = []
    for raw in data.get('events', []):
        events.append(
            ActionEvent(
                street=Street(raw['street']),
                actor=Player(raw['actor']),
                action=ActionType(raw['action']),
                amount=float(raw.get('amount', 0.0)),
                note=str(raw.get('note', '')),
                forced=bool(raw.get('forced', False)),
            )
        )
    return ActionHistory(events=events)


def _deserialize_session_payload(data: dict[str, Any]) -> dict[str, Any]:
    return data


def _deserialize_hand_payload(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out['hero_hand'] = tuple(out.get('hero_hand', []))
    out['villain_hand'] = tuple(out.get('villain_hand', []))
    out['street'] = Street(out['street'])
    out['current_actor'] = Player(out['current_actor'])
    out['current_aggressor'] = Player(out['current_aggressor']) if out.get('current_aggressor') else None
    out['ui_gate'] = UIGate(out['ui_gate'])
    out['betting_round'] = _deserialize_betting_round(out.get('betting_round', {}))
    out['history'] = _deserialize_history(out.get('history', {}))
    return out


def _summarize_session_row(row) -> dict[str, Any]:
    payload = _deserialize_session_payload(json_loads(row['payload_json']))
    return {
        'session_id': row['session_id'],
        'user_id': row['user_id'],
        'villain_profile_id': payload.get('villain_profile_id'),
        'scenario_id': payload.get('scenario_id'),
        'train_timer_seconds': payload.get('train_timer_seconds'),
        'hero_range_confirmed': bool(payload.get('hero_range_confirmed')),
        'villain_range_confirmed': bool(payload.get('villain_range_confirmed')),
        'is_ready_for_hand_start': bool(
            payload.get('scenario_id')
            and payload.get('pot') is not None
            and payload.get('hero_stack') is not None
            and payload.get('villain_stack') is not None
            and payload.get('hero_range_matrix_saved') is not None
            and payload.get('villain_range_matrix_saved') is not None
            and payload.get('hero_range_confirmed')
            and payload.get('villain_range_confirmed')
        ),
        'updated_at': row['updated_at'],
        'created_at': row['created_at'],
    }


def _summarize_hand_row(row) -> dict[str, Any]:
    payload = _deserialize_hand_payload(json_loads(row['payload_json']))
    return {
        'hand_id': row['hand_id'],
        'session_id': row['session_id'],
        'user_id': row['user_id'],
        'scenario_id': payload.get('scenario_id'),
        'villain_profile_id': payload.get('villain_profile_id'),
        'street': payload.get('street').value if payload.get('street') else None,
        'ui_gate': payload.get('ui_gate').value if payload.get('ui_gate') else None,
        'hand_over': bool(payload.get('hand_over')),
        'board': payload.get('board', []),
        'pot': float(payload.get('pot', 0.0) or 0.0),
        'hero_stack': float(payload.get('hero_stack', 0.0) or 0.0),
        'villain_stack': float(payload.get('villain_stack', 0.0) or 0.0),
        'updated_at': row['updated_at'],
        'created_at': row['created_at'],
    }


def _hand_results_snapshot(payload: dict[str, Any], *, now: str) -> tuple:
    live_combos = payload.get('villain_range_combos_live') or {}
    total_live_combos = 0
    for combos in live_combos.values():
        total_live_combos += len(combos)

    status = 'complete' if payload.get('hand_over') else 'active'
    completed_at = now if payload.get('hand_over') else None
    metadata = {
        'score_version': 1,
        'scoring_ready': False,
    }
    return (
        payload.get('hand_id'),
        payload.get('user_id'),
        payload.get('session_id'),
        payload.get('scenario_id'),
        payload.get('villain_profile_id'),
        status,
        payload.get('street'),
        payload.get('ui_gate'),
        1 if payload.get('hand_over') else 0,
        total_live_combos,
        now,
        now,
        completed_at,
        None,
        None,
        None,
        json_dumps(metadata),
    )


class SqliteStore:
    def create_session(self, session_id: str, payload: dict[str, Any]) -> None:
        now = _utcnow_iso()
        user_id = payload.get('user_id')
        with get_connection() as conn:
            conn.execute(
                '''
                INSERT INTO sessions (session_id, user_id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (session_id, user_id, json_dumps(_serialize_payload(payload)), now, now),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT payload_json FROM sessions WHERE session_id = ?',
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return _deserialize_session_payload(json_loads(row['payload_json']))

    def update_session(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_session(session_id)
        if current is None:
            raise KeyError(f'Unknown session_id: {session_id}')
        current.update(updates)
        with get_connection() as conn:
            conn.execute(
                'UPDATE sessions SET user_id = ?, payload_json = ?, updated_at = ? WHERE session_id = ?',
                (
                    current.get('user_id'),
                    json_dumps(_serialize_payload(current)),
                    _utcnow_iso(),
                    session_id,
                ),
            )
        return current

    def list_sessions(self, *, user_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with get_connection() as conn:
            if user_id:
                rows = conn.execute(
                    'SELECT session_id, user_id, payload_json, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?',
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT session_id, user_id, payload_json, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?',
                    (limit,),
                ).fetchall()
        return [_summarize_session_row(row) for row in rows]

    def create_hand(self, hand_id: str, payload: dict[str, Any]) -> None:
        now = _utcnow_iso()
        with get_connection() as conn:
            conn.execute(
                '''
                INSERT INTO hands (hand_id, user_id, session_id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    hand_id,
                    payload.get('user_id'),
                    payload.get('session_id'),
                    json_dumps(_serialize_payload(payload)),
                    now,
                    now,
                ),
            )
            conn.execute(
                '''
                INSERT INTO hand_results (
                    hand_id, user_id, session_id, scenario_id, villain_profile_id, status,
                    street, ui_gate, hand_over, total_live_combos, started_at, updated_at,
                    completed_at, ranging_score, response_score, overall_score, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (hand_id)
                DO UPDATE SET user_id = EXCLUDED.user_id,
                              session_id = EXCLUDED.session_id,
                              scenario_id = EXCLUDED.scenario_id,
                              villain_profile_id = EXCLUDED.villain_profile_id,
                              status = EXCLUDED.status,
                              street = EXCLUDED.street,
                              ui_gate = EXCLUDED.ui_gate,
                              hand_over = EXCLUDED.hand_over,
                              total_live_combos = EXCLUDED.total_live_combos,
                              started_at = EXCLUDED.started_at,
                              updated_at = EXCLUDED.updated_at,
                              completed_at = EXCLUDED.completed_at,
                              ranging_score = EXCLUDED.ranging_score,
                              response_score = EXCLUDED.response_score,
                              overall_score = EXCLUDED.overall_score,
                              metadata_json = EXCLUDED.metadata_json
                ''',
                _hand_results_snapshot(payload, now=now),
            )

    def get_hand(self, hand_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT payload_json FROM hands WHERE hand_id = ?',
                (hand_id,),
            ).fetchone()
        if row is None:
            return None
        return _deserialize_hand_payload(json_loads(row['payload_json']))

    def update_hand(self, hand_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_hand(hand_id)
        if current is None:
            raise KeyError(f'Unknown hand_id: {hand_id}')
        current.update(updates)
        now = _utcnow_iso()
        existing_result = self.get_hand_result(hand_id) or {'metadata': {'score_version': 2}}
        metadata = dict(existing_result.get('metadata') or {})
        metadata.setdefault('score_version', 2)
        metadata.setdefault('scoring_ready', True)

        with get_connection() as conn:
            conn.execute(
                'UPDATE hands SET user_id = ?, session_id = ?, payload_json = ?, updated_at = ? WHERE hand_id = ?',
                (
                    current.get('user_id'),
                    current.get('session_id'),
                    json_dumps(_serialize_payload(current)),
                    now,
                    hand_id,
                ),
            )
            completed_at = now if current.get('hand_over') else None
            conn.execute(
                '''
                UPDATE hand_results
                SET user_id = ?,
                    session_id = ?,
                    scenario_id = ?,
                    villain_profile_id = ?,
                    status = ?,
                    street = ?,
                    ui_gate = ?,
                    hand_over = ?,
                    total_live_combos = ?,
                    updated_at = ?,
                    completed_at = COALESCE(?, completed_at),
                    metadata_json = ?
                WHERE hand_id = ?
                ''',
                (
                    current.get('user_id'),
                    current.get('session_id'),
                    current.get('scenario_id'),
                    current.get('villain_profile_id'),
                    'complete' if current.get('hand_over') else 'active',
                    current.get('street').value if current.get('street') else None,
                    current.get('ui_gate').value if current.get('ui_gate') else None,
                    1 if current.get('hand_over') else 0,
                    sum(len(combos) for combos in (current.get('villain_range_combos_live') or {}).values()),
                    now,
                    completed_at,
                    json_dumps(metadata),
                    hand_id,
                ),
            )
        return current

    def list_hands(self, *, user_id: str | None = None, session_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        clauses: list[str] = []
        params: list[Any] = []
        if user_id:
            clauses.append('user_id = ?')
            params.append(user_id)
        if session_id:
            clauses.append('session_id = ?')
            params.append(session_id)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        with get_connection() as conn:
            rows = conn.execute(
                f'SELECT hand_id, session_id, user_id, payload_json, created_at, updated_at FROM hands {where_sql} ORDER BY updated_at DESC LIMIT ?',
                (*params, limit),
            ).fetchall()
        return [_summarize_hand_row(row) for row in rows]

    def get_latest_hand_for_session(self, session_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT hand_id, session_id, user_id, payload_json, created_at, updated_at FROM hands WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1',
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return _summarize_hand_row(row)

    def list_hand_results(self, *, user_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with get_connection() as conn:
            if user_id:
                rows = conn.execute(
                    '''
                    SELECT hand_id, user_id, session_id, scenario_id, villain_profile_id, status, street, ui_gate,
                           hand_over, total_live_combos, started_at, updated_at, completed_at,
                           ranging_score, response_score, overall_score, metadata_json
                    FROM hand_results
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    ''',
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    '''
                    SELECT hand_id, user_id, session_id, scenario_id, villain_profile_id, status, street, ui_gate,
                           hand_over, total_live_combos, started_at, updated_at, completed_at,
                           ranging_score, response_score, overall_score, metadata_json
                    FROM hand_results
                    ORDER BY updated_at DESC
                    LIMIT ?
                    ''',
                    (limit,),
                ).fetchall()
        return [
            {
                'hand_id': row['hand_id'],
                'user_id': row['user_id'],
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
            for row in rows
        ]

    def get_hand_result(self, hand_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT hand_id, user_id, session_id, scenario_id, villain_profile_id, status, street, ui_gate,
                       hand_over, total_live_combos, started_at, updated_at, completed_at,
                       ranging_score, response_score, overall_score, metadata_json
                FROM hand_results
                WHERE hand_id = ?
                """,
                (hand_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            'hand_id': row['hand_id'],
            'user_id': row['user_id'],
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

    def update_hand_result_scores(
        self,
        hand_id: str,
        *,
        ranging_score: float | None,
        response_score: float | None,
        overall_score: float | None,
        metadata: dict[str, Any],
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE hand_results
                SET ranging_score = ?, response_score = ?, overall_score = ?, metadata_json = ?, updated_at = ?
                WHERE hand_id = ?
                """,
                (ranging_score, response_score, overall_score, json_dumps(metadata), _utcnow_iso(), hand_id),
            )

    def reset(self) -> None:
        with get_connection() as conn:
            conn.execute('DELETE FROM hand_results')
            conn.execute('DELETE FROM hands')
            conn.execute('DELETE FROM sessions')


store = SqliteStore()
