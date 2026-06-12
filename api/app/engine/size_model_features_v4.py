from __future__ import annotations

from typing import Any

from api.app.engine.semantic_features_v7 import build_semantic_features_v7
from api.app.engine.size_model_features_v3 import (
    build_size_feature_dict_by_space,
    categorical_columns_by_space,
    feature_columns_by_space,
)

SIZE_MODEL_KINDS_V4 = ["open_bet", "raise_vs_bet", "reraise_vs_raise"]


SEMANTIC_SIZE_NUMERIC = [
    "hero_scenario_weight", "hero_fixed_weight", "hero_range_narrowness",
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
]

SEMANTIC_SIZE_CATEGORICAL = [
    "hero_range_source", "range_advantage_bucket", "preflop_range_advantage_actor",
    "nut_advantage_bucket", "nut_advantage_actor", "pfr_actor",
    "board_static_dynamic", "board_texture_key", "facing_size_pct_stack_bucket",
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
    "street_range_advantage", "street_theory_checkback",
    "aggressor_board_made", "previous_range_pressure",
]

OPEN_SIZE_NUMERIC = [
    "open_range_x_strength",
    "open_range_x_equity",
    "open_range_x_vulnerability",
    "open_vulnerability_x_strength",
    "open_dynamic_x_vulnerability",
    "open_theory_x_strength",
    "open_nut_x_strength",
]

FACING_SIZE_NUMERIC = [
    "facing_stack_pressure_x_strength",
    "facing_stack_pressure_x_equity",
    "facing_stack_pressure_x_vulnerability",
    "facing_stack_pressure_x_spr",
    "facing_pot_pressure_x_stack_pressure",
    "facing_commitment_x_strength",
    "facing_commitment_x_vulnerability",
    "facing_allin_x_strength",
    "facing_range_leverage_x_fold_equity",
    "facing_bluff_suppression_x_strength",
    "facing_value_raise_x_stack",
    "effective_stack_bucket_value",
    "stack_to_pot_ratio",
    "remaining_stack_after_facing",
    "remaining_stack_pct",
]

PRIOR_SIZE_NUMERIC = [
    "v3_size_prior_target",
    "v3_size_prior_x_strength",
    "v3_size_prior_x_equity",
    "v3_size_prior_x_range",
    "v3_size_prior_x_stack_pressure",
]

COMMON_SIZE_CATEGORICAL = [
    "vx_size_range_subgroup",
    "vx_size_theory_street",
    "vx_size_bluff_stack",
    "sx_size_range",
    "street_size_stack",
    "effective_stack_bucket",
    "stack_to_pot_bucket",
    "vx_scenario_range",
    "vx_scenario_board",
    "vx_scenario_street",
    "vx_board_vulnerability",
    "vx_range_vulnerability",
    "vx_size_river_bluff_role",
    "vx_size_leverage_range",
    "street_size_bluff_role",
    "vx_strength_range",
    "vx_strength_board",
    "vx_equity_range",
    "vx_nut_strength",
    "scenario_board_texture",
    "scenario_range_board",
    "street_range_board",
]

PRIOR_SIZE_CATEGORICAL = [
    "v3_size_prior_bucket",
    "v3_size_prior_model_kind",
    "vx_v3_size_prior_bucket",
    "street_v3_size_prior_bucket",
    "board_v3_size_prior_bucket",
]

OPEN_SIZE_CATEGORICAL = [
    "open_vx_scenario_range",
    "open_vx_scenario_board",
    "open_vx_range_vulnerability",
    "open_vx_board_vulnerability",
    "open_vx_theory_strength",
    "open_vx_range_board_strength",
]

