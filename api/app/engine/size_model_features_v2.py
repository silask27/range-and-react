from __future__ import annotations

from typing import Any

SIZE_MODEL_KINDS_V2 = [
    "open_bet",
    "raise_vs_bet",
    "reraise_vs_raise",
]



def _bool_to_int(value: object) -> object:
    if isinstance(value, bool):
        return int(value)
    return value



def _equity_bucket(hand_equity: float) -> str:
    value = float(hand_equity)
    if value < 0.15:
        return "eq_00_15"
    if value < 0.30:
        return "eq_15_30"
    if value < 0.45:
        return "eq_30_45"
    if value < 0.60:
        return "eq_45_60"
    if value < 0.75:
        return "eq_60_75"
    if value < 0.90:
        return "eq_75_90"
    return "eq_90_100"



def _spr_bucket(spr: float) -> str:
    value = float(spr)
    if value < 2.0:
        return "spr_lt_2"
    if value < 4.0:
        return "spr_2_4"
    if value < 8.0:
        return "spr_4_8"
    return "spr_ge_8"



def _vulnerability_bucket(vulnerability: float, hand_subgroup: str) -> str:
    subgroup = str(hand_subgroup or "NA")
    if subgroup in {"Air", "Gutshot", "Straight Draw", "Flush Draw", "Combo Draw"} or "Draw" in subgroup:
        return "not_applicable"
    value = float(vulnerability)
    if value <= 0.05:
        return "very_low"
    if value <= 0.20:
        return "low"
    if value <= 0.40:
        return "medium"
    if value <= 0.65:
        return "high"
    return "very_high"



def _facing_size_bucket(facing_size_pct_pot: float) -> str:
    value = float(facing_size_pct_pot)
    if value <= 0.33:
        return "tiny"
    if value <= 0.66:
        return "small"
    if value <= 1.00:
        return "medium"
    if value <= 1.50:
        return "large"
    return "overbet"



def _pot_size_bucket(pot_size: float) -> str:
    value = float(pot_size)
    if value < 10.0:
        return "pot_lt_10"
    if value < 25.0:
        return "pot_10_25"
    if value < 60.0:
        return "pot_25_60"
    if value < 120.0:
        return "pot_60_120"
    return "pot_ge_120"



def _board_type_compact(raw_features: dict[str, object]) -> str:
    paired = bool(raw_features.get("board_paired"))
    monotone = bool(raw_features.get("board_monotone"))
    two_tone = bool(raw_features.get("board_two_tone"))
    rainbow = bool(raw_features.get("board_rainbow"))
    flush_completed = bool(raw_features.get("board_flush_completed"))
    straight_completed = bool(raw_features.get("board_straight_completed"))
    connected = bool(raw_features.get("board_connected"))

    if flush_completed and straight_completed:
        return "flush_and_straight_complete"
    if flush_completed:
        return "flush_complete"
    if straight_completed:
        return "straight_complete"

    pair_tag = "paired" if paired else "unpaired"
    if monotone:
        tone_tag = "monotone"
    elif two_tone:
        tone_tag = "two_tone"
    elif rainbow:
        tone_tag = "rainbow"
    else:
        tone_tag = "mixed"
    conn_tag = "connected" if connected else "disconnected"
    return f"{pair_tag}_{tone_tag}_{conn_tag}"



