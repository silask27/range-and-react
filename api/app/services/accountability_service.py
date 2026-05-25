from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.services.assignment_service import list_assignments_with_progress
from api.app.storage.db import get_connection


def _clean_ids(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _label_for(key: str | None, *, kind: str) -> str:
    if not key:
        return "Any"
    if kind == "scenario" and key in SCENARIOS:
        return SCENARIOS[key].display_name
    if kind == "villain" and key in VILLAIN_PROFILES:
        return VILLAIN_PROFILES[key].meta.display_name
    return key


def _member_filter_sql(user_ids: list[str], alias: str = "u") -> tuple[str, list[Any]]:
    if not user_ids:
        return "", []
    placeholders = ", ".join("?" for _ in user_ids)
    return f" AND {alias}.user_id IN ({placeholders})", list(user_ids)


def _score(value: Any) -> float | None:
    return round(float(value), 2) if value is not None else None


def build_weekly_accountability_digest(
    *,
    visible_user_ids: Iterable[str] | None = None,
    visible_organization_ids: Iterable[str] | None = None,
    days: int = 7,
) -> dict[str, Any]:
    day_count = max(1, min(int(days or 7), 31))
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=day_count)
    user_ids = _clean_ids(visible_user_ids)
    organization_ids = _clean_ids(visible_organization_ids)
    user_filter_sql, user_filter_params = _member_filter_sql(user_ids, alias="u")

    with get_connection() as conn:
        member_rows = conn.execute(
            f"""
            SELECT u.user_id, u.email, u.display_name
            FROM users u
            WHERE u.role = 'member'
              AND u.is_active = 1
              {user_filter_sql}
            ORDER BY lower(COALESCE(u.display_name, u.email)) ASC
            """,
            tuple(user_filter_params),
        ).fetchall()
        member_ids = [str(row["user_id"]) for row in member_rows]
        member_placeholders = ", ".join("?" for _ in member_ids)
        hands_by_member: dict[str, dict[str, Any]] = {}
        if member_ids:
            hand_rows = conn.execute(
                f"""
                SELECT
                    hr.user_id,
                    COUNT(*) AS hands,
                    AVG(hr.overall_score) AS avg_overall_score,
                    AVG(hr.ranging_score) AS avg_ranging_score,
                    AVG(hr.response_score) AS avg_response_score,
                    MAX(hr.completed_at) AS last_completed_at
                FROM hand_results hr
                WHERE hr.hand_over = 1
                  AND hr.completed_at IS NOT NULL
                  AND hr.completed_at >= ?
                  AND hr.user_id IN ({member_placeholders})
                GROUP BY hr.user_id
                """,
                (cutoff.isoformat(), *member_ids),
            ).fetchall()
            hands_by_member = {str(row["user_id"]): dict(row) for row in hand_rows}

        weak_spot_rows = []
        if member_ids:
            weak_spot_rows = conn.execute(
                f"""
                SELECT
                    COALESCE(hr.scenario_id, 'any') AS scenario_id,
                    COALESCE(hr.villain_profile_id, 'any') AS villain_profile_id,
                    COUNT(*) AS hands,
                    AVG(hr.overall_score) AS avg_overall_score,
                    AVG(hr.ranging_score) AS avg_ranging_score,
                    AVG(hr.response_score) AS avg_response_score
                FROM hand_results hr
                WHERE hr.hand_over = 1
                  AND hr.completed_at IS NOT NULL
                  AND hr.completed_at >= ?
                  AND hr.user_id IN ({member_placeholders})
                GROUP BY COALESCE(hr.scenario_id, 'any'), COALESCE(hr.villain_profile_id, 'any')
                ORDER BY CASE WHEN AVG(hr.overall_score) IS NULL THEN 1 ELSE 0 END ASC,
                         AVG(hr.overall_score) ASC,
                         COUNT(*) DESC
                LIMIT 5
                """,
                (cutoff.isoformat(), *member_ids),
            ).fetchall()

    member_summaries = []
    trained_count = 0
    completed_hands = 0
    for row in member_rows:
        stats = hands_by_member.get(str(row["user_id"]), {})
        hands = int(stats.get("hands") or 0)
        if hands:
            trained_count += 1
            completed_hands += hands
        member_summaries.append({
            "user_id": row["user_id"],
            "display_name": row["display_name"] or row["email"],
            "email": row["email"],
            "hands": hands,
            "avg_overall_score": _score(stats.get("avg_overall_score")),
            "avg_ranging_score": _score(stats.get("avg_ranging_score")),
            "avg_response_score": _score(stats.get("avg_response_score")),
            "last_completed_at": stats.get("last_completed_at"),
        })

    missed_members = [member for member in member_summaries if int(member["hands"]) == 0]
    weakest_members = sorted(
        [member for member in member_summaries if int(member["hands"]) > 0 and member["avg_overall_score"] is not None],
        key=lambda item: (float(item["avg_overall_score"]), -int(item["hands"]), item["display_name"]),
    )[:5]

    assignments = list_assignments_with_progress(limit=5000, organization_ids=organization_ids or None, target_user_ids=user_ids or None)
    overdue_assignments = [item for item in assignments if item.get("status") == "overdue"]
    active_assignments = [item for item in assignments if item.get("status") == "active"]

    weak_spots = []
    for row in weak_spot_rows:
        scenario_id = None if row["scenario_id"] == "any" else str(row["scenario_id"])
        villain_id = None if row["villain_profile_id"] == "any" else str(row["villain_profile_id"])
        weak_spots.append({
            "scenario_id": scenario_id,
            "villain_profile_id": villain_id,
            "label": f"{_label_for(scenario_id, kind='scenario')} vs {_label_for(villain_id, kind='villain')}",
            "hands": int(row["hands"] or 0),
            "avg_overall_score": _score(row["avg_overall_score"]),
            "avg_ranging_score": _score(row["avg_ranging_score"]),
            "avg_response_score": _score(row["avg_response_score"]),
        })

    return {
        "period": {
            "days": day_count,
            "from": cutoff.isoformat(),
            "to": now.isoformat(),
        },
        "summary": {
            "active_members": len(member_summaries),
            "members_trained": trained_count,
            "members_missed": len(missed_members),
            "completed_hands": completed_hands,
            "active_assignments": len(active_assignments),
            "overdue_assignments": len(overdue_assignments),
        },
        "missed_members": missed_members[:10],
        "weakest_members": weakest_members,
        "weak_spots": weak_spots,
        "overdue_assignments": overdue_assignments[:10],
    }
