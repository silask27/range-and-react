from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.models.state import HandState
from api.app.services.access_service import (
    get_visible_user_ids,
    list_user_organization_ids,
)
from api.app.services.hand_service import get_hand
from api.app.services.organization_service import list_organization_members
from api.app.services.review_state import REVIEW_METADATA_KEY, clean_ids, review_state_from_metadata
from api.app.storage.memory_store import store


_COACH_REVIEW_ROLES = {UserRole.COACH.value, UserRole.ADMIN.value, UserRole.OWNER.value}
_STREET_ORDER = ["preflop", "flop", "turn", "river"]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _persist_result_metadata(result: dict[str, Any], metadata: dict[str, Any]) -> None:
    store.update_hand_result_scores(
        str(result["hand_id"]),
        ranging_score=result.get("ranging_score"),
        response_score=result.get("response_score"),
        overall_score=result.get("overall_score"),
        metadata=metadata,
    )


def _completed_hand_result(hand_id: str) -> dict[str, Any]:
    result = store.get_hand_result(hand_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown hand_id")
    if not result.get("hand_over"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only completed hands can be flagged for review.")
    return result


def _ensure_owns_hand_result(result: dict[str, Any], user: UserAccount) -> None:
    if str(result.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the hand owner can change review flags.")


def _coach_recipients_for_member(member_user_id: str) -> tuple[list[str], list[str]]:
    organization_ids = list_user_organization_ids(member_user_id)
    recipients: set[str] = set()
    for organization_id in organization_ids:
        for member in list_organization_members(organization_id):
            if not member.get("is_active"):
                continue
            role_values = {
                str(member.get("user_role") or "").lower(),
                str(member.get("membership_role") or "").lower(),
            }
            if role_values & _COACH_REVIEW_ROLES:
                user_id = str(member.get("user_id") or "").strip()
                if user_id and user_id != member_user_id:
                    recipients.add(user_id)
    return sorted(recipients), organization_ids


def set_hand_review_flag(hand_id: str, *, user: UserAccount, flagged: bool) -> dict[str, Any]:
    result = _completed_hand_result(hand_id)
    _ensure_owns_hand_result(result, user)

    metadata = dict(result.get("metadata") or {})
    review = review_state_from_metadata(metadata)
    if flagged:
        review.update({
            "flagged": True,
            "flagged_at": review.get("flagged_at") or _utcnow_iso(),
            "flagged_by_user_id": user.user_id,
            "status": "sent" if review.get("sent_to_coaches") else "flagged",
        })
    else:
        review.update({
            "flagged": False,
            "sent_to_coaches": False,
            "status": "none",
            "flagged_at": None,
            "flagged_by_user_id": None,
            "sent_at": None,
            "sent_by_user_id": None,
            "organization_ids": [],
            "coach_recipient_user_ids": [],
        })
    metadata[REVIEW_METADATA_KEY] = review
    _persist_result_metadata(result, metadata)
    return review_state_from_metadata(metadata)


def send_flagged_hands_to_coaches(*, user: UserAccount, hand_ids: list[str] | None = None) -> dict[str, Any]:
    requested = set(clean_ids(hand_ids))
    rows = []
    for row in store.list_hand_results(user_id=user.user_id, limit=1000):
        review = review_state_from_metadata(row.get("metadata"))
        if not row.get("hand_over") or not review.get("flagged"):
            continue
        if requested and str(row.get("hand_id")) not in requested:
            continue
        if not requested and review.get("sent_to_coaches"):
            continue
        rows.append(row)
    if requested:
        found = {str(row.get("hand_id")) for row in rows}
        missing = sorted(requested - found)
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Flagged hand not found: {missing[0]}")

    coach_ids, organization_ids = _coach_recipients_for_member(user.user_id)
    if not organization_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are not assigned to an organization yet.")
    if not coach_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active coaches are available in your organization yet.")

    sent_at = _utcnow_iso()
    updated: list[dict[str, Any]] = []
    for result in rows:
        metadata = dict(result.get("metadata") or {})
        review = review_state_from_metadata(metadata)
        review.update({
            "flagged": True,
            "sent_to_coaches": True,
            "sent_at": sent_at,
            "sent_by_user_id": user.user_id,
            "status": "sent",
            "organization_ids": organization_ids,
            "coach_recipient_user_ids": coach_ids,
        })
        metadata[REVIEW_METADATA_KEY] = review
        _persist_result_metadata(result, metadata)
        updated.append({"hand_id": result.get("hand_id"), "review": review_state_from_metadata(metadata)})

    return {
        "sent_count": len(updated),
        "coach_recipient_user_ids": coach_ids,
        "organization_ids": organization_ids,
        "hands": updated,
    }


def _can_view_review_result(result: dict[str, Any], user: UserAccount) -> bool:
    owner_id = str(result.get("user_id") or "")
    if owner_id == user.user_id:
        return True
    review = review_state_from_metadata(result.get("metadata"))
    if not review.get("sent_to_coaches"):
        return False
    if user.role in {UserRole.OWNER, UserRole.ADMIN}:
        return True
    if user.role != UserRole.COACH:
        return False
    if user.user_id in set(review.get("coach_recipient_user_ids") or []):
        return True
    review_org_ids = set(review.get("organization_ids") or [])
    return bool(review_org_ids & set(list_user_organization_ids(user.user_id)))


def ensure_can_view_review_hand(hand_id: str, user: UserAccount) -> dict[str, Any]:
    result = _completed_hand_result(hand_id)
    if _can_view_review_result(result, user):
        return result
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to that hand review.")


def list_review_queue(*, user: UserAccount) -> dict[str, Any]:
    visible_ids = get_visible_user_ids(user)
    candidate_user_ids = [user.user_id] if user.role == UserRole.MEMBER else visible_ids
    if candidate_user_ids is None:
        records = store.list_hand_results(limit=1000)
    else:
        records = []
        for user_id in candidate_user_ids:
            records.extend(store.list_hand_results(user_id=user_id, limit=1000))

    rows = [
        _review_queue_context(row)
        for row in records
        if row.get("hand_over") and _can_view_review_result(row, user)
    ]
    rows = [row for row in rows if row.get("review", {}).get("flagged")]
    rows.sort(key=lambda item: item.get("review", {}).get("sent_at") or item.get("review", {}).get("flagged_at") or item.get("completed_at") or "", reverse=True)
    return {"review_queue": rows}


def _review_queue_context(result: dict[str, Any]) -> dict[str, Any]:
    scenario = SCENARIOS.get(result.get("scenario_id"))
    villain = VILLAIN_PROFILES.get(result.get("villain_profile_id"))
    return {
        "hand_id": result.get("hand_id"),
        "session_id": result.get("session_id"),
        "owner_user_id": result.get("user_id"),
        "scenario_id": result.get("scenario_id"),
        "scenario_display_name": scenario.display_name if scenario else result.get("scenario_id"),
        "villain_profile_id": result.get("villain_profile_id"),
        "villain_display_name": villain.meta.display_name if villain else result.get("villain_profile_id"),
        "street": result.get("street"),
        "completed_at": result.get("completed_at"),
        "ranging_score": result.get("ranging_score"),
        "response_score": result.get("response_score"),
        "overall_score": result.get("overall_score"),
        "review": review_state_from_metadata(result.get("metadata")),
    }


def _street_board(board: list[str], street: str) -> list[str]:
    if street == "river":
        return list(board[:5])
    if street == "turn":
        return list(board[:4])
    if street == "flop":
        return list(board[:3])
    return []


def _event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "street": event.street.value,
        "actor": event.actor.value,
        "action": event.action.value,
        "amount": float(event.amount or 0.0),
        "note": event.note,
        "forced": bool(event.forced),
    }


def _action_title(event: Any) -> str:
    amount = float(event.amount or 0.0)
    suffix = f" {amount:g}bb" if amount > 0 else ""
    return f"{event.actor.value.title()} {event.action.value}{suffix}"


def build_hand_replay(hand_id: str, *, user: UserAccount) -> dict[str, Any]:
    result = ensure_can_view_review_hand(hand_id, user)
    try:
        hand = get_hand(hand_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    metadata = dict(result.get("metadata") or {})
    session = store.get_session(hand.session_id) or {}
    scenario = SCENARIOS.get(hand.scenario_id)
    villain = VILLAIN_PROFILES.get(hand.villain_profile_id)
    steps = _build_replay_steps(hand, session=session, metadata=metadata)

    return {
        "hand_id": hand.hand_id,
        "session_id": hand.session_id,
        "owner_user_id": hand.user_id,
        "scenario_id": hand.scenario_id,
        "scenario_display_name": scenario.display_name if scenario else hand.scenario_id,
        "villain_profile_id": hand.villain_profile_id,
        "villain_display_name": villain.meta.display_name if villain else hand.villain_profile_id,
        "hero_hand": list(hand.hero_hand),
        "villain_hand": list(hand.villain_hand),
        "final_board": list(hand.board),
        "pot": hand.pot,
        "hero_stack": hand.hero_stack,
        "villain_stack": hand.villain_stack,
        "review": review_state_from_metadata(metadata),
        "steps": steps,
    }


def _preflop_actor_payload(
    actor: str,
    *,
    session: dict[str, Any],
    hand: HandState,
) -> dict[str, Any]:
    if actor == "hero":
        tokens = list(session.get("hero_tokens_saved") or hand.hero_tokens_saved or [])
        matrix = session.get("hero_range_matrix_saved")
    else:
        tokens = list(session.get("villain_tokens_saved") or [])
        matrix = session.get("villain_range_matrix_saved")
    return {
        "actor": actor,
        "range_tokens": tokens,
        "matrix": matrix,
    }


def _build_replay_steps(hand: HandState, *, session: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    scenario = SCENARIOS.get(hand.scenario_id)
    first_actor = scenario.preflop_aggressor.value if scenario and hasattr(scenario.preflop_aggressor, "value") else (
        str(scenario.preflop_aggressor) if scenario else "hero"
    )
    if first_actor not in {"hero", "villain"}:
        first_actor = "hero"
    second_actor = "villain" if first_actor == "hero" else "hero"
    first_payload = _preflop_actor_payload(first_actor, session=session, hand=hand)
    second_payload = _preflop_actor_payload(second_actor, session=session, hand=hand)

    steps.append({
        "kind": "preflop_range",
        "street": "preflop",
        "title": "Preflop aggressor range",
        "summary": f"{len(first_payload['range_tokens'])} range labels saved.",
        "board": [],
        "details": {**first_payload, "role": "aggressor"},
    })
    steps.append({
        "kind": "preflop_range",
        "street": "preflop",
        "title": "Preflop non-aggressor range",
        "summary": f"{len(second_payload['range_tokens'])} range labels saved.",
        "board": [],
        "details": {**second_payload, "role": "non_aggressor"},
    })

    prune_evals_by_street: dict[str, list[dict[str, Any]]] = {}
    for item in metadata.get("prune_evaluations") or []:
        prune_evals_by_street.setdefault(str(item.get("street") or ""), []).append(dict(item))

    response_evals_by_street: dict[str, list[dict[str, Any]]] = {}
    for item in metadata.get("response_evaluations") or []:
        response_evals_by_street.setdefault(str(item.get("street") or ""), []).append(dict(item))

    replay_events_by_street: dict[str, list[dict[str, Any]]] = {}
    for item in hand.replay_events or []:
        if not isinstance(item, dict):
            continue
        street_name = str(item.get("street") or "")
        replay_events_by_street.setdefault(street_name, []).append(dict(item))

    events_by_street: dict[str, list[Any]] = {}
    for event in hand.history.events:
        events_by_street.setdefault(event.street.value, []).append(event)

    for street in _STREET_ORDER[1:]:
        board = _street_board(list(hand.board), street)
        if not board and not events_by_street.get(street) and not prune_evals_by_street.get(street) and not response_evals_by_street.get(street):
            continue
        steps.append({
            "kind": "street_start",
            "street": street,
            "title": f"{street.title()} board",
            "summary": " ".join(board) if board else "No board cards recorded.",
            "board": board,
            "details": {"pot": hand.pot, "hero_stack": hand.hero_stack, "villain_stack": hand.villain_stack},
        })

        response_queue = list(response_evals_by_street.get(street) or [])
        prune_queue = list(prune_evals_by_street.get(street) or [])
        replay_queue = list(replay_events_by_street.get(street) or [])
        replay_response_queue = [item for item in replay_queue if item.get("kind") == "response_matrix"]
        replay_prune_queue = [item for item in replay_queue if item.get("kind") == "prune_remove_subgroup"]
        for event in events_by_street.get(street) or []:
            if event.actor.value == "hero":
                if replay_response_queue:
                    evaluation = response_queue.pop(0) if response_queue else {}
                    steps.append(_response_step(street, board, evaluation, replay_event=replay_response_queue.pop(0)))
                elif response_queue:
                    steps.append(_response_step(street, board, response_queue.pop(0)))
            steps.append({
                "kind": "action",
                "street": street,
                "title": _action_title(event),
                "summary": event.note or ("Forced action" if event.forced else "Action event"),
                "board": board,
                "details": {"event": _event_to_dict(event)},
            })
            if event.actor.value == "villain":
                while replay_prune_queue:
                    steps.append(_prune_subgroup_step(street, board, replay_prune_queue.pop(0)))
                if prune_queue:
                    steps.append(_prune_step(street, board, prune_queue.pop(0)))
        for evaluation in response_queue:
            steps.append(_response_step(street, board, evaluation))
        for evaluation in prune_queue:
            steps.append(_prune_step(street, board, evaluation))

    return steps


def _response_step(
    street: str,
    board: list[str],
    evaluation: dict[str, Any],
    *,
    replay_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actual = evaluation.get("actual") or "not scored"
    predicted = evaluation.get("predicted") or "none"
    details = dict(evaluation)
    if replay_event:
        details.update(dict(replay_event.get("details") or {}))
        details["replay_event_kind"] = replay_event.get("kind")
    return {
        "kind": "response_matrix",
        "street": street,
        "title": "Response matrix",
        "summary": f"Selected {predicted}; villain response was {actual}.",
        "board": board,
        "details": details,
    }


def _prune_step(street: str, board: list[str], evaluation: dict[str, Any]) -> dict[str, Any]:
    start = evaluation.get("start_live_combos")
    end = evaluation.get("end_live_combos")
    return {
        "kind": "range_prune",
        "street": street,
        "title": "Villain range prune",
        "summary": f"Live combos moved from {start} to {end}.",
        "board": board,
        "details": evaluation,
    }


def _prune_subgroup_step(street: str, board: list[str], replay_event: dict[str, Any]) -> dict[str, Any]:
    details = dict(replay_event.get("details") or {})
    bucket = details.get("bucket") or "bucket"
    subgroup = details.get("subgroup") or "subgroup"
    before = details.get("before_live_combos")
    after = details.get("after_live_combos")
    return {
        "kind": "range_prune",
        "street": street,
        "title": f"Removed {subgroup}",
        "summary": f"{bucket}: live combos moved from {before} to {after}.",
        "board": board,
        "details": {
            **details,
            "actual_bucket": bucket,
            "actual_subgroup": subgroup,
            "replay_event_kind": replay_event.get("kind"),
        },
    }