FACING_SIZE_CATEGORICAL = [
    "facing_vx_stack_pressure",
    "facing_vx_spr_stack",
    "facing_vx_effective_stack",
    "facing_vx_commit_strength",
    "facing_vx_size_stack",
    "facing_vx_size_spr",
    "facing_vx_allin_strength",
    "facing_vx_stack_bluff_role",
    "facing_vx_leverage_commitment",
    "facing_vx_vulnerability_stack",
    "facing_vx_board_stack",
    "facing_vx_range_stack",
]


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bucket(value: float, cuts: list[float], labels: list[str]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def build_size_feature_dict_v4(raw_features: dict[str, object], model_kind: str, spot: Any) -> dict[str, object]:
    if model_kind not in SIZE_MODEL_KINDS_V4:
        raise ValueError(f"Unknown size model kind: {model_kind}")
    out = build_size_feature_dict_by_space(raw_features, model_kind, "villain_context_v3")
    semantic = build_semantic_features_v7(spot, raw_features)
    out.update({key: semantic.get(key) for key in SEMANTIC_SIZE_NUMERIC + SEMANTIC_SIZE_CATEGORICAL})
    villain = str(out.get("villain_type") or "NA")
    scenario = str(out.get("scenario_id") or "NA")
    street = str(out.get("street") or "NA")
    subgroup = str(out.get("hand_subgroup") or "NA")
    range_bucket = str(out.get("range_advantage_bucket") or "neutral")
    theory_bucket = str(out.get("theory_checkback_pressure_bucket") or "none")
    bluff_bucket = str(out.get("bluff_candidate_bucket") or "none")
    stack_bucket = str(out.get("facing_size_pct_stack_bucket") or "lt_20")
    vulnerability_bucket = str(out.get("vulnerability_bucket") or "NA")
    strength_bucket = str(out.get("current_strength_bucket") or "NA")
    equity_bucket = str(out.get("hand_equity_bucket") or "NA")
    board_type = str(out.get("board_type_compact") or "NA")
    board_texture = str(out.get("board_static_dynamic") or "NA")
    nut_bucket = str(out.get("nut_advantage_bucket") or "neutral")
    effective_stack = _float(out.get("effective_stack_size"))
    pot_size = _float(out.get("pot_size"))
    facing_raw = _float(out.get("facing_size_raw"))
    current_strength = _float(out.get("current_strength"))
    hand_equity = _float(out.get("hand_equity"))
    vulnerability = _float(out.get("vulnerability_score"))
    range_score = _float(out.get("range_advantage_score"))
    nut_score = _float(out.get("nut_advantage_score"))
    stack_pressure = _float(out.get("stack_pressure_score"))
    pot_pressure = _float(out.get("pot_pressure_score"))
    spr = _float(out.get("spr"))
    theory_pressure = _float(out.get("theory_checkback_pressure"))
    is_dynamic = _float(out.get("is_dynamic_board"))
    is_committing = _float(out.get("is_stack_committing_size"))
    is_all_in = _float(out.get("is_facing_all_in"))
    effective_fold_equity = _float(out.get("effective_fold_equity_score"))
    range_leverage_bluff = _float(out.get("range_leverage_bluff_raise_score"))
    bluff_suppression = _float(out.get("bluff_raise_suppression_score"))
    value_raise = _float(out.get("value_raise_candidate_score"))
    river_bluff_role = str(out.get("river_bluff_role") or "NA")
    v3_prior = _float(raw_features.get("v3_size_prior_target"))
    v3_prior_bucket = str(raw_features.get("v3_size_prior_bucket") or "NA")
    v3_prior_model_kind = str(raw_features.get("v3_size_prior_model_kind") or model_kind)
    stack_to_pot = effective_stack / pot_size if pot_size > 0.0 else 0.0
    remaining_stack = max(0.0, effective_stack - facing_raw)
    remaining_pct = remaining_stack / effective_stack if effective_stack > 0.0 else 0.0
    effective_stack_bucket = _bucket(effective_stack, [60.0, 120.0, 220.0, 400.0], ["eff_lt_60", "eff_60_120", "eff_120_220", "eff_220_400", "eff_ge_400"])
    stack_to_pot_bucket = _bucket(stack_to_pot, [1.5, 3.0, 6.0, 12.0], ["stp_lt_1_5", "stp_1_5_3", "stp_3_6", "stp_6_12", "stp_ge_12"])
    out.update(
        {
            "vx_size_range_subgroup": f"{villain}__{range_bucket}__{subgroup}",
            "vx_size_theory_street": f"{villain}__{street}__{theory_bucket}",
            "vx_size_bluff_stack": f"{villain}__{bluff_bucket}__{stack_bucket}",
            "sx_size_range": f"{scenario}__{range_bucket}",
            "street_size_stack": f"{street}__{stack_bucket}",
            "effective_stack_bucket": effective_stack_bucket,
            "stack_to_pot_bucket": stack_to_pot_bucket,
            "effective_stack_bucket_value": {
                "eff_lt_60": 0,
                "eff_60_120": 1,
                "eff_120_220": 2,
                "eff_220_400": 3,
                "eff_ge_400": 4,
            }[effective_stack_bucket],
            "stack_to_pot_ratio": stack_to_pot,
            "remaining_stack_after_facing": remaining_stack,
            "remaining_stack_pct": remaining_pct,
            "vx_scenario_range": f"{villain}__{scenario}__{range_bucket}",
            "vx_scenario_board": f"{villain}__{scenario}__{board_type}",
            "vx_scenario_street": f"{villain}__{scenario}__{street}",
            "vx_board_vulnerability": f"{villain}__{board_type}__{vulnerability_bucket}",
            "vx_range_vulnerability": f"{villain}__{range_bucket}__{vulnerability_bucket}",
            "vx_size_river_bluff_role": f"{villain}__{river_bluff_role}",
            "vx_size_leverage_range": f"{villain}__{_bucket(range_leverage_bluff, [0.15, 0.35, 0.60], ['none', 'low', 'medium', 'high'])}__{range_bucket}",
            "street_size_bluff_role": f"{street}__{river_bluff_role}",
            "vx_strength_range": f"{villain}__{strength_bucket}__{range_bucket}",
            "vx_strength_board": f"{villain}__{strength_bucket}__{board_type}",
            "vx_equity_range": f"{villain}__{equity_bucket}__{range_bucket}",
            "vx_nut_strength": f"{villain}__{nut_bucket}__{strength_bucket}",
            "scenario_board_texture": f"{scenario}__{board_texture}",
            "scenario_range_board": f"{scenario}__{range_bucket}__{board_type}",
            "street_range_board": f"{street}__{range_bucket}__{board_type}",
            "v3_size_prior_target": v3_prior,
            "v3_size_prior_x_strength": v3_prior * current_strength,
            "v3_size_prior_x_equity": v3_prior * hand_equity,
            "v3_size_prior_x_range": v3_prior * range_score,
            "v3_size_prior_x_stack_pressure": v3_prior * stack_pressure,
            "v3_size_prior_bucket": v3_prior_bucket,
            "v3_size_prior_model_kind": v3_prior_model_kind,
            "vx_v3_size_prior_bucket": f"{villain}__{v3_prior_bucket}",
            "street_v3_size_prior_bucket": f"{street}__{v3_prior_bucket}",
            "board_v3_size_prior_bucket": f"{board_type}__{v3_prior_bucket}",
        }
    )
    if model_kind == "open_bet":
        out.update(
            {
                "open_range_x_strength": range_score * current_strength,
                "open_range_x_equity": range_score * hand_equity,
                "open_range_x_vulnerability": range_score * vulnerability,
                "open_vulnerability_x_strength": vulnerability * current_strength,
                "open_dynamic_x_vulnerability": is_dynamic * vulnerability,
                "open_theory_x_strength": theory_pressure * current_strength,
                "open_nut_x_strength": nut_score * current_strength,
                "open_vx_scenario_range": f"{villain}__{scenario}__{range_bucket}",
                "open_vx_scenario_board": f"{villain}__{scenario}__{board_type}",
                "open_vx_range_vulnerability": f"{villain}__{range_bucket}__{vulnerability_bucket}",
                "open_vx_board_vulnerability": f"{villain}__{board_type}__{vulnerability_bucket}",
                "open_vx_theory_strength": f"{villain}__{theory_bucket}__{strength_bucket}",
                "open_vx_range_board_strength": f"{villain}__{range_bucket}__{board_type}__{strength_bucket}",
            }
        )
    else:
        out.update(
            {
                "facing_stack_pressure_x_strength": stack_pressure * current_strength,
                "facing_stack_pressure_x_equity": stack_pressure * hand_equity,
                "facing_stack_pressure_x_vulnerability": stack_pressure * vulnerability,
                "facing_stack_pressure_x_spr": stack_pressure * spr,
                "facing_pot_pressure_x_stack_pressure": pot_pressure * stack_pressure,
                "facing_commitment_x_strength": is_committing * current_strength,
                "facing_commitment_x_vulnerability": is_committing * vulnerability,
                "facing_allin_x_strength": is_all_in * current_strength,
                "facing_range_leverage_x_fold_equity": range_leverage_bluff * effective_fold_equity,
                "facing_bluff_suppression_x_strength": bluff_suppression * current_strength,
                "facing_value_raise_x_stack": value_raise * stack_pressure,
                "facing_vx_stack_pressure": f"{villain}__{stack_bucket}",
                "facing_vx_spr_stack": f"{villain}__{out.get('spr_bucket')}__{stack_bucket}",
                "facing_vx_effective_stack": f"{villain}__{effective_stack_bucket}",
                "facing_vx_commit_strength": f"{villain}__{int(is_committing)}__{strength_bucket}",
                "facing_vx_size_stack": f"{villain}__{out.get('facing_size_bucket')}__{stack_bucket}",
                "facing_vx_size_spr": f"{villain}__{out.get('facing_size_bucket')}__{out.get('spr_bucket')}",
                "facing_vx_allin_strength": f"{villain}__{int(is_all_in)}__{strength_bucket}",
                "facing_vx_stack_bluff_role": f"{villain}__{stack_bucket}__{river_bluff_role}",
                "facing_vx_leverage_commitment": f"{villain}__{_bucket(range_leverage_bluff, [0.15, 0.35, 0.60], ['none', 'low', 'medium', 'high'])}__{int(is_committing)}",
                "facing_vx_vulnerability_stack": f"{villain}__{vulnerability_bucket}__{stack_bucket}",
                "facing_vx_board_stack": f"{villain}__{board_type}__{stack_bucket}",
                "facing_vx_range_stack": f"{villain}__{range_bucket}__{stack_bucket}",
            }
        )
    return out


def feature_columns_for_size_model_v4(model_kind: str) -> list[str]:
    common = (
        feature_columns_by_space(model_kind, "villain_context_v3")
        + list(SEMANTIC_SIZE_NUMERIC)
        + list(SEMANTIC_SIZE_CATEGORICAL)
        + list(COMMON_SIZE_CATEGORICAL)
    )
    if model_kind == "open_bet":
        return _unique(common + list(OPEN_SIZE_NUMERIC) + list(OPEN_SIZE_CATEGORICAL))
    if model_kind == "raise_vs_bet":
        return _unique(common + list(FACING_SIZE_NUMERIC) + list(FACING_SIZE_CATEGORICAL))
    if model_kind == "reraise_vs_raise":
        return _unique(common + list(PRIOR_SIZE_NUMERIC) + list(PRIOR_SIZE_CATEGORICAL) + list(FACING_SIZE_NUMERIC) + list(FACING_SIZE_CATEGORICAL))
    raise ValueError(f"Unknown size model kind: {model_kind}")


def categorical_columns_for_size_model_v4(model_kind: str) -> list[str]:
    common = (
        categorical_columns_by_space(model_kind, "villain_context_v3")
        + list(SEMANTIC_SIZE_CATEGORICAL)
        + list(COMMON_SIZE_CATEGORICAL)
    )
    if model_kind == "open_bet":
        return _unique(common + list(OPEN_SIZE_CATEGORICAL))
    if model_kind == "raise_vs_bet":
        return _unique(common + list(FACING_SIZE_CATEGORICAL))
    if model_kind == "reraise_vs_raise":
        return _unique(common + list(PRIOR_SIZE_CATEGORICAL) + list(FACING_SIZE_CATEGORICAL))
    raise ValueError(f"Unknown size model kind: {model_kind}")
