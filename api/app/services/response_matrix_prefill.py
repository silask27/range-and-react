# File: api/app/services/response_matrix_prefill.py
# Summary: Shared helpers for carrying narrow response-matrix defaults between
# street nodes without treating them as completed user saves.

from __future__ import annotations

from typing import Any

from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.models.enums import Street
from api.app.models.state import HandState


def _current_live_bucket_rows(
    hand: HandState,
    *,
    iters: int | None,
) -> list[str]:
    bucket_view = build_bucket_matrix_view(
        villain_range_combos_live=hand.villain_range_combos_live,
        board=hand.board,
        hero_hand=hand.hero_hand,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        iters=iters,
        seed=int(hand.bucket_seed),
    )

    rows = bucket_view.get("rows", [])
    if not isinstance(rows, list):
        return []

    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        bucket_name = row.get("bucket_name")
        combo_count = row.get("combo_count")
        if isinstance(bucket_name, str) and isinstance(combo_count, int) and combo_count > 0:
            out.append(bucket_name)
    return out


def _turn_draw_to_river_air_prefill(
    hand: HandState,
    *,
    iters: int | None,
) -> dict[str, Any] | None:
    previous_saved = hand.response_matrix_saved
    if hand.street != Street.RIVER or not isinstance(previous_saved, dict):
        return None
    if previous_saved.get("street") != Street.TURN.value:
        return None

    previous_selections = previous_saved.get("selections")
    if not isinstance(previous_selections, dict):
        return None
    if "Air" in previous_selections or "Draw" not in previous_selections:
        return None

    draw_row = previous_selections.get("Draw")
    if not isinstance(draw_row, dict):
        return None

    columns = list(hand.response_matrix_columns)
    if not columns:
        return None

    row_order = _current_live_bucket_rows(hand, iters=iters)
    if "Air" not in row_order:
        return None

    air_defaults = {
        column: str(draw_row.get(column, ""))
        for column in columns
    }
    if not any(air_defaults.values()):
        return None

    selections: dict[str, dict[str, str]] = {}
    for row_name in row_order:
        selections[row_name] = {column: "" for column in columns}
    selections["Air"] = air_defaults

    return {
        "street": Street.RIVER.value,
        "columns": columns,
        "row_order": row_order,
        "selections": selections,
        "complete": False,
        "allow_partial": False,
        "save_reason": "turn_draw_to_river_air_prefill",
        "prefill_source": {
            "from_street": Street.TURN.value,
            "from_bucket": "Draw",
            "to_bucket": "Air",
        },
    }


def prepare_response_matrix_for_new_node(
    hand: HandState,
    *,
    iters: int | None,
) -> None:
    """
    Reset response-matrix node state, with one narrow prefill exception:
    when a new River matrix contains Air that did not exist in the saved Turn
    matrix, inherit Air's defaults from the Turn Draw row.
    """
    prefill = _turn_draw_to_river_air_prefill(hand, iters=iters)
    hand.response_matrix_saved = prefill or {}
