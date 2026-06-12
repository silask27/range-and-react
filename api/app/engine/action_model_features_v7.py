from __future__ import annotations

from math import log2
from typing import Any

from api.app.engine.action_model_features_v6 import ACTIONS_BY_NODE_V6 as ACTIONS_BY_NODE_V7
from api.app.engine.semantic_features_v7 import build_semantic_features_v7


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_to_int(value: object) -> int:
    return int(bool(value))


def _bucket(value: float, cuts: list[float], labels: list[str]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def _equity_bucket(value: float) -> str:
    return _bucket(float(value), [0.15, 0.30, 0.45, 0.60, 0.75, 0.90], ["eq_00_15", "eq_15_30", "eq_30_45", "eq_45_60", "eq_60_75", "eq_75_90", "eq_90_100"])


def _spr_bucket(value: float) -> str:
    return _bucket(float(value), [2.0, 4.0, 8.0], ["spr_lt_2", "spr_2_4", "spr_4_8", "spr_ge_8"])


def _size_bucket(value: float) -> str:
    return _bucket(float(value), [0.34, 0.67, 1.01, 1.51], ["tiny", "small", "medium", "large", "overbet"])


def _pot_bucket(value: float) -> str:
    return _bucket(float(value), [10.0, 25.0, 60.0, 120.0], ["pot_lt_10", "pot_10_25", "pot_25_60", "pot_60_120", "pot_ge_120"])


def _normalize_probs(probs: dict[str, float], actions: list[str]) -> dict[str, float]:
    cleaned = {action: max(0.0, float(probs.get(action, 0.0))) for action in actions}
    total = sum(cleaned.values())
    if total <= 0.0:
        return {action: 1.0 / len(actions) for action in actions}
    return {action: value / total for action, value in cleaned.items()}


def _entropy(probs: dict[str, float]) -> float:
    denom = log2(max(1, len(probs)))
    if denom <= 0.0:
        return 0.0
    return float(-sum(p * log2(p) for p in probs.values() if p > 0.0) / denom)


def _top_margin(probs: dict[str, float]) -> float:
    values = sorted(probs.values(), reverse=True)
    if len(values) < 2:
        return float(values[0]) if values else 0.0
    return float(values[0] - values[1])


def _board_type(raw: dict[str, object]) -> str:
    pair = "paired" if bool(raw.get("board_paired")) else "unpaired"
    if bool(raw.get("board_monotone")):
        tone = "monotone"
    elif bool(raw.get("board_two_tone")):
        tone = "two_tone"
    elif bool(raw.get("board_rainbow")):
        tone = "rainbow"
    else:
        tone = "mixed"
    conn = "connected" if bool(raw.get("board_connected")) else "disconnected"
    if bool(raw.get("board_flush_completed")) and bool(raw.get("board_straight_completed")):
        return f"{pair}_flush_straight_complete"
    if bool(raw.get("board_flush_completed")):
        return f"{pair}_flush_complete"
    if bool(raw.get("board_straight_completed")):
        return f"{pair}_straight_complete"
    return f"{pair}_{tone}_{conn}"


def build_action_features_v7(*, spot: Any, raw_context: dict[str, object]) -> dict[str, object]:
    villain = str(raw_context.get("villain_type") or getattr(spot, "villain_type", "NA"))
    node = str(raw_context.get("node") or getattr(spot, "node", "NA"))
    street = str(raw_context.get("street") or getattr(spot, "street", "NA"))
    scenario = str(raw_context.get("scenario_id") or getattr(spot, "scenario_id", "NA"))
    hand_subgroup = str(raw_context.get("hand_subgroup") or "NA")
    current_aggressor = str(raw_context.get("current_aggressor") or "NA")
    previous_summary = str(raw_context.get("previous_action_summary") or "NA")
    open_action_type = str(raw_context.get("open_action_type") or "NA")
    hand_equity = _float(raw_context.get("hand_equity"))
    current_strength = _float(raw_context.get("current_strength"))
    spr = _float(raw_context.get("spr"))
    facing_size_pct_pot = _float(raw_context.get("facing_size_pct_pot"))
    facing_size_pct_stack = _float(raw_context.get("facing_size_pct_stack"))
    board_type = _board_type(raw_context)
    hand_equity_bucket = _equity_bucket(hand_equity)
    current_strength_bucket = _equity_bucket(current_strength)
    spr_bucket = _spr_bucket(spr)
    facing_size_bucket = _size_bucket(facing_size_pct_pot)
    stack_bucket = _bucket(facing_size_pct_stack, [0.20, 0.40, 0.70, 1.00], ["lt_20", "20_40", "40_70", "70_100", "all_in_or_more"])

    out: dict[str, object] = {
        "node": node,
        "villain_type": villain,
        "street": street,
        "scenario_id": scenario,
        "hand_subgroup": hand_subgroup,
        "hand_equity": hand_equity,
        "current_strength": current_strength,
        "hand_equity_bucket": hand_equity_bucket,
        "current_strength_bucket": current_strength_bucket,
        "spr": spr,
        "spr_bucket": spr_bucket,
        "pot_size": _float(raw_context.get("pot_size")),
        "pot_size_bucket": _pot_bucket(_float(raw_context.get("pot_size"))),
        "street_start_pot": _float(raw_context.get("street_start_pot")),
        "facing_pot_before_action": _float(raw_context.get("facing_pot_before_action")),
        "effective_stack_size": _float(raw_context.get("effective_stack_size")),
        "villain_is_ip": _bool_to_int(raw_context.get("villain_is_ip")),
        "facing_size_raw": _float(raw_context.get("facing_size_raw")),
        "facing_size_pct_pot": facing_size_pct_pot,
        "facing_size_pct_stack": facing_size_pct_stack,
        "facing_size_pct_stack_bucket": stack_bucket,
        "facing_previous_bet_raw": _float(raw_context.get("facing_previous_bet_raw")),
        "facing_raise_multiple": _float(raw_context.get("facing_raise_multiple")),
        "facing_size_bucket": facing_size_bucket,
        "previous_action_summary": previous_summary,
        "current_aggressor": current_aggressor,
        "previous_street_villain_last_action": str(raw_context.get("previous_street_villain_last_action") or "NA"),
        "hero_prev_street_last_action_type": str(raw_context.get("hero_prev_street_last_action_type") or "NA"),
        "hero_prev_street_last_aggressive_size_pct_pot": _float(raw_context.get("hero_prev_street_last_aggressive_size_pct_pot")),
        "hero_prev_street_total_investment_pct_pot": _float(raw_context.get("hero_prev_street_total_investment_pct_pot")),
        "hero_prev_street_called_raise": _bool_to_int(raw_context.get("hero_prev_street_called_raise")),
        "previous_street_ended_aggressive": _bool_to_int(raw_context.get("previous_street_ended_aggressive")),
        "opponent_perceived_strength": _float(raw_context.get("opponent_perceived_strength")),
        "board_high_card_bucket": str(raw_context.get("board_high_card_bucket") or "NA"),
        "board_type_compact": board_type,
        "board_paired": _bool_to_int(raw_context.get("board_paired")),
        "board_rainbow": _bool_to_int(raw_context.get("board_rainbow")),
        "board_monotone": _bool_to_int(raw_context.get("board_monotone")),
        "board_two_tone": _bool_to_int(raw_context.get("board_two_tone")),
        "board_flush_completed": _bool_to_int(raw_context.get("board_flush_completed")),
        "board_straight_completed": _bool_to_int(raw_context.get("board_straight_completed")),
        "board_connected": _bool_to_int(raw_context.get("board_connected")),
        "vulnerability_score": _float(raw_context.get("vulnerability_score")),
        "open_action_type": open_action_type,
        "vx_node": f"{villain}__{node}",
        "vx_street": f"{villain}__{street}",
        "vx_scenario": f"{villain}__{scenario}",
        "vx_hand_subgroup": f"{villain}__{hand_subgroup}",
        "vx_current_strength_bucket": f"{villain}__{current_strength_bucket}",
        "vx_hand_equity_bucket": f"{villain}__{hand_equity_bucket}",
        "vx_spr_bucket": f"{villain}__{spr_bucket}",
        "vx_board_type": f"{villain}__{board_type}",
        "vx_previous_action_summary": f"{villain}__{previous_summary}",
        "vx_current_aggressor": f"{villain}__{current_aggressor}",
        "vx_open_action_type": f"{villain}__{open_action_type}",
        "sx_node": f"{scenario}__{node}",
        "sx_street": f"{scenario}__{street}",
        "sx_hand_subgroup": f"{scenario}__{hand_subgroup}",
        "vsx_node": f"{villain}__{scenario}__{node}",
        "vsx_street": f"{villain}__{scenario}__{street}",
    }
    semantic = build_semantic_features_v7(spot, raw_context)
    out.update(semantic)
    out.update(
        {
            "vx_range_strength": f"{villain}__{current_strength_bucket}__{semantic['range_advantage_bucket']}",
            "vx_theory_strength": f"{villain}__{current_strength_bucket}__{semantic['theory_checkback_pressure_bucket']}",
            "vx_stack_strength": f"{villain}__{stack_bucket}__{current_strength_bucket}",
            "street_stack_pressure": f"{street}__{stack_bucket}",
            "node_stack_pressure": f"{node}__{stack_bucket}",
            "node_range_advantage": f"{node}__{semantic['range_advantage_bucket']}",
            "node_bluff_candidate": f"{node}__{semantic['bluff_candidate_bucket']}",
            "node_river_bluff_role": f"{node}__{semantic['river_bluff_role']}",
            "node_stack_bluff_suppression": f"{node}__{stack_bucket}__{semantic['river_bluff_role']}",
            "vx_stack_bluff_role": f"{villain}__{stack_bucket}__{semantic['river_bluff_role']}",
            "vx_leverage_action_spot": f"{villain}__{node}__{semantic['river_bluff_role']}__{semantic['range_advantage_bucket']}",
        }
    )
    actions = ACTIONS_BY_NODE_V7.get(node, [])
    prior_probs = _normalize_probs(
        {action: _float(raw_context.get(f"v6_prior_p_{action}")) for action in actions},
        actions,
    ) if actions else {}
    if prior_probs:
        prior_top_action = max(prior_probs, key=prior_probs.get)
        for action in actions:
            out[f"v6_prior_p_{action}"] = float(prior_probs[action])
        out["v6_prior_top_action"] = prior_top_action
        out["v6_prior_top_prob"] = float(prior_probs[prior_top_action])
        out["v6_prior_top_margin"] = _top_margin(prior_probs)
        out["v6_prior_entropy"] = _entropy(prior_probs)
        out["vx_v6_prior_top_action"] = f"{villain}__{prior_top_action}"
        out["street_v6_prior_top_action"] = f"{street}__{prior_top_action}"
    return out


NUMERIC_FEATURES_V7 = [
    "hand_equity", "current_strength", "spr", "pot_size", "street_start_pot",
    "facing_pot_before_action", "effective_stack_size", "villain_is_ip",
    "facing_size_raw", "facing_size_pct_pot", "facing_size_pct_stack",
    "facing_previous_bet_raw", "facing_raise_multiple",
    "hero_prev_street_last_aggressive_size_pct_pot",
    "hero_prev_street_total_investment_pct_pot", "hero_prev_street_called_raise",
    "previous_street_ended_aggressive", "opponent_perceived_strength",
    "board_paired", "board_rainbow", "board_monotone", "board_two_tone",
    "board_flush_completed", "board_straight_completed", "board_connected",
    "vulnerability_score", "hero_scenario_weight", "hero_fixed_weight",
    "hero_scenario_combo_count", "hero_fixed_combo_count", "hero_range_narrowness",
    "hero_weighted_range_narrowness", "villain_strength_vs_fixed_range",
    "villain_strength_vs_scenario_range", "scenario_strength_delta",
    "range_advantage_score", "nut_advantage_score", "board_favors_pfr",
    "board_favors_caller", "is_dynamic_board", "is_static_board",
    "board_four_to_straight", "board_four_to_flush", "board_made_straight",
    "board_made_flush", "is_facing_all_in", "is_stack_committing_size",
    "effective_fold_equity_score", "stack_pressure_score", "pot_pressure_score", "value_bet_incentive",
    "thin_value_incentive", "protection_bet_incentive", "semi_bluff_incentive",
    "sdv_bluff_raise_candidate", "air_bluff_candidate", "bluff_candidate_score",
    "showdown_value_score", "villain_range_leverage_score", "villain_nut_leverage_score",
    "rank_blocker_score", "hero_capped_previous_line_score",
    "range_leverage_bluff_raise_score", "bluff_raise_suppression_score",
    "value_raise_candidate_score", "is_bluff_raise_candidate", "is_value_raise_candidate",
    "is_ace_high_bluffcatcher", "theory_checkback_pressure", "is_nut_hand",
    "hand_improves_board_made_hand", "private_card_nut_advantage",
    "board_lockdown_value_spot",
    "v6_prior_top_prob", "v6_prior_top_margin", "v6_prior_entropy",
]


CATEGORICAL_FEATURES_V7 = [
    "villain_type", "street", "scenario_id", "hand_subgroup",
    "hand_equity_bucket", "current_strength_bucket", "spr_bucket",
    "pot_size_bucket", "facing_size_bucket", "facing_size_pct_stack_bucket",
    "previous_action_summary", "current_aggressor",
    "previous_street_villain_last_action", "hero_prev_street_last_action_type",
    "board_high_card_bucket", "board_type_compact", "open_action_type",
    "vx_node", "vx_street", "vx_scenario", "vx_hand_subgroup",
    "vx_current_strength_bucket", "vx_hand_equity_bucket", "vx_spr_bucket",
    "vx_board_type", "vx_previous_action_summary", "vx_current_aggressor",
    "vx_open_action_type", "sx_node", "sx_street", "sx_hand_subgroup",
    "vsx_node", "vsx_street", "hero_range_source", "range_advantage_bucket",
    "preflop_range_advantage_actor", "nut_advantage_bucket", "nut_advantage_actor",
    "pfr_actor", "board_static_dynamic", "board_texture_key",
    "bluff_candidate_bucket", "theory_checkback_pressure_bucket",
    "river_bluff_role", "river_bluff_role_bucket", "strategic_tier",
    "vx_range_advantage_bucket", "vx_nut_advantage_bucket",
    "vx_theory_checkback_pressure", "vx_board_static_dynamic",
    "vx_bluff_candidate_bucket", "vx_river_bluff_role",
    "vx_range_leverage_bluff_bucket", "vx_stack_commitment_bluff_pressure",
    "vx_strategic_tier_range_pressure", "vx_is_facing_all_in",
    "vx_stack_committing_size", "hand_bucket_x_is_facing_all_in",
    "vx_hand_bucket_all_in", "vx_all_in_street", "vx_all_in_node",
    "vx_all_in_hand_subgroup", "vx_all_in_equity_bucket",
    "vx_all_in_draw_or_sdv", "vx_stack_commitment_equity",
    "vx_stack_commitment_subgroup", "vx_stack_pressure_bucket",
    "vx_value_strength", "vx_scenario_range_advantage",
    "street_range_advantage", "street_theory_checkback", "aggressor_board_made",
    "previous_range_pressure", "vx_range_strength", "vx_theory_strength",
    "vx_stack_strength", "street_stack_pressure", "node_stack_pressure",
    "node_range_advantage", "node_bluff_candidate", "node_river_bluff_role",
    "node_stack_bluff_suppression", "vx_stack_bluff_role", "vx_leverage_action_spot",
    "v6_prior_top_action",
    "vx_v6_prior_top_action", "street_v6_prior_top_action",
]


def feature_columns_for_action_v7(node: str) -> list[str]:
    action_prior_cols = [f"v6_prior_p_{action}" for action in ACTIONS_BY_NODE_V7.get(str(node), [])]
    return list(CATEGORICAL_FEATURES_V7) + list(NUMERIC_FEATURES_V7) + action_prior_cols


def categorical_columns_for_action_v7(node: str) -> list[str]:
    return list(CATEGORICAL_FEATURES_V7)
