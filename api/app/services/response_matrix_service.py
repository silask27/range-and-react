# File: api/app/services/response_matrix_service.py
# Summary: Service-layer helpers for validating and saving the Screen 3 response matrix before hero is allowed to act.

from __future__ import annotations

from dataclasses import fields

from api.app.data.catalog import get_scenario
from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.models.enums import (
    ActionType,
    AggressionResponse,
    CallResponse,
    CheckResponse,
    Player,
    ResponseColumnType,
    UIGate,
)
from api.app.models.state import HandState
from api.app.storage.memory_store import store


_DEFAULT_VALID_RESPONSES_BY_COLUMN: dict[str, set[str]] = {
    ResponseColumnType.CHECK.value: {CheckResponse.BET.value, CheckResponse.CHECK.value},
    ResponseColumnType.BET_SMALL.value: {
        AggressionResponse.FOLD.value,
        AggressionResponse.CALL.value,
        AggressionResponse.RAISE.value,
    },
    ResponseColumnType.BET_BIG.value: {
        AggressionResponse.FOLD.value,
        AggressionResponse.CALL.value,
        AggressionResponse.RAISE.value,
    },
    ResponseColumnType.RAISE.value: {
        AggressionResponse.FOLD.value,
        AggressionResponse.CALL.value,
        AggressionResponse.RAISE.value,
    },
    ResponseColumnType.CALL.value: {
        CallResponse.PASSIVE.value,
        CallResponse.AGGRESSIVE.value,
    },
}


def _hand_to_store_payload(hand: HandState) -> dict:
    """
    Store a shallow field mapping so nested dataclasses remain typed objects.
    """
    return {f.name: getattr(hand, f.name) for f in fields(HandState)}


def _hand_from_store(hand_id: str) -> HandState:
    payload = store.get_hand(hand_id)
    if payload is None:
        raise ValueError(f"Unknown hand_id: {hand_id}")
    return HandState(**payload)


def _current_bucket_row_order(
    hand: HandState,
    *,
    iters: int | None,
) -> list[str]:
    """
    Return the current broad-bucket row order for the hand.

    Important:
    - Always use hand.bucket_seed so the frontend and backend validate against
      the same deterministic bucket rows for a given hand state.
    - The updated bucketizer may contain subgroup sections within each broad
      bucket row, but the response matrix is still keyed by broad bucket name.
    - If iters is omitted, the bucket pipeline falls back to the street-specific
      defaults defined in bucketizer.py.
    """
    bucket_view = build_bucket_matrix_view(
        villain_range_combos_live=hand.villain_range_combos_live,
        board=hand.board,
        hero_hand=hand.hero_hand,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        iters=iters,
        seed=int(hand.bucket_seed),
    )
    return list(bucket_view["row_order"])


def _latest_street_event(hand: HandState):
    for event in reversed(hand.history.events):
        if event.street == hand.street:
            return event
    return None


def _is_ip_checkback_node(hand: HandState) -> bool:
    """
    Return True when the current response-matrix node represents:

    - hero is in position
    - villain has checked to hero on this street
    - hero is not facing a bet

    In this spot, the "If I Check" column is really asking:
    "If I check back, what is villain's likely future posture?"
    so the valid responses should be P / A instead of B / X.
    """
    scenario = get_scenario(hand.scenario_id)

    if not scenario.hero_is_ip:
        return False

    if hand.current_actor != Player.HERO:
        return False

    if hand.betting_round.to_call_for(Player.HERO) > 0:
        return False

    latest_event = _latest_street_event(hand)
    if latest_event is None:
        return False

    return (
        latest_event.actor == Player.VILLAIN
        and latest_event.action == ActionType.CHECK
        and latest_event.street == hand.street
    )


def _valid_responses_by_column_for_hand(hand: HandState) -> dict[str, set[str]]:
    """
    Build the valid response alphabet for the current node.

    Most columns are static, but the CHECK column is context-sensitive:
    - default: B / X
    - hero IP after villain checks: P / A
    """
    valid = {
        column: set(values)
        for column, values in _DEFAULT_VALID_RESPONSES_BY_COLUMN.items()
    }

    if _is_ip_checkback_node(hand):
        valid[ResponseColumnType.CHECK.value] = {
            CallResponse.PASSIVE.value,
            CallResponse.AGGRESSIVE.value,
        }

    return valid