def build_size_feature_dict_v2(raw_features: dict[str, object], model_kind: str) -> dict[str, object]:
    if model_kind not in SIZE_MODEL_KINDS_V2:
        raise ValueError(f"Unknown size model kind: {model_kind}")

    villain_type = str(raw_features.get("villain_type") or "NA")
    hand_subgroup = str(raw_features.get("hand_subgroup") or "NA")
    scenario_id = str(raw_features.get("scenario_id") or "NA")
    street = str(raw_features.get("street") or "NA")
    previous_action_summary = str(raw_features.get("previous_action_summary") or "NA")
    current_aggressor = str(raw_features.get("current_aggressor") or "NA")
    previous_street_villain_last_action = str(raw_features.get("previous_street_villain_last_action") or "NA")
    hero_prev_street_last_action_type = str(raw_features.get("hero_prev_street_last_action_type") or "NA")
    opponent_perceived_strength = str(raw_features.get("opponent_perceived_strength") or "NA")
    board_high_card_bucket = str(raw_features.get("board_high_card_bucket") or "NA")
    open_action_type = str(raw_features.get("open_action_type") or "NA")

    hand_equity = float(raw_features.get("hand_equity") or 0.0)
    current_strength = float(raw_features.get("current_strength") or 0.0)
    spr = float(raw_features.get("spr") or 0.0)
    vulnerability_score = float(raw_features.get("vulnerability_score") or 0.0)
    facing_size_raw = float(raw_features.get("facing_size_raw") or 0.0)
    facing_size_pct_pot = float(raw_features.get("facing_size_pct_pot") or 0.0)
    facing_size_pct_stack = float(raw_features.get("facing_size_pct_stack") or 0.0)
    facing_previous_bet_raw = float(raw_features.get("facing_previous_bet_raw") or 0.0)
    facing_raise_multiple = float(raw_features.get("facing_raise_multiple") or 0.0)
    pot_size = float(raw_features.get("pot_size") or 0.0)
    street_start_pot = float(raw_features.get("street_start_pot") or 0.0)
    facing_pot_before_action = float(raw_features.get("facing_pot_before_action") or pot_size)
    effective_stack_size = float(raw_features.get("effective_stack_size") or 0.0)

    hand_equity_bucket = _equity_bucket(hand_equity)
    current_strength_bucket = _equity_bucket(current_strength)
    spr_bucket = _spr_bucket(spr)
    vulnerability_bucket = _vulnerability_bucket(vulnerability_score, hand_subgroup)
    facing_size_bucket = _facing_size_bucket(facing_size_pct_pot)
    pot_size_bucket = _pot_size_bucket(pot_size)
    board_type_compact = _board_type_compact(raw_features)

    out: dict[str, object] = {
        "villain_type": villain_type,
        "scenario_id": scenario_id,
        "street": street,
        "villain_is_ip": _bool_to_int(raw_features.get("villain_is_ip")),
        "pot_size": pot_size,
        "street_start_pot": street_start_pot,
        "facing_pot_before_action": facing_pot_before_action,
        "effective_stack_size": effective_stack_size,
        "spr": spr,
        "hand_equity": hand_equity,
        "current_strength": current_strength,
        "hand_subgroup": hand_subgroup,
        "previous_action_summary": previous_action_summary,
        "current_aggressor": current_aggressor,
        "previous_street_villain_last_action": previous_street_villain_last_action,
        "hero_prev_street_last_action_type": hero_prev_street_last_action_type,
        "hero_prev_street_last_aggressive_size_pct_pot": float(raw_features.get("hero_prev_street_last_aggressive_size_pct_pot") or 0.0),
        "hero_prev_street_total_investment_pct_pot": float(raw_features.get("hero_prev_street_total_investment_pct_pot") or 0.0),
        "hero_prev_street_called_raise": _bool_to_int(raw_features.get("hero_prev_street_called_raise")),
        "previous_street_ended_aggressive": _bool_to_int(raw_features.get("previous_street_ended_aggressive")),
        "opponent_perceived_strength": opponent_perceived_strength,
        "board_high_card_bucket": board_high_card_bucket,
        "board_paired": _bool_to_int(raw_features.get("board_paired")),
        "board_rainbow": _bool_to_int(raw_features.get("board_rainbow")),
        "board_monotone": _bool_to_int(raw_features.get("board_monotone")),
        "board_two_tone": _bool_to_int(raw_features.get("board_two_tone")),
        "board_flush_completed": _bool_to_int(raw_features.get("board_flush_completed")),
        "board_straight_completed": _bool_to_int(raw_features.get("board_straight_completed")),
        "board_connected": _bool_to_int(raw_features.get("board_connected")),
        "vulnerability_score": vulnerability_score,
        "hand_equity_bucket": hand_equity_bucket,
        "current_strength_bucket": current_strength_bucket,
        "spr_bucket": spr_bucket,
        "vulnerability_bucket": vulnerability_bucket,
        "pot_size_bucket": pot_size_bucket,
        "board_type_compact": board_type_compact,
        "vx_hand_subgroup": f"{villain_type}__{hand_subgroup}",
        "vx_previous_action_summary": f"{villain_type}__{previous_action_summary}",
        "vx_scenario_id": f"{villain_type}__{scenario_id}",
        "vx_street": f"{villain_type}__{street}",
        "vx_hand_equity_bucket": f"{villain_type}__{hand_equity_bucket}",
        "vx_current_strength_bucket": f"{villain_type}__{current_strength_bucket}",
        "vx_spr_bucket": f"{villain_type}__{spr_bucket}",
        "vx_vulnerability_bucket": f"{villain_type}__{vulnerability_bucket}",
        "vx_board_type_compact": f"{villain_type}__{board_type_compact}",
        "sx_previous_action_summary": f"{scenario_id}__{previous_action_summary}",
        "sx_street": f"{scenario_id}__{street}",
    }

    if model_kind == "open_bet":
        out.update(
            {
                "open_action_type": open_action_type,
                "vx_open_action_type": f"{villain_type}__{open_action_type}",
            }
        )
    else:
        out.update(
            {
                "facing_size_raw": facing_size_raw,
                "facing_size_pct_pot": facing_size_pct_pot,
                "facing_size_pct_stack": facing_size_pct_stack,
                "facing_previous_bet_raw": facing_previous_bet_raw,
                "facing_raise_multiple": facing_raise_multiple,
                "facing_size_bucket": facing_size_bucket,
                "vx_facing_size_bucket": f"{villain_type}__{facing_size_bucket}",
            }
        )

    return out



