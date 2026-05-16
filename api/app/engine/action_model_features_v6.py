from __future__ import annotations

from math import log2
from typing import Any

MODEL_ORDER_V6 = ["v1", "v2", "v3", "v4", "v5"]
ACTIONS_BY_NODE_V6 = {
    "open_action": ["x", "b"],
    "facing_bet": ["f", "c", "r"],
    "facing_raise": ["f", "c", "r"],
}


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
    return _bucket(
        float(value),
        [0.15, 0.30, 0.45, 0.60, 0.75, 0.90],
        ["eq_00_15", "eq_15_30", "eq_30_45", "eq_45_60", "eq_60_75", "eq_75_90", "eq_90_100"],
    )


def _spr_bucket(value: float) -> str:
    return _bucket(float(value), [2.0, 4.0, 8.0], ["spr_lt_2", "spr_2_4", "spr_4_8", "spr_ge_8"])


def _size_bucket(value: float) -> str:
    return _bucket(float(value), [0.34, 0.67, 1.01, 1.51], ["tiny", "small", "medium", "large", "overbet"])


def _pot_bucket(value: float) -> str:
    return _bucket(float(value), [10.0, 25.0, 60.0, 120.0], ["pot_lt_10", "pot_10_25", "pot_25_60", "pot_60_120", "pot_ge_120"])


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


def _normalize_probs(probs: dict[str, float], actions: list[str]) -> dict[str, float]:
    cleaned = {action: max(0.0, float(probs.get(action, 0.0))) for action in actions}
    total = sum(cleaned.values())
    if total <= 0.0:
        return {action: 1.0 / len(actions) for action in actions}
    return {action: value / total for action, value in cleaned.items()}


def _entropy(probs: dict[str, float]) -> float:
    n = max(1, len(probs))
    denom = log2(n)
    if denom <= 0:
        return 0.0
    return float(-sum(p * log2(p) for p in probs.values() if p > 0.0) / denom)


def _top_margin(probs: dict[str, float]) -> float:
    values = sorted(probs.values(), reverse=True)
    if len(values) < 2:
        return float(values[0]) if values else 0.0
    return float(values[0] - values[1])


def _version_probs_from_row(row: dict[str, object], version: str, actions: list[str]) -> dict[str, float]:
    return _normalize_probs(
        {action: _float(row.get(f"p_{action}_{version}")) for action in actions},
        actions,
    )


def _version_probs_from_runtime(version_probs: dict[str, dict[str, float]], version: str, actions: list[str]) -> dict[str, float]:
    return _normalize_probs(version_probs.get(version, {}), actions)