def _validate_and_normalize_response_matrix_payload(
    *,
    hand: HandState,
    row_order: list[str],
    columns: list[str],
    selections: dict,
    allow_partial: bool,
) -> dict[str, dict[str, str]]:
    """
    Validate the incoming response matrix and return the normalized payload that
    should be persisted to hand.response_matrix_saved["selections"].

    Complete-save mode:
    - rows must match exactly
    - columns per row must match exactly
    - every value must be a valid non-blank response

    Partial-save mode:
    - missing rows are allowed
    - missing columns are allowed
    - blank / omitted selections are allowed and are normalized to ""
    - present non-blank selections must still be valid for the current node
    """
    if not isinstance(selections, dict):
        raise ValueError("selections must be an object keyed by bucket name")

    expected_rows = set(row_order)
    actual_rows = set(selections.keys())
    extra_rows = sorted(actual_rows - expected_rows)
    if extra_rows:
        raise ValueError(
            "selections contains unsupported bucket rows. "
            f"Extra={extra_rows[:5]}"
        )

    valid_responses_by_column = _valid_responses_by_column_for_hand(hand)
    expected_cols = set(columns)

    if not allow_partial and actual_rows != expected_rows:
        missing = sorted(expected_rows - actual_rows)
        extra = sorted(actual_rows - expected_rows)
        raise ValueError(
            "selections must contain exactly the current bucket rows. "
            f"Missing={missing[:5]} Extra={extra[:5]}"
        )

    normalized: dict[str, dict[str, str]] = {}

    for bucket_name in row_order:
        row_payload = selections.get(bucket_name, {})

        if row_payload is None:
            row_payload = {}

        if not isinstance(row_payload, dict):
            raise ValueError(f"Row payload for bucket {bucket_name!r} must be an object")

        actual_cols = set(row_payload.keys())
        extra_cols = sorted(actual_cols - expected_cols)
        if extra_cols:
            raise ValueError(
                f"Row {bucket_name!r} contains unsupported columns. "
                f"Extra={extra_cols[:5]}"
            )

        if not allow_partial and actual_cols != expected_cols:
            missing = sorted(expected_cols - actual_cols)
            extra = sorted(actual_cols - expected_cols)
            raise ValueError(
                f"Row {bucket_name!r} must contain exactly the current columns. "
                f"Missing={missing[:5]} Extra={extra[:5]}"
            )

        normalized_row: dict[str, str] = {}

        for column in columns:
            if column not in valid_responses_by_column:
                raise ValueError(f"Unsupported response matrix column: {column!r}")

            if column not in row_payload:
                if allow_partial:
                    normalized_row[column] = ""
                    continue
                raise ValueError(
                    f"Row {bucket_name!r} is missing required column {column!r}"
                )

            value = row_payload[column]

            if allow_partial and (value is None or value == ""):
                normalized_row[column] = ""
                continue

            if not isinstance(value, str):
                raise ValueError(
                    f"Selection for row {bucket_name!r}, column {column!r} must be a string"
                )

            if value not in valid_responses_by_column[column]:
                allowed = sorted(valid_responses_by_column[column])
                raise ValueError(
                    f"Invalid selection for row {bucket_name!r}, column {column!r}: {value!r}. "
                    f"Allowed={allowed}"
                )

            normalized_row[column] = value

        normalized[bucket_name] = normalized_row

    return normalized


def save_response_matrix(
    hand_id: str,
    *,
    selections: dict,
    iters: int | None = None,
    seed: int = 42,
    allow_partial: bool = False,
    save_reason: str | None = None,
) -> HandState:
    """
    Validate and save the Screen 3 response matrix.

    Important:
    - The optional seed argument is accepted for backward compatibility but is
      intentionally ignored. Validation always uses hand.bucket_seed.
    - This fixes the old issue where the frontend could save against one bucket
      view while the backend validated against a slightly different regenerated
      row set.
    - If iters is omitted, validation uses the street-specific bucketizer
      defaults rather than forcing a fixed Monte Carlo iteration count.
    - allow_partial=True is intended for timer-expiry saves only and permits
      blank / omitted selections to be persisted as empty strings.
    - save_reason marks whether the save came from a manual complete save or
      a timer-expiry auto-save, so later gate checks can distinguish the two.

    On success:
    - response_matrix_saved is updated with the normalized saved payload
    - ui_gate is switched to HERO_TO_ACT
    """
    del seed

    hand = _hand_from_store(hand_id)

    if hand.ui_gate != UIGate.MUST_FILL_RESPONSE_MATRIX:
        raise ValueError(
            f"Hand {hand_id} is not in must_fill_response_matrix gate; current gate={hand.ui_gate}"
        )

    columns = list(hand.response_matrix_columns)
    if not columns:
        raise ValueError(f"Hand {hand_id} has no response_matrix_columns to validate against")

    row_order = _current_bucket_row_order(hand, iters=iters)

    normalized_selections = _validate_and_normalize_response_matrix_payload(
        hand=hand,
        row_order=row_order,
        columns=columns,
        selections=selections,
        allow_partial=allow_partial,
    )

    hand.response_matrix_saved = {
        "street": hand.street.value,
        "columns": columns,
        "row_order": row_order,
        "selections": normalized_selections,
        "complete": not allow_partial,
        "allow_partial": allow_partial,
        "save_reason": save_reason or ("timer_expired" if allow_partial else "manual"),
    }
    hand.ui_gate = UIGate.HERO_TO_ACT

    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand
