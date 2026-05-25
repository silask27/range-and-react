from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable
from uuid import uuid4

from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.services.assignment_service import create_assignment
from api.app.storage.db import get_connection, json_dumps, json_loads


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def _serialize_cohort(row, *, member_count: int = 0) -> dict[str, Any]:
    return {
        "cohort_id": row["cohort_id"],
        "organization_id": row["organization_id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "created_by_user_id": row["created_by_user_id"],
        "metadata": json_loads(row["metadata_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "member_count": int(member_count or 0),
    }


def list_cohorts(*, organization_ids: Iterable[str] | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
    org_ids = _clean_ids(organization_ids)
    if organization_ids is not None and not org_ids:
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if org_ids:
        placeholders = ", ".join("?" for _ in org_ids)
        clauses.append(f"c.organization_id IN ({placeholders})")
        params.extend(org_ids)
    if not include_inactive:
        clauses.append("c.status = 'active'")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT c.*, COUNT(cm.user_id) AS member_count
            FROM cohorts c
            LEFT JOIN cohort_memberships cm ON cm.cohort_id = c.cohort_id
            {where_sql}
            GROUP BY c.cohort_id
            ORDER BY lower(c.name) ASC
            """,
            tuple(params),
        ).fetchall()
    return [_serialize_cohort(row, member_count=row["member_count"]) for row in rows]


def get_cohort(cohort_id: str) -> dict[str, Any] | None:
    cohort_id_clean = str(cohort_id or "").strip()
    if not cohort_id_clean:
        return None
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT c.*, COUNT(cm.user_id) AS member_count
            FROM cohorts c
            LEFT JOIN cohort_memberships cm ON cm.cohort_id = c.cohort_id
            WHERE c.cohort_id = ?
            GROUP BY c.cohort_id
            LIMIT 1
            """,
            (cohort_id_clean,),
        ).fetchone()
    return _serialize_cohort(row, member_count=row["member_count"]) if row is not None else None


def create_cohort(*, organization_id: str, name: str, description: str | None, created_by_user_id: str | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    org_id = str(organization_id or "").strip()
    name_clean = str(name or "").strip()
    if not org_id:
        raise ValueError("organization_id is required")
    if not name_clean:
        raise ValueError("name is required")
    now = _utcnow_iso()
    cohort_id = str(uuid4())
    with get_connection() as conn:
        org_exists = conn.execute("SELECT 1 FROM organizations WHERE organization_id = ? LIMIT 1", (org_id,)).fetchone()
        if org_exists is None:
            raise ValueError("Unknown organization_id")
        conn.execute(
            """
            INSERT INTO cohorts (
                cohort_id, organization_id, name, description, status, created_by_user_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                cohort_id,
                org_id,
                name_clean,
                str(description or "").strip() or None,
                str(created_by_user_id or "").strip() or None,
                json_dumps(metadata if isinstance(metadata, dict) else {}),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM cohorts WHERE cohort_id = ?", (cohort_id,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to create cohort")
    return _serialize_cohort(row)


def add_cohort_members(*, cohort_id: str, user_ids: Iterable[str]) -> dict[str, Any]:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise ValueError("Unknown cohort_id")
    ids = _clean_ids(user_ids)
    now = _utcnow_iso()
    added: list[str] = []
    skipped: list[str] = []
    with get_connection() as conn:
        for user_id in ids:
            membership = conn.execute(
                """
                SELECT u.role, u.is_active
                FROM users u
                JOIN organization_memberships om ON om.user_id = u.user_id
                WHERE u.user_id = ? AND om.organization_id = ?
                LIMIT 1
                """,
                (user_id, cohort["organization_id"]),
            ).fetchone()
            if membership is None or str(membership["role"]) != UserRole.MEMBER.value or not bool(membership["is_active"]):
                skipped.append(user_id)
                continue
            exists = conn.execute(
                "SELECT 1 FROM cohort_memberships WHERE cohort_id = ? AND user_id = ? LIMIT 1",
                (cohort["cohort_id"], user_id),
            ).fetchone()
            if exists is not None:
                skipped.append(user_id)
                continue
            conn.execute(
                "INSERT INTO cohort_memberships (cohort_membership_id, cohort_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid4()), cohort["cohort_id"], user_id, now),
            )
            added.append(user_id)
    return {"cohort": get_cohort(cohort_id), "added_user_ids": added, "skipped_user_ids": skipped}


def list_cohort_members(*, cohort_id: str, active_only: bool = True) -> list[dict[str, Any]]:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise ValueError("Unknown cohort_id")
    active_sql = "AND u.is_active = 1" if active_only else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT u.user_id, u.email, u.display_name, u.role, u.is_active, cm.created_at
            FROM cohort_memberships cm
            JOIN users u ON u.user_id = cm.user_id
            WHERE cm.cohort_id = ? {active_sql}
            ORDER BY lower(COALESCE(u.display_name, u.email)) ASC
            """,
            (cohort["cohort_id"],),
        ).fetchall()
    return [
        {
            "user_id": row["user_id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_assignments_for_cohort(*, cohort_id: str, created_by: UserAccount, title: str, description: str | None, scenario_id: str | None, villain_profile_id: str | None, repetition_target: int, minimum_overall_score: float | None, due_at: str | None) -> dict[str, Any]:
    cohort = get_cohort(cohort_id)
    if cohort is None:
        raise ValueError("Unknown cohort_id")
    members = [member for member in list_cohort_members(cohort_id=cohort_id, active_only=True) if member["role"] == UserRole.MEMBER.value]
    assignments: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for member in members:
        try:
            assignments.append(
                create_assignment(
                    created_by_user_id=created_by.user_id,
                    target_user_id=member["user_id"],
                    organization_id=cohort["organization_id"],
                    title=title,
                    description=description,
                    scenario_id=scenario_id,
                    villain_profile_id=villain_profile_id,
                    repetition_target=repetition_target,
                    minimum_overall_score=minimum_overall_score,
                    due_at=due_at,
                    metadata={"cohort_id": cohort["cohort_id"], "cohort_name": cohort["name"], "source": "cohort_assignment"},
                )
            )
        except ValueError as exc:
            failures.append({"user_id": member["user_id"], "error": str(exc)})
    return {"cohort": cohort, "created_count": len(assignments), "assignments": assignments, "failures": failures}