def _build_common_context(raw: dict[str, object], node: str) -> dict[str, object]:
    villain = str(raw.get("villain_type") or "NA")
    street = str(raw.get("street") or "NA")
    scenario = str(raw.get("scenario_id") or "NA")
    hand_subgroup = str(raw.get("hand_subgroup") or "NA")
    current_aggressor = str(raw.get("current_aggressor") or "NA")
    previous_action_summary = str(raw.get("previous_action_summary") or "NA")
    open_action_type = str(raw.get("open_action_type") or "NA")
    hand_equity = _float(raw.get("hand_equity"))
    current_strength = _float(raw.get("current_strength"))
    spr = _float(raw.get("spr"))
    facing_size_pct_pot = _float(raw.get("facing_size_pct_pot"))
    pot_size = _float(raw.get("pot_size"))
    board_type = _board_type(raw)
    hand_equity_bucket = _equity_bucket(hand_equity)
    current_strength_bucket = _equity_bucket(current_strength)
    spr_bucket = _spr_bucket(spr)
    facing_size_bucket = _size_bucket(facing_size_pct_pot)
    pot_bucket = _pot_bucket(pot_size)

    return {
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
        "pot_size": pot_size,
        "pot_size_bucket": pot_bucket,
        "effective_stack_size": _float(raw.get("effective_stack_size")),
        "villain_is_ip": _bool_to_int(raw.get("villain_is_ip")),
        "facing_size_raw": _float(raw.get("facing_size_raw")),
        "facing_size_pct_pot": facing_size_pct_pot,
        "facing_size_pct_stack": _float(raw.get("facing_size_pct_stack")),
        "facing_size_bucket": facing_size_bucket,
        "previous_action_summary": previous_action_summary,
        "current_aggressor": current_aggressor,
        "previous_street_villain_last_action": str(raw.get("previous_street_villain_last_action") or "NA"),
        "hero_prev_street_last_action_type": str(raw.get("hero_prev_street_last_action_type") or "NA"),
        "hero_prev_street_last_aggressive_size_pct_pot": _float(raw.get("hero_prev_street_last_aggressive_size_pct_pot")),
        "hero_prev_street_total_investment_pct_pot": _float(raw.get("hero_prev_street_total_investment_pct_pot")),
        "hero_prev_street_called_raise": _bool_to_int(raw.get("hero_prev_street_called_raise")),
        "previous_street_ended_aggressive": _bool_to_int(raw.get("previous_street_ended_aggressive")),
        "opponent_perceived_strength": _float(raw.get("opponent_perceived_strength")),
        "board_high_card_bucket": str(raw.get("board_high_card_bucket") or "NA"),
        "board_type_compact": board_type,
        "board_paired": _bool_to_int(raw.get("board_paired")),
        "board_rainbow": _bool_to_int(raw.get("board_rainbow")),
        "board_monotone": _bool_to_int(raw.get("board_monotone")),
        "board_two_tone": _bool_to_int(raw.get("board_two_tone")),
        "board_flush_completed": _bool_to_int(raw.get("board_flush_completed")),
        "board_straight_completed": _bool_to_int(raw.get("board_straight_completed")),
        "board_connected": _bool_to_int(raw.get("board_connected")),
        "vulnerability_score": _float(raw.get("vulnerability_score")),
        "open_action_type": open_action_type,
        "vx_node": f"{villain}__{node}",
        "vx_street": f"{villain}__{street}",
        "vx_scenario": f"{villain}__{scenario}",
        "vx_hand_subgroup": f"{villain}__{hand_subgroup}",
        "vx_current_strength_bucket": f"{villain}__{current_strength_bucket}",
        "vx_hand_equity_bucket": f"{villain}__{hand_equity_bucket}",
        "vx_spr_bucket": f"{villain}__{spr_bucket}",
        "vx_board_type": f"{villain}__{board_type}",
        "vx_previous_action_summary": f"{villain}__{previous_action_summary}",
        "vx_current_aggressor": f"{villain}__{current_aggressor}",
        "vx_open_action_type": f"{villain}__{open_action_type}",
        "sx_node": f"{scenario}__{node}",
        "sx_street": f"{scenario}__{street}",
        "sx_hand_subgroup": f"{scenario}__{hand_subgroup}",
        "vsx_node": f"{villain}__{scenario}__{node}",
        "vsx_street": f"{villain}__{scenario}__{street}",
    }


def build_action_meta_features_v6(
    *,
    node: str,
    raw_context: dict[str, object],
    version_probs: dict[str, dict[str, float]],
) -> dict[str, object]:
    actions = ACTIONS_BY_NODE_V6[str(node)]
    out = _build_common_context(raw_context, str(node))
    normalized_by_version = {
        version: _version_probs_from_runtime(version_probs, version, actions)
        for version in MODEL_ORDER_V6
    }

    for version, probs in normalized_by_version.items():
        for action in actions:
            out[f"{version}_p_{action}"] = float(probs[action])
        out[f"{version}_top_action"] = max(probs, key=probs.get)
        out[f"{version}_top_prob"] = max(probs.values())
        out[f"{version}_top_margin"] = _top_margin(probs)
        out[f"{version}_entropy"] = _entropy(probs)

    for action in actions:
        values = [normalized_by_version[version][action] for version in MODEL_ORDER_V6]
        out[f"expert_mean_p_{action}"] = float(sum(values) / len(values))
        out[f"expert_max_p_{action}"] = float(max(values))
        out[f"expert_min_p_{action}"] = float(min(values))
        out[f"expert_spread_p_{action}"] = float(max(values) - min(values))

    top_actions = [out[f"{version}_top_action"] for version in MODEL_ORDER_V6]
    out["expert_top_consensus_count"] = max(top_actions.count(action) for action in actions)
    out["expert_top_consensus_action"] = max(actions, key=top_actions.count)
    out["expert_mean_entropy"] = float(sum(_entropy(normalized_by_version[v]) for v in MODEL_ORDER_V6) / len(MODEL_ORDER_V6))
    out["expert_mean_top_margin"] = float(sum(_top_margin(normalized_by_version[v]) for v in MODEL_ORDER_V6) / len(MODEL_ORDER_V6))
    return out


