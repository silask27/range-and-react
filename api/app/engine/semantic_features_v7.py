from __future__ import annotations

from typing import Any

from api.app.data.catalog import get_scenario
from api.app.engine import bucketizer as bz
from api.app.engine.board_texture import evaluate_board_texture
from api.app.engine.cards import normalize_cards
from typing import Any
GeneratedSpot = Any


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _bucket(value: float, cuts: list[float], labels: list[str]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def _signed_bucket(value: float) -> str:
    if value <= -0.18:
        return "villain_large"
    if value <= -0.07:
        return "villain_small"
    if value < 0.07:
        return "neutral"
    if value < 0.18:
        return "hero_small"
    return "hero_large"


def _pressure_bucket(value: float) -> str:
    return _bucket(float(value), [0.08, 0.18, 0.32, 0.55], ["none", "low", "medium", "high", "very_high"])


def _strength_bucket(value: float) -> str:
    return _bucket(float(value), [0.20, 0.40, 0.60, 0.78, 0.90], ["very_weak", "weak", "medium", "strong", "very_strong", "nutted"])


def _stack_bucket(value: float) -> str:
    return _bucket(float(value), [0.20, 0.40, 0.70, 1.00], ["lt_20", "20_40", "40_70", "70_100", "all_in_or_more"])


def _strategic_tier(villain: str) -> str:
    return {
        "Erik": "elite_range_thinker",
        "Blake": "thinking_reg",
        "Alex": "straightforward_reg",
        "Steve": "pressure_aggressor",
        "Tom": "station",
        "Dave": "passive_chaser",
        "Mike": "nit",
    }.get(str(villain), "unknown")


def _has_rank(cards: list[str], rank: str) -> bool:
    return any(str(card[:-1]).upper() == rank for card in cards)


def _rank_blocker_score(hole_cards: list[str], board: list[str]) -> float:
    has_ace = _has_rank(hole_cards, "A")
    has_king = _has_rank(hole_cards, "K")
    board_has_ace = _has_rank(board, "A")
    board_has_king = _has_rank(board, "K")
    score = 0.0
    if has_ace:
        score += 0.45
    if has_king and board_has_king:
        score += 0.30
    if has_ace and not board_has_ace:
        score += 0.15
    return _clamp(score, 0.0, 1.0)


def _previous_hero_capped_score(previous_summary: str) -> float:
    if previous_summary == "NA":
        return 0.0
    score = 0.0
    if "hero_check" in previous_summary:
        score += 0.45
    if "hero_call" in previous_summary:
        score += 0.25
    if "hero_bet" in previous_summary:
        score -= 0.20
    if "hero_raise" in previous_summary:
        score -= 0.45
    if "villain_bet" in previous_summary or "villain_raise" in previous_summary:
        score += 0.20
    return _clamp(score, 0.0, 1.0)


def _scenario_tokens(spot: GeneratedSpot) -> tuple[str, ...]:
    try:
        scenario = get_scenario(spot.scenario_id)
    except Exception:
        return ()
    return tuple(getattr(scenario, "hero_range_tokens", ()) or ())


def _pfr_actor(spot: GeneratedSpot) -> str:
    return "hero" if bool(spot.hero_is_aggressor_preflop) else "villain"


def _actor_from_score(score: float) -> str:
    if score >= 0.07:
        return "hero"
    if score <= -0.07:
        return "villain"
    return "neutral"


def _made_or_value_subgroup(subgroup: str) -> bool:
    return subgroup in {
        "Overpair",
        "Top Pair",
        "Mid Pair",
        "Low Pair",
        "Two Pair",
        "Trips",
        "Set",
        "Straight",
        "Flush",
        "Full House",
        "Quads",
        "Straight Flush",
    }


def _draw_subgroup(subgroup: str) -> bool:
    return "Draw" in subgroup or subgroup in {"Gutshot", "Straight Draw", "Flush Draw", "Combo Draw"}


def _hand_bucket_from_context(raw_features: dict[str, object], subgroup: str, current_strength: float) -> str:
    raw_bucket = str(raw_features.get("hand_bucket") or "").strip()
    if raw_bucket:
        return raw_bucket
    if _draw_subgroup(subgroup):
        return "Draw"
    if subgroup == "High Card" or current_strength < 0.20:
        return "Air"
    if subgroup in {"Mid Pair", "Low Pair"} or current_strength < 0.55:
        return "SDV"
    if current_strength >= 0.82 or subgroup in {"Straight", "Flush", "Full House", "Quads", "Straight Flush"}:
        return "Nutted"
    return "Value"


def _scenario_range_scores(spot: GeneratedSpot) -> dict[str, float | int | str]:
    board = normalize_cards(spot.board)
    hole_cards = normalize_cards(spot.villain_hand)
    hole = tuple(sorted((hole_cards[0], hole_cards[1])))
    hero_mix = bz.selected_hero_range_mix(
        villain_profile_id=spot.villain_type,
        scenario_hero_range_tokens=_scenario_tokens(spot),
    )
    fixed_combos = list(hero_mix.get("fixed_combos") or [])
    scenario_combos = list(hero_mix.get("scenario_combos") or [])
    scenario_weight = _float(hero_mix.get("scenario_weight"))
    fixed_weight = _float(hero_mix.get("fixed_weight"), 1.0)

    fixed_strength = bz.current_score_vs_hero_range_exact(hole, board, fixed_combos) if fixed_combos else 0.0
    scenario_strength = (
        bz.current_score_vs_hero_range_exact(hole, board, scenario_combos)
        if scenario_combos and scenario_weight > 0.0
        else fixed_strength
    )
    fixed_count = max(1, len(fixed_combos))
    scenario_count = len(scenario_combos)
    range_narrowness = 0.0 if scenario_count <= 0 else 1.0 - min(1.0, scenario_count / fixed_count)
    weighted_range_narrowness = scenario_weight * range_narrowness

    # Hero-perspective pressure: positive means villain's exact hand performs worse
    # against the scenario range than the fixed/default range.
    range_advantage_score = scenario_weight * (fixed_strength - scenario_strength)
    nut_advantage_score = weighted_range_narrowness * (0.50 - scenario_strength)

    return {
        "hero_range_source": str(hero_mix.get("source") or "fixed"),
        "hero_scenario_weight": float(scenario_weight),
        "hero_fixed_weight": float(fixed_weight),
        "hero_scenario_combo_count": int(scenario_count),
        "hero_fixed_combo_count": int(fixed_count),
        "hero_range_narrowness": float(range_narrowness),
        "hero_weighted_range_narrowness": float(weighted_range_narrowness),
        "villain_strength_vs_fixed_range": float(fixed_strength),
        "villain_strength_vs_scenario_range": float(scenario_strength),
        "scenario_strength_delta": float(scenario_strength - fixed_strength),
        "range_advantage_score": float(range_advantage_score),
        "range_advantage_bucket": _signed_bucket(range_advantage_score),
        "preflop_range_advantage_actor": _actor_from_score(range_advantage_score),
        "nut_advantage_score": float(nut_advantage_score),
        "nut_advantage_bucket": _signed_bucket(nut_advantage_score),
        "nut_advantage_actor": _actor_from_score(nut_advantage_score),
    }


def _board_made_hand_features(spot: GeneratedSpot) -> dict[str, object]:
    board = normalize_cards(spot.board)
    hole_cards = normalize_cards(spot.villain_hand)
    hole = tuple(sorted((hole_cards[0], hole_cards[1])))
    villain_rank = bz.rank_7(list(hole) + board)
    board_rank = bz.rank_5(tuple(board)) if len(board) == 5 else (0,)
    return {
        "is_nut_hand": int(bz.is_best_possible_hand(hole, board)),
        "hand_improves_board_made_hand": int(len(board) == 5 and villain_rank > board_rank),
        "private_card_nut_advantage": int(bz.is_best_possible_hand(hole, board) and (len(board) < 5 or villain_rank > board_rank)),
    }


def build_semantic_features_v7(spot: GeneratedSpot, raw_features: dict[str, object]) -> dict[str, object]:
    texture = evaluate_board_texture(spot.board)
    board = normalize_cards(spot.board)
    hole_cards = normalize_cards(spot.villain_hand)
    subgroup = str(raw_features.get("hand_subgroup") or "NA")
    current_strength = _float(raw_features.get("current_strength"))
    hand_equity = _float(raw_features.get("hand_equity"))
    vulnerability = _float(raw_features.get("vulnerability_score"))
    facing_stack = _float(raw_features.get("facing_size_pct_stack"))
    facing_pot = _float(raw_features.get("facing_size_pct_pot"))
    street = str(raw_features.get("street") or spot.street)
    villain = str(raw_features.get("villain_type") or spot.villain_type)
    scenario = str(raw_features.get("scenario_id") or spot.scenario_id)
    hand_bucket = _hand_bucket_from_context(raw_features, subgroup, current_strength)
    current_aggressor = str(raw_features.get("current_aggressor") or "NA")
    previous_summary = str(raw_features.get("previous_action_summary") or "NA")
    pfr_actor = _pfr_actor(spot)

    range_scores = _scenario_range_scores(spot)
    range_actor = str(range_scores["preflop_range_advantage_actor"])
    range_score = _float(range_scores["range_advantage_score"])
    scenario_weight = _float(range_scores["hero_scenario_weight"])

    if range_actor == "neutral":
        board_favors_pfr = False
        board_favors_caller = False
    elif range_actor == pfr_actor:
        board_favors_pfr = True
        board_favors_caller = False
    else:
        board_favors_pfr = False
        board_favors_caller = True

    static_dynamic = "dynamic" if texture.dynamic_board else ("static_paired" if texture.static_paired else "static_unpaired")
    made_or_value = _made_or_value_subgroup(subgroup)
    draw = _draw_subgroup(subgroup)
    air = subgroup == "High Card" or str(raw_features.get("hand_bucket") or "") == "Air"
    sdv = subgroup in {"Mid Pair", "Low Pair"} or (0.35 <= current_strength < 0.62 and made_or_value)
    draw_or_sdv = draw or sdv
    river = street == "river"

    value_bet_incentive = _clamp((0.70 * current_strength) + (0.25 * hand_equity) + (0.18 * vulnerability), 0.0, 1.0)
    thin_value_incentive = _clamp((current_strength - 0.48) * 1.8, 0.0, 1.0)
    protection_bet_incentive = _clamp(vulnerability * (0.35 + current_strength), 0.0, 1.0)
    semi_bluff_incentive = _clamp((0.65 * float(draw)) + (0.35 * hand_equity) - (0.18 * current_strength), 0.0, 1.0)
    sdv_bluff_raise_candidate = _clamp(float(sdv) * (0.55 + 0.55 * hand_equity - 0.40 * current_strength), 0.0, 1.0)
    air_bluff_candidate = _clamp(float(air or draw) * (0.70 - current_strength + 0.20 * hand_equity), 0.0, 1.0)
    bluff_candidate_score = _clamp(max(semi_bluff_incentive, sdv_bluff_raise_candidate, air_bluff_candidate), 0.0, 1.0)
    showdown_value_score = _clamp((0.65 * current_strength) + (0.35 * hand_equity), 0.0, 1.0)

    checked_to_ip = spot.node == "open_action" and spot.open_action_type == "checked_to" and bool(spot.villain_is_ip)
    strong_hand = max(current_strength, hand_equity)
    theory_checkback_pressure = 0.0
    if checked_to_ip:
        hero_range_pressure = max(0.0, range_score)
        static_bonus = 0.12 if texture.static_paired or texture.static_unpaired else 0.0
        theory_checkback_pressure = _clamp(
            scenario_weight * (0.55 * hero_range_pressure + 0.25 * strong_hand + static_bonus - 0.18 * vulnerability),
            0.0,
            1.0,
        )

    all_in_facing = int(
        spot.node in {"facing_bet", "facing_raise"}
        and spot.facing_action.amount is not None
        and float(spot.facing_action.amount) >= float(spot.effective_stack_size) - 1e-6
    )
    stack_committing = int(facing_stack >= 0.70)
    all_in_key = "all_in" if all_in_facing else "not_all_in"
    stack_commitment_key = "committed" if stack_committing else "not_committed"
    draw_or_sdv_key = "draw_or_sdv" if draw_or_sdv else "not_draw_or_sdv"
    effective_fold_equity_score = _clamp(1.0 - facing_stack, 0.0, 1.0) if spot.node in {"facing_bet", "facing_raise"} else 1.0

    board_features = _board_made_hand_features(spot)
    villain_range_leverage_score = _clamp(max(0.0, -range_score) * 3.0, 0.0, 1.0)
    villain_nut_leverage_score = _clamp(max(0.0, -_float(range_scores["nut_advantage_score"])) * 3.0, 0.0, 1.0)
    blocker_score = _rank_blocker_score(hole_cards, board)
    hero_capped_score = _previous_hero_capped_score(previous_summary)
    high_card_ace = int(river and air and _has_rank(hole_cards, "A"))
    top_pair_or_better = int(current_strength >= 0.55 and made_or_value)
    value_raise_candidate_score = _clamp(
        float(spot.node in {"facing_bet", "facing_raise"})
        * ((0.75 * current_strength) + (0.20 * hand_equity) + (0.25 * float(board_features["is_nut_hand"]))),
        0.0,
        1.0,
    )
    range_leverage_bluff_raise_score = _clamp(
        float(river and spot.node in {"facing_bet", "facing_raise"})
        * effective_fold_equity_score
        * (
            0.42 * villain_range_leverage_score
            + 0.34 * villain_nut_leverage_score
            + 0.20 * blocker_score
            + 0.18 * hero_capped_score
            + 0.10 * float(sdv or high_card_ace or top_pair_or_better)
        ),
        0.0,
        1.0,
    )
    bluff_raise_suppression_score = _clamp(
        float(spot.node in {"facing_bet", "facing_raise"})
        * facing_stack
        * max(bluff_candidate_score, range_leverage_bluff_raise_score),
        0.0,
        1.5,
    )
    is_bluff_raise_candidate = int(
        spot.node in {"facing_bet", "facing_raise"}
        and not stack_committing
        and max(bluff_candidate_score, range_leverage_bluff_raise_score) >= 0.32
        and current_strength < 0.88
    )
    if not river:
        river_bluff_role = "not_river"
    elif value_raise_candidate_score >= 0.82 and current_strength >= 0.72:
        river_bluff_role = "value"
    elif range_leverage_bluff_raise_score >= 0.38 and blocker_score >= 0.45:
        river_bluff_role = "range_blocker_sdv_bluff"
    elif sdv and range_leverage_bluff_raise_score >= 0.25:
        river_bluff_role = "sdv_bluff"
    elif high_card_ace:
        river_bluff_role = "ace_high_bluffcatch"
    elif air:
        river_bluff_role = "pure_bluff"
    else:
        river_bluff_role = "no_clear_bluff"

    board_lockdown_value_spot = int(
        river
        and bool(texture.straight_completed)
        and bool(board_features["hand_improves_board_made_hand"])
        and current_strength >= 0.70
    )

    out: dict[str, object] = {
        **range_scores,
        **board_features,
        "pfr_actor": pfr_actor,
        "board_favors_pfr": int(board_favors_pfr),
        "board_favors_caller": int(board_favors_caller),
        "board_static_dynamic": static_dynamic,
        "board_texture_key": "_".join(texture.texture_keys()) or static_dynamic,
        "is_dynamic_board": int(texture.dynamic_board),
        "is_static_board": int(texture.static_paired or texture.static_unpaired),
        "board_four_to_straight": int(texture.four_to_straight),
        "board_four_to_flush": int(texture.four_to_flush),
        "board_made_straight": int(texture.straight_completed),
        "board_made_flush": int(texture.flush_completed),
        "facing_size_pct_stack_bucket": _stack_bucket(facing_stack),
        "facing_size_pct_stack": facing_stack,
        "is_facing_all_in": all_in_facing,
        "is_stack_committing_size": stack_committing,
        "effective_fold_equity_score": effective_fold_equity_score,
        "stack_pressure_score": _clamp(facing_stack, 0.0, 1.5),
        "pot_pressure_score": _clamp(facing_pot, 0.0, 3.0),
        "value_bet_incentive": value_bet_incentive,
        "thin_value_incentive": thin_value_incentive,
        "protection_bet_incentive": protection_bet_incentive,
        "semi_bluff_incentive": semi_bluff_incentive,
        "sdv_bluff_raise_candidate": sdv_bluff_raise_candidate,
        "air_bluff_candidate": air_bluff_candidate,
        "bluff_candidate_score": bluff_candidate_score,
        "bluff_candidate_bucket": _pressure_bucket(bluff_candidate_score),
        "showdown_value_score": showdown_value_score,
        "villain_range_leverage_score": villain_range_leverage_score,
        "villain_nut_leverage_score": villain_nut_leverage_score,
        "rank_blocker_score": blocker_score,
        "hero_capped_previous_line_score": hero_capped_score,
        "range_leverage_bluff_raise_score": range_leverage_bluff_raise_score,
        "bluff_raise_suppression_score": bluff_raise_suppression_score,
        "value_raise_candidate_score": value_raise_candidate_score,
        "is_bluff_raise_candidate": is_bluff_raise_candidate,
        "is_value_raise_candidate": int(value_raise_candidate_score >= 0.72),
        "is_ace_high_bluffcatcher": high_card_ace,
        "river_bluff_role": river_bluff_role,
        "river_bluff_role_bucket": river_bluff_role,
        "strategic_tier": _strategic_tier(villain),
        "theory_checkback_pressure": theory_checkback_pressure,
        "theory_checkback_pressure_bucket": _pressure_bucket(theory_checkback_pressure),
        "board_lockdown_value_spot": board_lockdown_value_spot,
        "vx_range_advantage_bucket": f"{villain}__{range_scores['range_advantage_bucket']}",
        "vx_nut_advantage_bucket": f"{villain}__{range_scores['nut_advantage_bucket']}",
        "vx_theory_checkback_pressure": f"{villain}__{_pressure_bucket(theory_checkback_pressure)}",
        "vx_board_static_dynamic": f"{villain}__{static_dynamic}",
        "vx_bluff_candidate_bucket": f"{villain}__{_pressure_bucket(bluff_candidate_score)}",
        "vx_river_bluff_role": f"{villain}__{river_bluff_role}",
        "vx_range_leverage_bluff_bucket": f"{villain}__{_pressure_bucket(range_leverage_bluff_raise_score)}",
        "vx_stack_commitment_bluff_pressure": f"{villain}__{_stack_bucket(facing_stack)}__{_pressure_bucket(bluff_raise_suppression_score)}",
        "vx_strategic_tier_range_pressure": f"{_strategic_tier(villain)}__{range_scores['range_advantage_bucket']}__{range_scores['nut_advantage_bucket']}",
        "vx_is_facing_all_in": f"{villain}__{all_in_key}",
        "vx_stack_committing_size": f"{villain}__{stack_commitment_key}",
        "hand_bucket_x_is_facing_all_in": f"{hand_bucket}__{all_in_key}",
        "vx_hand_bucket_all_in": f"{villain}__{hand_bucket}__{all_in_key}",
        "vx_all_in_street": f"{villain}__{street}__{all_in_key}",
        "vx_all_in_node": f"{villain}__{spot.node}__{all_in_key}",
        "vx_all_in_hand_subgroup": f"{villain}__{subgroup}__{all_in_key}",
        "vx_all_in_equity_bucket": f"{villain}__{_bucket(hand_equity, [0.15, 0.30, 0.45, 0.60, 0.75, 0.90], ['eq_00_15', 'eq_15_30', 'eq_30_45', 'eq_45_60', 'eq_60_75', 'eq_75_90', 'eq_90_100'])}__{all_in_key}",
        "vx_all_in_draw_or_sdv": f"{villain}__{draw_or_sdv_key}__{all_in_key}",
        "vx_stack_commitment_equity": f"{villain}__{_stack_bucket(facing_stack)}__{_bucket(hand_equity, [0.15, 0.30, 0.45, 0.60, 0.75, 0.90], ['eq_00_15', 'eq_15_30', 'eq_30_45', 'eq_45_60', 'eq_60_75', 'eq_75_90', 'eq_90_100'])}",
        "vx_stack_commitment_subgroup": f"{villain}__{_stack_bucket(facing_stack)}__{subgroup}",
        "vx_stack_pressure_bucket": f"{villain}__{_stack_bucket(facing_stack)}",
        "vx_value_strength": f"{villain}__{_strength_bucket(value_bet_incentive)}",
        "vx_scenario_range_advantage": f"{villain}__{scenario}__{range_scores['range_advantage_bucket']}",
        "street_range_advantage": f"{street}__{range_scores['range_advantage_bucket']}",
        "street_theory_checkback": f"{street}__{_pressure_bucket(theory_checkback_pressure)}",
        "aggressor_board_made": f"{current_aggressor}__straight_{int(texture.straight_completed)}__flush_{int(texture.flush_completed)}",
        "previous_range_pressure": f"{previous_summary}__{range_scores['range_advantage_bucket']}",
    }
    return out
