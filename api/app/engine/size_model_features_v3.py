from __future__ import annotations

from typing import Any

from api.app.engine.size_model_features import build_size_feature_dict, categorical_columns_for_size_model, feature_columns_for_size_model
from api.app.engine.size_model_features_v2 import build_size_feature_dict_v2, categorical_columns_for_size_model_v2, feature_columns_for_size_model_v2

SIZE_MODEL_KINDS_V3 = ["open_bet", "raise_vs_bet", "reraise_vs_raise"]


def build_size_feature_dict_v3(raw_features: dict[str, object], model_kind: str) -> dict[str, object]:
    if model_kind not in SIZE_MODEL_KINDS_V3:
        raise ValueError(f"Unknown size model kind: {model_kind}")
    out = build_size_feature_dict_v2(raw_features, model_kind)
    villain = str(out.get("villain_type") or "NA")
    scenario = str(out.get("scenario_id") or "NA")
    street = str(out.get("street") or "NA")
    subgroup = str(out.get("hand_subgroup") or "NA")
    current_aggressor = str(out.get("current_aggressor") or "NA")
    previous_summary = str(out.get("previous_action_summary") or "NA")
    equity_bucket = str(out.get("hand_equity_bucket") or "NA")
    current_strength_bucket = str(out.get("current_strength_bucket") or "NA")
    spr_bucket = str(out.get("spr_bucket") or "NA")
    board_type = str(out.get("board_type_compact") or "NA")
    facing_size_bucket = str(out.get("facing_size_bucket") or "NA")
    open_action_type = str(out.get("open_action_type") or "NA")
    previous_villain_action = str(out.get("previous_street_villain_last_action") or "NA")
    hero_prev_action = str(out.get("hero_prev_street_last_action_type") or "NA")
    board_high = str(out.get("board_high_card_bucket") or "NA")

    out.update(
        {
            "vx_current_aggressor": f"{villain}__{current_aggressor}",
            "vx_previous_villain_action": f"{villain}__{previous_villain_action}",
            "vx_hero_prev_action": f"{villain}__{hero_prev_action}",
            "vx_board_high_card_bucket": f"{villain}__{board_high}",
            "vx_pot_size_bucket": f"{villain}__{out.get('pot_size_bucket')}",
            "vx_strength_spr": f"{villain}__{current_strength_bucket}__{spr_bucket}",
            "vx_equity_spr": f"{villain}__{equity_bucket}__{spr_bucket}",
            "vx_subgroup_board": f"{villain}__{subgroup}__{board_type}",
            "vx_street_subgroup": f"{villain}__{street}__{subgroup}",
            "vx_scenario_street": f"{villain}__{scenario}__{street}",
            "vx_scenario_subgroup": f"{villain}__{scenario}__{subgroup}",
            "sx_subgroup": f"{scenario}__{subgroup}",
            "sx_board_type": f"{scenario}__{board_type}",
            "sx_strength": f"{scenario}__{current_strength_bucket}",
            "street_subgroup": f"{street}__{subgroup}",
            "street_board_type": f"{street}__{board_type}",
            "aggressor_previous": f"{current_aggressor}__{previous_summary}",
            "strength_board": f"{current_strength_bucket}__{board_type}",
        }
    )
    if model_kind == "open_bet":
        out["vx_open_action_strength"] = f"{villain}__{open_action_type}__{current_strength_bucket}"
    else:
        out["vx_facing_size_strength"] = f"{villain}__{facing_size_bucket}__{current_strength_bucket}"
        out["vx_facing_size_subgroup"] = f"{villain}__{facing_size_bucket}__{subgroup}"
    return out


def feature_columns_for_size_model_v3(model_kind: str) -> list[str]:
    common_extra = [
        "vx_current_aggressor",
        "vx_previous_villain_action",
        "vx_hero_prev_action",
        "vx_board_high_card_bucket",
        "vx_pot_size_bucket",
        "vx_strength_spr",
        "vx_equity_spr",
        "vx_subgroup_board",
        "vx_street_subgroup",
        "vx_scenario_street",
        "vx_scenario_subgroup",
        "sx_subgroup",
        "sx_board_type",
        "sx_strength",
        "street_subgroup",
        "street_board_type",
        "aggressor_previous",
        "strength_board",
    ]
    base = feature_columns_for_size_model_v2(model_kind)
    if model_kind == "open_bet":
        return base + common_extra + ["vx_open_action_strength"]
    if model_kind in {"raise_vs_bet", "reraise_vs_raise"}:
        return base + common_extra + ["vx_facing_size_strength", "vx_facing_size_subgroup"]
    raise ValueError(f"Unknown size model kind: {model_kind}")


def categorical_columns_for_size_model_v3(model_kind: str) -> list[str]:
    common_extra = [
        "vx_current_aggressor",
        "vx_previous_villain_action",
        "vx_hero_prev_action",
        "vx_board_high_card_bucket",
        "vx_pot_size_bucket",
        "vx_strength_spr",
        "vx_equity_spr",
        "vx_subgroup_board",
        "vx_street_subgroup",
        "vx_scenario_street",
        "vx_scenario_subgroup",
        "sx_subgroup",
        "sx_board_type",
        "sx_strength",
        "street_subgroup",
        "street_board_type",
        "aggressor_previous",
        "strength_board",
    ]
    base = categorical_columns_for_size_model_v2(model_kind)
    if model_kind == "open_bet":
        return base + common_extra + ["vx_open_action_strength"]
    if model_kind in {"raise_vs_bet", "reraise_vs_raise"}:
        return base + common_extra + ["vx_facing_size_strength", "vx_facing_size_subgroup"]
    raise ValueError(f"Unknown size model kind: {model_kind}")


def build_size_feature_dict_by_space(raw_features: dict[str, object], model_kind: str, feature_space: str) -> dict[str, object]:
    if feature_space == "compact_v1":
        return build_size_feature_dict(raw_features, model_kind)
    if feature_space == "context_v2":
        return build_size_feature_dict_v2(raw_features, model_kind)
    if feature_space == "villain_context_v3":
        return build_size_feature_dict_v3(raw_features, model_kind)
    raise ValueError(f"Unknown v3 size feature space: {feature_space}")


def feature_columns_by_space(model_kind: str, feature_space: str) -> list[str]:
    if feature_space == "compact_v1":
        return feature_columns_for_size_model(model_kind)
    if feature_space == "context_v2":
        return feature_columns_for_size_model_v2(model_kind)
    if feature_space == "villain_context_v3":
        return feature_columns_for_size_model_v3(model_kind)
    raise ValueError(f"Unknown v3 size feature space: {feature_space}")


def categorical_columns_by_space(model_kind: str, feature_space: str) -> list[str]:
    if feature_space == "compact_v1":
        return categorical_columns_for_size_model(model_kind)
    if feature_space == "context_v2":
        return categorical_columns_for_size_model_v2(model_kind)
    if feature_space == "villain_context_v3":
        return categorical_columns_for_size_model_v3(model_kind)
    raise ValueError(f"Unknown v3 size feature space: {feature_space}")