def build_action_meta_features_v6_from_training_row(
    row: dict[str, object],
    *,
    include_v5: bool = True,
) -> dict[str, object]:
    node = str(row["node"])
    actions = ACTIONS_BY_NODE_V6[node]
    versions = MODEL_ORDER_V6 if include_v5 else MODEL_ORDER_V6[:-1]
    version_probs = {
        version: _version_probs_from_row(row, version, actions)
        for version in versions
    }
    if not include_v5:
        version_probs["v5"] = {
            action: sum(version_probs[v][action] for v in versions) / len(versions)
            for action in actions
        }
    return build_action_meta_features_v6(
        node=node,
        raw_context=row,
        version_probs=version_probs,
    )


def feature_columns_for_action_v6(node: str) -> list[str]:
    actions = ACTIONS_BY_NODE_V6[str(node)]
    common = [
        "villain_type", "street", "scenario_id", "hand_subgroup",
        "hand_equity", "current_strength", "hand_equity_bucket", "current_strength_bucket",
        "spr", "spr_bucket", "pot_size", "pot_size_bucket", "effective_stack_size",
        "villain_is_ip", "facing_size_raw", "facing_size_pct_pot", "facing_size_pct_stack",
        "facing_size_bucket", "previous_action_summary", "current_aggressor",
        "previous_street_villain_last_action", "hero_prev_street_last_action_type",
        "hero_prev_street_last_aggressive_size_pct_pot", "hero_prev_street_total_investment_pct_pot",
        "hero_prev_street_called_raise", "previous_street_ended_aggressive",
        "opponent_perceived_strength", "board_high_card_bucket", "board_type_compact",
        "board_paired", "board_rainbow", "board_monotone", "board_two_tone",
        "board_flush_completed", "board_straight_completed", "board_connected",
        "vulnerability_score", "open_action_type",
        "vx_node", "vx_street", "vx_scenario", "vx_hand_subgroup",
        "vx_current_strength_bucket", "vx_hand_equity_bucket", "vx_spr_bucket",
        "vx_board_type", "vx_previous_action_summary", "vx_current_aggressor",
        "vx_open_action_type", "sx_node", "sx_street", "sx_hand_subgroup",
        "vsx_node", "vsx_street",
        "expert_top_consensus_count", "expert_top_consensus_action",
        "expert_mean_entropy", "expert_mean_top_margin",
    ]
    expert_cols: list[str] = []
    for version in MODEL_ORDER_V6:
        expert_cols.extend([f"{version}_top_action", f"{version}_top_prob", f"{version}_top_margin", f"{version}_entropy"])
        expert_cols.extend([f"{version}_p_{action}" for action in actions])
    for action in actions:
        expert_cols.extend([
            f"expert_mean_p_{action}",
            f"expert_max_p_{action}",
            f"expert_min_p_{action}",
            f"expert_spread_p_{action}",
        ])
    return common + expert_cols


def categorical_columns_for_action_v6(node: str) -> list[str]:
    common = [
        "villain_type", "street", "scenario_id", "hand_subgroup",
        "hand_equity_bucket", "current_strength_bucket", "spr_bucket",
        "pot_size_bucket", "facing_size_bucket", "previous_action_summary",
        "current_aggressor", "previous_street_villain_last_action",
        "hero_prev_street_last_action_type", "board_high_card_bucket",
        "board_type_compact", "open_action_type", "vx_node", "vx_street",
        "vx_scenario", "vx_hand_subgroup", "vx_current_strength_bucket",
        "vx_hand_equity_bucket", "vx_spr_bucket", "vx_board_type",
        "vx_previous_action_summary", "vx_current_aggressor",
        "vx_open_action_type", "sx_node", "sx_street", "sx_hand_subgroup",
        "vsx_node", "vsx_street", "expert_top_consensus_action",
    ]
    return common + [f"{version}_top_action" for version in MODEL_ORDER_V6]