def feature_columns_for_size_model_v2(model_kind: str) -> list[str]:
    common = [
        "villain_type",
        "scenario_id",
        "street",
        "villain_is_ip",
        "pot_size",
        "street_start_pot",
        "facing_pot_before_action",
        "effective_stack_size",
        "spr",
        "hand_equity",
        "current_strength",
        "hand_subgroup",
        "previous_action_summary",
        "current_aggressor",
        "previous_street_villain_last_action",
        "hero_prev_street_last_action_type",
        "hero_prev_street_last_aggressive_size_pct_pot",
        "hero_prev_street_total_investment_pct_pot",
        "hero_prev_street_called_raise",
        "previous_street_ended_aggressive",
        "opponent_perceived_strength",
        "board_high_card_bucket",
        "board_paired",
        "board_rainbow",
        "board_monotone",
        "board_two_tone",
        "board_flush_completed",
        "board_straight_completed",
        "board_connected",
        "vulnerability_score",
        "hand_equity_bucket",
        "current_strength_bucket",
        "spr_bucket",
        "vulnerability_bucket",
        "pot_size_bucket",
        "board_type_compact",
        "vx_hand_subgroup",
        "vx_previous_action_summary",
        "vx_scenario_id",
        "vx_street",
        "vx_hand_equity_bucket",
        "vx_current_strength_bucket",
        "vx_spr_bucket",
        "vx_vulnerability_bucket",
        "vx_board_type_compact",
        "sx_previous_action_summary",
        "sx_street",
    ]
    if model_kind == "open_bet":
        return common + [
            "open_action_type",
            "vx_open_action_type",
        ]
    if model_kind in {"raise_vs_bet", "reraise_vs_raise"}:
        return common + [
            "facing_size_raw",
            "facing_size_pct_pot",
            "facing_size_pct_stack",
            "facing_previous_bet_raw",
            "facing_raise_multiple",
            "facing_size_bucket",
            "vx_facing_size_bucket",
        ]
    raise ValueError(f"Unknown size model kind: {model_kind}")



def categorical_columns_for_size_model_v2(model_kind: str) -> list[str]:
    common = [
        "villain_type",
        "scenario_id",
        "street",
        "hand_subgroup",
        "previous_action_summary",
        "current_aggressor",
        "previous_street_villain_last_action",
        "hero_prev_street_last_action_type",
        "opponent_perceived_strength",
        "board_high_card_bucket",
        "hand_equity_bucket",
        "current_strength_bucket",
        "spr_bucket",
        "vulnerability_bucket",
        "pot_size_bucket",
        "board_type_compact",
        "vx_hand_subgroup",
        "vx_previous_action_summary",
        "vx_scenario_id",
        "vx_street",
        "vx_hand_equity_bucket",
        "vx_current_strength_bucket",
        "vx_spr_bucket",
        "vx_vulnerability_bucket",
        "vx_board_type_compact",
        "sx_previous_action_summary",
        "sx_street",
    ]
    if model_kind == "open_bet":
        return common + [
            "open_action_type",
            "vx_open_action_type",
        ]
    if model_kind in {"raise_vs_bet", "reraise_vs_raise"}:
        return common + [
            "facing_size_bucket",
            "vx_facing_size_bucket",
        ]
    raise ValueError(f"Unknown size model kind: {model_kind}")
