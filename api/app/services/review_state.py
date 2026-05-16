from __future__ import annotations

from typing import Any, Iterable


REVIEW_METADATA_KEY = "review"


def clean_ids(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def review_state_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict((metadata or {}).get(REVIEW_METADATA_KEY) or {})
    status_value = str(raw.get("status") or "").strip().lower()
    flagged = bool(raw.get("flagged"))
    sent = bool(raw.get("sent_to_coaches"))
    if not status_value:
        status_value = "sent" if sent else "flagged" if flagged else "none"
    return {
        "flagged": flagged,
        "sent_to_coaches": sent,
        "status": status_value,
        "flagged_at": raw.get("flagged_at"),
        "flagged_by_user_id": raw.get("flagged_by_user_id"),
        "sent_at": raw.get("sent_at"),
        "sent_by_user_id": raw.get("sent_by_user_id"),
        "organization_ids": clean_ids(raw.get("organization_ids")),
        "coach_recipient_user_ids": clean_ids(raw.get("coach_recipient_user_ids")),
    }
