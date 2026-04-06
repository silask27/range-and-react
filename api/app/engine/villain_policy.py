# File: api/app/engine/villain_policy.py
# Summary: Reworked policy helpers that map villain broad families, equity,
# vulnerability, board texture, node type, player-specific thresholds, and guardrails
# into normalized action-size menu weights for the villain decision engine.

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from api.app.engine.board_texture import BoardTextureInfo, evaluate_board_texture
from api.app.engine.villain_hand_bucket import VillainHandBucketResult
from api.app.models.enums import ActionType, Street
from api.app.models.villain_profile import (
    DecisionNode,
    FamilyTendency,
    FacingMenuKey,
    OpenMenuKey,
    StreetProfile,
    SubgroupOverride,
    TextureProfile,
    VillainProfileParams,
)


@dataclass(frozen=True)
class VillainPolicyView:
    """
    Policy-facing interpretation of villain's current exact hidden hand.

    Important design choices:
    - flop / turn use broad family_key:
        draw / sdv / value / nutted_value / air
    - river uses simplified river_family_key:
        air / sdv / value
    - equity is the main within-family strength driver
    - vulnerability matters only on flop / turn
    """

    bucket_label: str
    subgroup_label: str

    family_key: str
    river_family_key: str
    active_family_key: str

    street_key: str
    decision_node: DecisionNode

    equity_vs_hero: float
    draw_strength: float
    value_strength: float
    vulnerability: float

    is_nuts: bool
    is_near_nuts: bool
    is_invulnerable_value: bool

    is_made_hand: bool
    is_pair_plus_draw: bool
    is_strong_draw: bool
    is_weak_draw: bool
    has_nut_flush_draw: bool
    can_make_nutted_draw: bool
    is_missed_draw_river_air: bool

    hero_range_source: str
    uses_scenario_hero_range: bool


@dataclass(frozen=True)
class VillainActionPolicy:
    """
    Final normalized villain policy for the current node.

    open_menu_weights:
        normalized weights for unopened decision menu
        - check
        - bet_small
        - bet_medium
        - bet_big
        - bet_overbet

    facing_menu_weights:
        normalized weights for facing-bet / facing-raise decision menu
        - fold
        - call
        - raise_small
        - raise_normal
        - raise_big

    action_weights:
        compatibility/action summary view collapsed to ActionType buckets
    """

    action_weights: dict[ActionType, float]

    open_menu_weights: dict[str, float]
    facing_menu_weights: dict[str, float]

    bet_size_weights: dict[str, float]
    raise_size_weights: dict[str, float]

    policy_bucket: str
    river_policy_bucket: str
    decision_node: DecisionNode

    facing_bet: bool
    size_frac_of_pot: float
    raw_call_size: float

    texture_keys: list[str]
    debug: dict[str, float | str | bool]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _normalize_weights[T: str | ActionType](weights: dict[T, float]) -> dict[T, float]:
    cleaned = {key: max(0.0, float(weight)) for key, weight in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        if not cleaned:
            return {}
        equal = 1.0 / len(cleaned)
        return {key: equal for key in cleaned}
    return {key: value / total for key, value in cleaned.items()}


def _size_frac_of_pot(to_call: float, pot: float) -> float:
    if pot <= 0:
        return 0.0
    return max(0.0, float(to_call) / float(pot))


def _street_key(street: Street) -> str:
    value = street.value if hasattr(street, "value") else str(street)
    return value.lower()


def _default_street_profile() -> StreetProfile:
    return StreetProfile()


def _default_texture_profile() -> TextureProfile:
    return TextureProfile()


def _effective_subgroup_override(
    params: VillainProfileParams,
    subgroup_label: str,
) -> SubgroupOverride:
    return params.subgroup_overrides.get(subgroup_label, SubgroupOverride())


def _effective_street_profile(
    params: VillainProfileParams,
    street: Street,
) -> StreetProfile:
    return params.street_profiles.get(_street_key(street), _default_street_profile())


def _effective_texture_keys_and_info(
    board: list[str] | tuple[str, ...] | None,
) -> tuple[list[str], BoardTextureInfo | None]:
    if not board:
        return [], None
    texture_info = evaluate_board_texture(board)
    return texture_info.texture_keys(), texture_info


def _effective_texture_profiles(
    params: VillainProfileParams,
    keys: list[str],
) -> list[TextureProfile]:
    return [
        params.texture_profiles.get(key, _default_texture_profile())
        for key in keys
    ]


def _multiply_texture_attr(
    textures: list[TextureProfile],
    attr_name: str,
) -> float:
    product = 1.0
    for texture in textures:
        product *= float(getattr(texture, attr_name))
    return product


def _classify_decision_node(
    *,
    to_call: float,
    pot: float,
    node_hint: DecisionNode | None = None,
) -> DecisionNode:
    """
    Richer node model than the old generic opened/facing-bet split.

    Current heuristic:
    - explicit node_hint wins when provided by the caller
    - otherwise use faced size as a % of pot

    Sizing bands agreed in calibration:
    - small <= 40% pot
    - medium <= 75% pot
    - big <= 125% pot
    - overbet > 125% pot
    """
    if node_hint is not None:
        return node_hint

    if to_call <= 0:
        return "unopened"

    frac = _size_frac_of_pot(to_call, pot)
    if frac <= 0.40:
        return "facing_small_bet"
    if frac <= 0.75:
        return "facing_medium_bet"
    if frac <= 1.25:
        return "facing_big_bet"
    return "facing_overbet"


def policy_view_from_bucket_result(
    result: VillainHandBucketResult,
    *,
    street: Street,
    decision_node: DecisionNode,
) -> VillainPolicyView:
    active_family = result.family_key if street != Street.RIVER else result.river_family_key

    return VillainPolicyView(
        bucket_label=result.bucket_label,
        subgroup_label=result.subgroup_label,
        family_key=result.family_key,
        river_family_key=result.river_family_key,
        active_family_key=active_family,
        street_key=result.street_key,
        decision_node=decision_node,
        equity_vs_hero=result.equity_vs_hero,
        draw_strength=result.draw_strength,
        value_strength=result.value_strength,
        vulnerability=result.vulnerability if street != Street.RIVER else 0.0,
        is_nuts=result.is_nuts,
        is_near_nuts=result.is_near_nuts,
        is_invulnerable_value=result.is_invulnerable_value,
        is_made_hand=result.is_made_hand,
        is_pair_plus_draw=result.is_pair_plus_draw,
        is_strong_draw=result.is_strong_draw,
        is_weak_draw=result.is_weak_draw,
        has_nut_flush_draw=result.has_nut_flush_draw,
        can_make_nutted_draw=result.can_make_nutted_draw,
        is_missed_draw_river_air=result.is_missed_draw_river_air,
        hero_range_source=result.hero_range_source,
        uses_scenario_hero_range=result.uses_scenario_hero_range,
    )


def _node_raise_pressure(decision_node: DecisionNode) -> float:
    if decision_node == "facing_small_bet":
        return 1.12
    if decision_node == "facing_medium_bet":
        return 1.00
    if decision_node == "facing_big_bet":
        return 0.82
    if decision_node == "facing_overbet":
        return 0.58
    if decision_node == "facing_raise":
        return 0.46
    return 1.00


def _node_continue_pressure(decision_node: DecisionNode) -> float:
    if decision_node == "facing_small_bet":
        return 1.08
    if decision_node == "facing_medium_bet":
        return 1.00
    if decision_node == "facing_big_bet":
        return 0.88
    if decision_node == "facing_overbet":
        return 0.74
    if decision_node == "facing_raise":
        return 0.70
    return 1.00


def _node_fold_pressure(decision_node: DecisionNode) -> float:
    if decision_node == "facing_small_bet":
        return 0.86
    if decision_node == "facing_medium_bet":
        return 1.00
    if decision_node == "facing_big_bet":
        return 1.16
    if decision_node == "facing_overbet":
        return 1.34
    if decision_node == "facing_raise":
        return 1.28
    return 1.00


def _family_for_policy(
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
) -> FamilyTendency:
    """
    River simplification:
    - use the simplified river family for policy selection on river
    - use original family on flop / turn
    """
    family_key = policy_view.active_family_key
    return params.family_profiles[family_key]


def _equity_continue_multiplier(
    policy_view: VillainPolicyView,
    family: FamilyTendency,
) -> float:
    eq = _clamp(policy_view.equity_vs_hero, 0.0, 1.0)

    if policy_view.active_family_key == "draw":
        base = 0.76 + policy_view.draw_strength * 0.46
        if policy_view.is_weak_draw:
            base -= 0.08
        return base + eq * family.equity_continue * 0.24

    if policy_view.active_family_key == "sdv":
        return 0.62 + eq * family.equity_continue * 0.34

    if policy_view.active_family_key == "value":
        return 0.74 + policy_view.value_strength * 0.36 + eq * family.equity_continue * 0.16

    if policy_view.active_family_key == "nutted_value":
        return 0.94 + eq * 0.08

    return 0.28 + eq * family.equity_continue * 0.18


def _equity_aggression_multiplier(
    policy_view: VillainPolicyView,
    family: FamilyTendency,
) -> float:
    eq = _clamp(policy_view.equity_vs_hero, 0.0, 1.0)

    if policy_view.active_family_key == "draw":
        base = 0.56 + policy_view.draw_strength * 0.66
        if policy_view.is_pair_plus_draw:
            base -= 0.10
        if policy_view.can_make_nutted_draw:
            base += 0.08
        return base + eq * family.equity_aggression * 0.18

    if policy_view.active_family_key == "sdv":
        return 0.30 + eq * family.equity_aggression * 0.18

    if policy_view.active_family_key == "value":
        base = 0.56 + policy_view.value_strength * 0.54
        if policy_view.vulnerability > 0:
            base += policy_view.vulnerability * family.vulnerability_fastplay * 0.34
        return base + eq * family.equity_aggression * 0.16

    if policy_view.active_family_key == "nutted_value":
        base = 0.88 + policy_view.value_strength * 0.16
        if policy_view.vulnerability > 0:
            base += policy_view.vulnerability * family.vulnerability_fastplay * 0.26
        return base + eq * family.equity_aggression * 0.08

    # air
    return 0.30 + eq * family.equity_aggression * 0.08


def _raw_dollar_continue_multiplier(
    *,
    to_call: float,
    street: Street,
    family_key: str,
    sensitivity: float,
) -> float:
    """
    Models players who react to the actual chip amount, not just the % of pot.

    Calibration intent from the villain notes:
    - strongest on Mike
    - moderate on Alex / Blake
    - fairly small on Dave / Tom
    - minimal on Erik / Steve
    - matters most for river SDV, less for flop/turn strong draws
    """
    sensitivity = _clamp(sensitivity, 0.0, 1.0)
    if sensitivity <= 0:
        return 1.0

    base_units = to_call / 100.0

    family_factor = {
        "draw": 0.60 if street != Street.RIVER else 0.84,
        "sdv": 1.00,
        "value": 0.38,
        "nutted_value": 0.10,
        "air": 1.05,
    }.get(family_key, 0.80)

    penalty = sensitivity * min(0.36, base_units) * family_factor
    return _clamp(1.0 - penalty, 0.58, 1.02)


def _non_pfa_bluff_multiplier(
    params: VillainProfileParams,
    villain_is_pfa: bool | None,
) -> float:
    if villain_is_pfa is None or villain_is_pfa:
        return 1.0
    return _clamp(1.0 - params.non_pfa_bluff_penalty, 0.72, 1.00)


def _current_aggressor_modifiers(
    params: VillainProfileParams,
    villain_is_current_aggressor: bool | None,
) -> tuple[float, float]:
    """
    Returns:
    - bluff multiplier
    - value multiplier

    Current aggressor matters more than preflop aggressor.
    """
    if villain_is_current_aggressor is None:
        return 1.0, 1.0

    if villain_is_current_aggressor:
        bluff_mult = 1.0 + params.current_aggressor_bluff_bonus
        value_mult = 1.0 + params.current_aggressor_value_bonus
        return _clamp(bluff_mult, 0.70, 1.30), _clamp(value_mult, 0.80, 1.30)

    bluff_mult = 1.0 - max(0.0, params.current_aggressor_bluff_bonus) * 0.70
    value_mult = 1.0 - max(0.0, params.current_aggressor_value_bonus) * 0.16
    return _clamp(bluff_mult, 0.72, 1.00), _clamp(value_mult, 0.86, 1.04)


def _river_bluff_threshold_multiplier(
    params: VillainProfileParams,
) -> float:
    """
    Lower bluff_threshold => more willing to bluff with low-equity air.
    """
    threshold = params.river_thresholds.bluff_threshold
    return _clamp(1.05 - 1.40 * threshold, 0.18, 0.96)


def _river_thin_value_multiplier(
    params: VillainProfileParams,
    value_strength: float,
) -> float:
    """
    Lower thin_value_threshold => goes thinner for value.
    """
    thresholds = params.river_thresholds
    thin_threshold = thresholds.thin_value_threshold
    strong_threshold = thresholds.strong_value_threshold

    if value_strength >= strong_threshold:
        return 1.32

    if value_strength >= thin_threshold:
        # above thin threshold -> value bet meaningfully
        return _clamp(0.84 + (value_strength - thin_threshold) * 1.90, 0.84, 1.26)

    # below threshold -> much more check-back pressure
    gap = thin_threshold - value_strength
    return _clamp(0.54 - gap * 0.90, 0.16, 0.54)


def _river_sdv_call_multiplier(
    params: VillainProfileParams,
    equity_vs_hero: float,
) -> float:
    threshold = params.river_thresholds.sdv_call_threshold
    delta = equity_vs_hero - threshold
    if delta >= 0:
        return _clamp(0.92 + delta * 1.60, 0.92, 1.34)
    return _clamp(0.82 + delta * 1.80, 0.18, 0.82)


def _prior_line_modifiers(
    params: VillainProfileParams,
    *,
    prior_villain_aggressive_actions: int,
    prior_hero_aggressive_actions: int,
    street: Street,
) -> tuple[float, float]:
    """
    Returns:
    - villain bluff multiplier from prior line
    - hero aggression penalty to calling / bluffing thresholds

    If history is not supplied yet, the defaults are neutral.
    """
    if street != Street.RIVER:
        return 1.0, 1.0

    bluff_mult = 1.0 + min(0.40, params.river_thresholds.prior_aggression_bluff_bonus * prior_villain_aggressive_actions)
    hero_penalty = 1.0 - min(0.34, params.river_thresholds.prior_hero_aggression_call_penalty * prior_hero_aggressive_actions)
    return _clamp(bluff_mult, 1.0, 1.40), _clamp(hero_penalty, 0.66, 1.0)


def _pair_plus_draw_aggression_discount(
    *,
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
    street: Street,
    decision_node: DecisionNode,
) -> float:
    """
    Pair+draw hands inherit the broad family they bucket into, but they should
    usually raise less than equally strong pure draws because they already have
    showdown value.

    The discount is intentionally villain-sensitive:
    - passive / station profiles discount less because they already raise rarely
    - thinking players discount more because they preserve SDV more carefully
    - maniacs discount less so strong pair+draws still stay active
    """
    if not policy_view.is_pair_plus_draw:
        return 1.0

    family_key = policy_view.active_family_key

    if family_key == "draw":
        discount = 0.80
        if params.passive or params.calling_station:
            discount += 0.10
        if params.thinking_player:
            discount -= 0.16
        if params.aggressive:
            discount -= 0.03
        if params.maniac:
            discount += 0.08
        if street == Street.TURN:
            discount += 0.03
        if decision_node == "facing_raise":
            discount -= 0.08
        elif decision_node in {"facing_big_bet", "facing_overbet"}:
            discount -= 0.04
        return _clamp(discount, 0.52, 0.98)

    if family_key == "sdv":
        discount = 0.92
        if params.thinking_player:
            discount -= 0.10
        if params.maniac:
            discount += 0.04
        if decision_node == "facing_raise":
            discount -= 0.06
        return _clamp(discount, 0.70, 0.99)

    if family_key in {"value", "nutted_value"}:
        discount = 0.96
        if params.thinking_player:
            discount -= 0.06
        if params.maniac:
            discount += 0.03
        if decision_node == "facing_raise":
            discount -= 0.03
        return _clamp(discount, 0.78, 1.00)

    return 1.0


def _pair_plus_draw_semibluff_floor(
    *,
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
    street: Street,
    decision_node: DecisionNode,
) -> float:
    """
    Pair+draw hands that bucket into SDV/Value should still retain some semibluff
    aggression because they carry real draw equity on top of made-hand strength.

    This floor is most important for Steve, moderate for Erik/Blake, and small for
    the passive / underbluffing profiles.
    """
    if not policy_view.is_pair_plus_draw:
        return 0.0
    if policy_view.active_family_key not in {"sdv", "value", "nutted_value"}:
        return 0.0

    base = 0.04 + policy_view.draw_strength * 0.10
    base *= _clamp(1.0 + params.bluff_bias * 1.80, 0.60, 1.60)

    if params.maniac:
        base += 0.12
    elif params.thinking_player:
        base -= 0.02
    elif params.aggressive:
        base += 0.02
    elif params.passive or params.calling_station:
        base -= 0.04
    else:
        base -= 0.02

    if decision_node == "facing_raise":
        base += 0.04
    elif decision_node == "facing_small_bet":
        base += 0.02

    if street == Street.TURN:
        base -= 0.01

    if policy_view.active_family_key == "value":
        base += 0.02

    return _clamp(base, 0.02, 0.40)

def _river_value_bet_force(
    *,
    policy_view: VillainPolicyView,
    family: FamilyTendency,
    street_profile: StreetProfile,
    params: VillainProfileParams,
    value_aggr_mult: float,
    hero_aggr_penalty: float,
) -> float:
    """
    River value betting needs to distinguish thin value from clear value.

    Prior hero aggression should push everyone toward more checking with medium
    value, while near-nutted hands should still strongly prefer betting.
    """
    base = family.thin_value_freq * street_profile.thin_value_mult
    base *= _river_thin_value_multiplier(params, policy_view.value_strength)
    base *= value_aggr_mult
    base *= hero_aggr_penalty

    if policy_view.is_nuts:
        return max(base, 0.98)
    if policy_view.is_near_nuts:
        return max(base, 0.90)

    strong_threshold = params.river_thresholds.strong_value_threshold
    if policy_view.value_strength >= strong_threshold:
        bonus = 1.0 + (policy_view.value_strength - strong_threshold) * 1.40
        base *= _clamp(bonus, 1.08, 1.34)

    return base


def _enforce_min_total_raise_share(
    menu_weights: dict[str, float],
    minimum_raise_share: float,
) -> dict[str, float]:
    """
    Lift total raise share to a minimum by borrowing mostly from call, then fold.
    Used for hard aggression floors like Steve's strong draws / natural bluffs.
    """
    normalized = _normalize_weights(menu_weights)
    current_raise = (
        normalized.get("raise_small", 0.0)
        + normalized.get("raise_normal", 0.0)
        + normalized.get("raise_big", 0.0)
    )
    if current_raise >= minimum_raise_share:
        return normalized

    needed = minimum_raise_share - current_raise
    take_from_call = min(normalized.get("call", 0.0), needed * 0.80)
    normalized["call"] = normalized.get("call", 0.0) - take_from_call
    needed -= take_from_call

    if needed > 0:
        take_from_fold = min(normalized.get("fold", 0.0), needed)
        normalized["fold"] = normalized.get("fold", 0.0) - take_from_fold
        needed -= take_from_fold

    injected = minimum_raise_share - current_raise - max(0.0, needed)
    if injected <= 0:
        return _normalize_weights(normalized)

    raise_total = (
        normalized.get("raise_small", 0.0)
        + normalized.get("raise_normal", 0.0)
        + normalized.get("raise_big", 0.0)
    )
    if raise_total <= 0:
        normalized["raise_small"] = normalized.get("raise_small", 0.0) + injected * 0.24
        normalized["raise_normal"] = normalized.get("raise_normal", 0.0) + injected * 0.46
        normalized["raise_big"] = normalized.get("raise_big", 0.0) + injected * 0.30
    else:
        normalized["raise_small"] += injected * normalized["raise_small"] / raise_total
        normalized["raise_normal"] += injected * normalized["raise_normal"] / raise_total
        normalized["raise_big"] += injected * normalized["raise_big"] / raise_total

    return _normalize_weights(normalized)


def _open_bet_size_bias(
    *,
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
    street: Street,
    texture_info: BoardTextureInfo | None,
) -> dict[str, float]:
    """
    Relative size-family preferences for unopened betting actions.
    """
    small = 1.0
    medium = 1.0
    big = 1.0
    overbet = 0.0 if not params.size_profile.allow_overbet_bet else 0.22

    if policy_view.active_family_key == "air":
        small += 0.30
        medium += 0.08
        big -= 0.12
        if street == Street.RIVER and policy_view.is_missed_draw_river_air:
            medium += 0.18
            big += 0.12
        else:
            big -= 0.06
        overbet *= 0.28

    elif policy_view.active_family_key == "sdv":
        small += 0.26
        medium += 0.08
        big -= 0.18
        if policy_view.is_pair_plus_draw:
            medium += 0.04
            big *= 0.92
        overbet *= 0.12

    elif policy_view.active_family_key == "draw":
        medium += 0.16 + policy_view.draw_strength * 0.22
        big += max(0.0, policy_view.draw_strength - 0.55) * 0.36
        small += (1.0 - policy_view.draw_strength) * 0.16
        if policy_view.is_pair_plus_draw:
            big *= 0.88
            medium += 0.04
        if policy_view.can_make_nutted_draw:
            big += 0.12
        overbet *= 0.34 if params.size_profile.dynamic_sizing else 0.10

    else:
        # value / nutted value
        medium += 0.18
        big += policy_view.value_strength * 0.40
        if street != Street.RIVER:
            big += policy_view.vulnerability * 0.22
        if policy_view.is_invulnerable_value:
            small += 0.10
            medium += 0.08
            big *= 0.88
        if policy_view.is_pair_plus_draw:
            big *= 0.94
        if params.size_profile.allow_overbet_bet:
            if params.size_profile.dynamic_sizing:
                overbet += policy_view.value_strength * 0.26
                if texture_info and texture_info.dynamic_board and street == Street.TURN:
                    overbet += 0.12
                if street == Street.RIVER and (policy_view.is_nuts or policy_view.is_near_nuts):
                    overbet += 0.24
            else:
                overbet += max(0.0, policy_view.value_strength - 0.84) * 0.12
                if street == Street.RIVER and (policy_view.is_nuts or policy_view.is_near_nuts):
                    overbet += 0.12

    if policy_view.active_family_key == "air":
        small += params.size_profile.bluff_size_discount * 1.20
        medium += params.size_profile.bluff_size_discount * 0.35

    return {
        "small": max(0.01, small),
        "medium": max(0.01, medium),
        "big": max(0.01, big),
        "overbet": max(0.0, overbet),
    }

def _raise_size_bias(
    *,
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
    decision_node: DecisionNode,
    street: Street,
) -> dict[str, float]:
    """
    Relative raise-size preferences.

    Calibration:
    - smaller faced bets -> bigger raises more often
    - passive players are more face up and mostly size by hand strength
    - Erik is dynamic; Steve is chaotic but still guardrailed
    """
    small = 1.0
    normal = 1.0
    big = 1.0

    if policy_view.active_family_key == "air":
        small += 0.22
        normal += 0.10
        big -= 0.10
        if street == Street.RIVER and policy_view.is_missed_draw_river_air:
            normal += 0.16
            big += 0.12

    elif policy_view.active_family_key == "sdv":
        small += 0.28
        normal += 0.04
        big -= 0.22
        if policy_view.is_pair_plus_draw:
            normal += 0.06
            big *= 0.92

    elif policy_view.active_family_key == "draw":
        normal += 0.18
        big += policy_view.draw_strength * 0.24
        if policy_view.is_pair_plus_draw:
            big *= 0.86
            normal += 0.06

    else:
        normal += 0.16
        big += policy_view.value_strength * 0.34
        if street != Street.RIVER:
            big += policy_view.vulnerability * 0.20
        if policy_view.is_invulnerable_value:
            small += 0.12
            normal += 0.08
            big *= 0.88
        if street == Street.RIVER and (policy_view.is_nuts or policy_view.is_near_nuts):
            normal += 0.22
            big += 0.34
            small *= 0.70

    if decision_node == "facing_small_bet":
        big += 0.18
    elif decision_node == "facing_big_bet":
        small += 0.18
    elif decision_node == "facing_overbet":
        small += 0.28
        big *= 0.78
    elif decision_node == "facing_raise":
        small += 0.06
        normal += 0.10
        if street == Street.RIVER and (policy_view.is_nuts or policy_view.is_near_nuts):
            big += 0.12

    return {
        "small": max(0.01, small),
        "normal": max(0.01, normal),
        "big": max(0.01, big),
    }

def _aggregate_open_menu_to_action_weights(
    menu_weights: dict[str, float],
) -> dict[ActionType, float]:
    check = menu_weights.get("check", 0.0)
    bet = (
        menu_weights.get("bet_small", 0.0)
        + menu_weights.get("bet_medium", 0.0)
        + menu_weights.get("bet_big", 0.0)
        + menu_weights.get("bet_overbet", 0.0)
    )
    return _normalize_weights(
        {
            ActionType.CHECK: check,
            ActionType.BET: bet,
        }
    )


def _aggregate_facing_menu_to_action_weights(
    menu_weights: dict[str, float],
) -> dict[ActionType, float]:
    fold = menu_weights.get("fold", 0.0)
    call = menu_weights.get("call", 0.0)
    raise_total = (
        menu_weights.get("raise_small", 0.0)
        + menu_weights.get("raise_normal", 0.0)
        + menu_weights.get("raise_big", 0.0)
    )
    return _normalize_weights(
        {
            ActionType.FOLD: fold,
            ActionType.CALL: call,
            ActionType.RAISE: raise_total,
        }
    )


def _apply_open_guardrails(
    *,
    menu_weights: dict[str, float],
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
    street: Street,
) -> dict[str, float]:
    out = dict(menu_weights)
    guard = params.guardrails

    if policy_view.active_family_key == "sdv":
        out["bet_big"] *= 0.42
        out["bet_overbet"] *= 0.20

    if policy_view.active_family_key == "air" and not params.size_profile.allow_overbet_bet:
        out["bet_overbet"] = 0.0

    if street == Street.RIVER and policy_view.active_family_key == "value":
        if policy_view.is_nuts:
            out["check"] *= 0.01
            out["bet_big"] += 0.28
            if params.size_profile.allow_overbet_bet:
                out["bet_overbet"] += params.size_profile.polar_overbet_bonus + 0.16
        elif policy_view.is_near_nuts:
            out["check"] *= 0.04
            out["bet_big"] += 0.20
            if params.size_profile.allow_overbet_bet:
                out["bet_overbet"] += params.size_profile.polar_overbet_bonus + 0.10

    if street != Street.RIVER and policy_view.is_invulnerable_value:
        out["check"] += guard.invulnerable_slowplay_bonus

    return _normalize_weights(out)

def _apply_facing_guardrails(
    *,
    menu_weights: dict[str, float],
    policy_view: VillainPolicyView,
    params: VillainProfileParams,
    street: Street,
    decision_node: DecisionNode,
    can_raise: bool,
    prior_villain_aggressive_actions: int,
) -> dict[str, float]:
    out = dict(menu_weights)
    guard = params.guardrails

    if not can_raise:
        out["raise_small"] = 0.0
        out["raise_normal"] = 0.0
        out["raise_big"] = 0.0

    if guard.never_fold_nutted_value and policy_view.family_key == "nutted_value":
        out["fold"] = 0.0

    if street == Street.RIVER and can_raise and policy_view.active_family_key == "value":
        if policy_view.is_nuts:
            out["fold"] = 0.0
            out["call"] = 0.0
            out["raise_small"] = 0.0
            out["raise_normal"] = 0.30
            out["raise_big"] = 0.70
        elif policy_view.is_near_nuts:
            out["fold"] = 0.0
            out["call"] = 0.0
            out["raise_small"] = 0.0
            out["raise_normal"] = 0.46
            out["raise_big"] = 0.54

    if (
        street == Street.RIVER
        and guard.never_call_river_near_zero_air
        and policy_view.active_family_key == "air"
        and policy_view.equity_vs_hero <= guard.near_zero_equity_cutoff
    ):
        out["call"] = 0.0

    if policy_view.active_family_key == "air":
        call_cap = guard.max_air_call_freq
        current_total = sum(out.values())
        if current_total > 0:
            normalized = _normalize_weights(out)
            if normalized["call"] > call_cap:
                spill = normalized["call"] - call_cap
                normalized["call"] = call_cap
                normalized["fold"] += spill * 0.75
                normalized["raise_small"] += spill * 0.15
                normalized["raise_normal"] += spill * 0.10
                out = normalized

    if policy_view.active_family_key == "sdv":
        raise_cap = guard.max_sdv_raise_freq
        normalized = _normalize_weights(out)
        current_raise = normalized["raise_small"] + normalized["raise_normal"] + normalized["raise_big"]
        if current_raise > raise_cap:
            scale = raise_cap / current_raise if current_raise > 0 else 0.0
            normalized["raise_small"] *= scale
            normalized["raise_normal"] *= scale
            normalized["raise_big"] *= scale
            redistributed = 1.0 - sum(normalized.values())
            normalized["call"] += redistributed * 0.85
            normalized["fold"] += redistributed * 0.15
            out = normalized

    if params.passive and policy_view.active_family_key == "draw":
        raise_cap = guard.max_passive_draw_raise_freq
        normalized = _normalize_weights(out)
        current_raise = normalized["raise_small"] + normalized["raise_normal"] + normalized["raise_big"]
        if current_raise > raise_cap:
            scale = raise_cap / current_raise if current_raise > 0 else 0.0
            normalized["raise_small"] *= scale
            normalized["raise_normal"] *= scale
            normalized["raise_big"] *= scale
            redistributed = 1.0 - sum(normalized.values())
            normalized["call"] += redistributed * 0.90
            normalized["fold"] += redistributed * 0.10
            out = normalized

    if decision_node == "facing_raise":
        out["raise_big"] *= 0.88

    if can_raise:
        normalized = _normalize_weights(out)
        if params.maniac and policy_view.active_family_key == "draw" and (policy_view.is_strong_draw or policy_view.is_pair_plus_draw):
            min_raise = {
                "facing_small_bet": 0.22,
                "facing_medium_bet": 0.18,
                "facing_big_bet": 0.12,
                "facing_overbet": 0.08,
                "facing_raise": 0.30,
            }.get(decision_node, 0.0)
            if policy_view.is_pair_plus_draw:
                min_raise -= 0.03
            normalized = _enforce_min_total_raise_share(normalized, max(0.0, min_raise))

        if street != Street.RIVER and policy_view.is_pair_plus_draw and decision_node == "facing_raise":
            if params.maniac:
                min_raise = 0.30
            elif params.thinking_player:
                min_raise = 0.13
            elif params.aggressive:
                min_raise = 0.17
            elif params.passive or params.calling_station:
                min_raise = 0.02
            else:
                min_raise = 0.05
            normalized = _enforce_min_total_raise_share(normalized, min_raise)

        if (
            params.maniac
            and street == Street.RIVER
            and policy_view.active_family_key == "air"
            and policy_view.is_missed_draw_river_air
            and prior_villain_aggressive_actions > 0
        ):
            min_raise = 0.22 if decision_node != "facing_raise" else 0.30
            normalized = _enforce_min_total_raise_share(normalized, min_raise)
        out = normalized

    return _normalize_weights(out)

def _build_open_menu_weights(
    *,
    policy_view: VillainPolicyView,
    family: FamilyTendency,
    subgroup: SubgroupOverride,
    street_profile: StreetProfile,
    texture_profiles: list[TextureProfile],
    texture_info: BoardTextureInfo | None,
    params: VillainProfileParams,
    street: Street,
    prior_villain_aggressive_actions: int,
    prior_hero_aggressive_actions: int,
    villain_is_current_aggressor: bool | None,
    villain_is_pfa: bool | None,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """
    Build unopened action-size menu.

    Returns:
    - normalized unopened menu weights
    - normalized bet size weights
    - debug metrics
    """
    base_menu = family.unopened_menu.for_node("unopened")
    bet_size_bias = _open_bet_size_bias(
        policy_view=policy_view,
        params=params,
        street=street,
        texture_info=texture_info,
    )

    bluff_aggr_mult, value_aggr_mult = _current_aggressor_modifiers(
        params,
        villain_is_current_aggressor,
    )
    non_pfa_bluff_mult = _non_pfa_bluff_multiplier(params, villain_is_pfa)
    prior_bluff_mult, hero_aggr_penalty = _prior_line_modifiers(
        params,
        prior_villain_aggressive_actions=prior_villain_aggressive_actions,
        prior_hero_aggressive_actions=prior_hero_aggressive_actions,
        street=street,
    )

    draw_aggr_texture = _multiply_texture_attr(texture_profiles, "draw_aggression_mult")
    value_fastplay_texture = _multiply_texture_attr(texture_profiles, "value_fastplay_mult")
    nutted_fastplay_texture = _multiply_texture_attr(texture_profiles, "nutted_fastplay_mult")
    trap_texture = _multiply_texture_attr(texture_profiles, "trap_mult")
    bluff_texture = _multiply_texture_attr(texture_profiles, "bluff_mult")

    pair_plus_draw_discount = _pair_plus_draw_aggression_discount(
        policy_view=policy_view,
        params=params,
        street=street,
        decision_node="unopened",
    )

    lead_force = family.lead_freq * street_profile.lead_mult
    trap_force = family.trap_freq * street_profile.trap_mult * trap_texture

    if policy_view.active_family_key == "draw":
        bet_force = lead_force * _equity_aggression_multiplier(policy_view, family)
        bet_force *= draw_aggr_texture
        bet_force *= pair_plus_draw_discount
        if subgroup.dead_draw_penalty or policy_view.is_weak_draw:
            bet_force *= 0.82
        if policy_view.can_make_nutted_draw:
            bet_force *= 1.08
        check_force = 1.0 + trap_force * 0.50

    elif policy_view.active_family_key == "sdv":
        if street == Street.RIVER:
            bet_force = family.thin_value_freq * street_profile.thin_value_mult
            bet_force *= _river_thin_value_multiplier(params, policy_view.value_strength)
            bet_force *= hero_aggr_penalty
        else:
            bet_force = lead_force * _equity_aggression_multiplier(policy_view, family) * 0.28
            if policy_view.is_pair_plus_draw:
                bet_force *= pair_plus_draw_discount
        check_force = 1.12 + trap_force * 0.60

    elif policy_view.active_family_key == "value":
        if street == Street.RIVER:
            bet_force = _river_value_bet_force(
                policy_view=policy_view,
                family=family,
                street_profile=street_profile,
                params=params,
                value_aggr_mult=value_aggr_mult,
                hero_aggr_penalty=hero_aggr_penalty,
            )
        else:
            bet_force = lead_force * _equity_aggression_multiplier(policy_view, family)
            bet_force *= value_fastplay_texture
            bet_force *= 1.0 + params.turn_fastplay_bias * (0.40 if street == Street.TURN else 0.0)
            if policy_view.vulnerability > 0:
                bet_force *= 1.0 + policy_view.vulnerability * (0.42 + params.turn_fastplay_bias * 0.18)
            bet_force *= value_aggr_mult
            if policy_view.is_pair_plus_draw:
                bet_force *= pair_plus_draw_discount
        check_force = max(0.20, 1.0 + trap_force - policy_view.vulnerability * 0.18)

    elif policy_view.active_family_key == "nutted_value":
        bet_force = lead_force * _equity_aggression_multiplier(policy_view, family)
        bet_force *= nutted_fastplay_texture
        bet_force *= 1.0 + params.turn_fastplay_bias * (0.34 if street == Street.TURN else 0.0)
        if policy_view.vulnerability > 0:
            bet_force *= 1.0 + policy_view.vulnerability * 0.22
        bet_force *= value_aggr_mult
        if policy_view.is_pair_plus_draw:
            bet_force *= pair_plus_draw_discount
        check_force = max(0.16, 1.0 + trap_force - policy_view.vulnerability * 0.10)

    else:
        # air
        if street == Street.RIVER:
            bet_force = family.river_bluff_freq * _river_bluff_threshold_multiplier(params)
            bet_force *= prior_bluff_mult
            if policy_view.is_missed_draw_river_air:
                bet_force *= 1.18
            else:
                bet_force *= 0.80
        else:
            bet_force = family.bluff_freq * street_profile.bluff_mult
        bet_force *= bluff_texture
        bet_force *= bluff_aggr_mult
        bet_force *= non_pfa_bluff_mult
        check_force = 1.18 + trap_force * 0.10

    menu = {
        "check": base_menu.get("check", 0.0) * check_force,
        "bet_small": base_menu.get("bet_small", 0.0) * bet_force * bet_size_bias["small"],
        "bet_medium": base_menu.get("bet_medium", 0.0) * bet_force * bet_size_bias["medium"],
        "bet_big": base_menu.get("bet_big", 0.0) * bet_force * bet_size_bias["big"],
        "bet_overbet": base_menu.get("bet_overbet", 0.0) * bet_force * bet_size_bias["overbet"],
    }

    menu = _apply_open_guardrails(
        menu_weights=menu,
        policy_view=policy_view,
        params=params,
        street=street,
    )

    bet_size_weights = _normalize_weights(
        {
            "small": menu["bet_small"],
            "medium": menu["bet_medium"],
            "big": menu["bet_big"],
            "overbet": menu["bet_overbet"],
        }
    )

    debug = {
        "bet_force": float(bet_force),
        "check_force": float(check_force),
        "trap_force": float(trap_force),
        "hero_aggr_penalty": float(hero_aggr_penalty),
        "pair_plus_draw_discount": float(pair_plus_draw_discount),
    }
    return menu, bet_size_weights, debug

def _build_facing_menu_weights(
    *,
    policy_view: VillainPolicyView,
    family: FamilyTendency,
    subgroup: SubgroupOverride,
    street_profile: StreetProfile,
    texture_profiles: list[TextureProfile],
    texture_info: BoardTextureInfo | None,
    params: VillainProfileParams,
    street: Street,
    decision_node: DecisionNode,
    to_call: float,
    pot: float,
    can_raise: bool,
    prior_villain_aggressive_actions: int,
    prior_hero_aggressive_actions: int,
    villain_is_current_aggressor: bool | None,
    villain_is_pfa: bool | None,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """
    Build facing-bet or facing-raise action-size menu.
    """
    facing_template = (
        family.facing_raise_menu.for_node("facing_raise")
        if decision_node == "facing_raise"
        else family.facing_bet_menu.for_node("facing_small_bet")
    )
    raise_size_bias = _raise_size_bias(
        policy_view=policy_view,
        params=params,
        decision_node=decision_node,
        street=street,
    )

    bluff_aggr_mult, value_aggr_mult = _current_aggressor_modifiers(
        params,
        villain_is_current_aggressor,
    )
    non_pfa_bluff_mult = _non_pfa_bluff_multiplier(params, villain_is_pfa)
    prior_bluff_mult, hero_aggr_penalty = _prior_line_modifiers(
        params,
        prior_villain_aggressive_actions=prior_villain_aggressive_actions,
        prior_hero_aggressive_actions=prior_hero_aggressive_actions,
        street=street,
    )

    continue_pressure = _node_continue_pressure(decision_node)
    raise_pressure = _node_raise_pressure(decision_node)
    fold_pressure = _node_fold_pressure(decision_node)

    draw_continue_texture = _multiply_texture_attr(texture_profiles, "draw_continue_mult")
    draw_aggr_texture = _multiply_texture_attr(texture_profiles, "draw_aggression_mult")
    sdv_continue_texture = _multiply_texture_attr(texture_profiles, "sdv_continue_mult")
    value_fastplay_texture = _multiply_texture_attr(texture_profiles, "value_fastplay_mult")
    nutted_fastplay_texture = _multiply_texture_attr(texture_profiles, "nutted_fastplay_mult")
    bluff_texture = _multiply_texture_attr(texture_profiles, "bluff_mult")

    pair_plus_draw_discount = _pair_plus_draw_aggression_discount(
        policy_view=policy_view,
        params=params,
        street=street,
        decision_node=decision_node,
    )

    if decision_node == "facing_raise":
        continue_force = family.facing_raise_continue * max(0.86, street_profile.continue_mult * 0.96)
        raise_force = family.facing_raise_reraise * max(0.82, street_profile.raise_mult * 0.92)
    else:
        continue_force = family.continue_vs_bet * street_profile.continue_mult
        raise_force = family.raise_vs_bet * street_profile.raise_mult
    fold_force = 1.0

    if policy_view.active_family_key == "draw":
        continue_force *= _equity_continue_multiplier(policy_view, family)
        continue_force *= draw_continue_texture
        continue_force *= _raw_dollar_continue_multiplier(
            to_call=to_call,
            street=street,
            family_key="draw",
            sensitivity=params.raw_dollar_sensitivity,
        )
        raise_force *= _equity_aggression_multiplier(policy_view, family)
        raise_force *= draw_aggr_texture
        raise_force *= pair_plus_draw_discount
        if subgroup.dead_draw_penalty or policy_view.is_weak_draw:
            raise_force *= 0.80
        if policy_view.can_make_nutted_draw:
            raise_force *= 1.08
        raise_force *= max(0.55, 1.0 - params.turn_draw_aggression_penalty * (0.60 if street == Street.TURN else 0.20))
        fold_force *= 1.00

    elif policy_view.active_family_key == "sdv":
        continue_force *= _equity_continue_multiplier(policy_view, family)
        continue_force *= sdv_continue_texture
        continue_force *= _raw_dollar_continue_multiplier(
            to_call=to_call,
            street=street,
            family_key="sdv",
            sensitivity=params.raw_dollar_sensitivity,
        )
        if street == Street.RIVER:
            continue_force *= _river_sdv_call_multiplier(params, policy_view.equity_vs_hero)
            continue_force *= hero_aggr_penalty
        raise_force *= _equity_aggression_multiplier(policy_view, family) * 0.55
        if policy_view.is_pair_plus_draw:
            raise_force *= pair_plus_draw_discount
            raise_force = max(
                raise_force,
                _pair_plus_draw_semibluff_floor(
                    policy_view=policy_view,
                    params=params,
                    street=street,
                    decision_node=decision_node,
                ),
            )
        fold_force *= 1.04

    elif policy_view.active_family_key == "value":
        continue_force *= _equity_continue_multiplier(policy_view, family)
        continue_force *= _raw_dollar_continue_multiplier(
            to_call=to_call,
            street=street,
            family_key="value",
            sensitivity=params.raw_dollar_sensitivity,
        )
        if street == Street.RIVER:
            river_value_mult = _river_thin_value_multiplier(params, policy_view.value_strength)
            continue_force *= river_value_mult
            continue_force *= hero_aggr_penalty
            raise_force *= river_value_mult
            raise_force *= value_aggr_mult
        else:
            raise_force *= _equity_aggression_multiplier(policy_view, family)
            raise_force *= value_fastplay_texture
            raise_force *= 1.0 + params.turn_fastplay_bias * (0.40 if street == Street.TURN else 0.0)
            if policy_view.vulnerability > 0:
                raise_force *= 1.0 + policy_view.vulnerability * 0.32
            raise_force *= value_aggr_mult
        if policy_view.is_pair_plus_draw:
            raise_force *= pair_plus_draw_discount
            raise_force = max(
                raise_force,
                _pair_plus_draw_semibluff_floor(
                    policy_view=policy_view,
                    params=params,
                    street=street,
                    decision_node=decision_node,
                ),
            )
        fold_force *= 0.90

    elif policy_view.active_family_key == "nutted_value":
        continue_force *= 1.10
        raise_force *= _equity_aggression_multiplier(policy_view, family)
        raise_force *= nutted_fastplay_texture
        raise_force *= value_aggr_mult
        if street != Street.RIVER and policy_view.vulnerability > 0:
            raise_force *= 1.0 + policy_view.vulnerability * 0.18
        if policy_view.is_pair_plus_draw:
            raise_force *= pair_plus_draw_discount
            raise_force = max(
                raise_force,
                _pair_plus_draw_semibluff_floor(
                    policy_view=policy_view,
                    params=params,
                    street=street,
                    decision_node=decision_node,
                ),
            )
        fold_force *= 0.16

    else:
        # air
        continue_force *= _equity_continue_multiplier(policy_view, family)
        continue_force *= _raw_dollar_continue_multiplier(
            to_call=to_call,
            street=street,
            family_key="air",
            sensitivity=params.raw_dollar_sensitivity,
        )
        if street == Street.RIVER:
            raise_force *= family.river_bluff_freq * _river_bluff_threshold_multiplier(params)
            raise_force *= prior_bluff_mult
            continue_force *= hero_aggr_penalty
            if policy_view.is_missed_draw_river_air:
                raise_force *= 1.24
            else:
                raise_force *= 0.78
        else:
            raise_force *= family.bluff_freq * street_profile.bluff_mult
        raise_force *= bluff_texture
        raise_force *= bluff_aggr_mult
        raise_force *= non_pfa_bluff_mult
        fold_force *= 1.10

    continue_force *= continue_pressure
    raise_force *= raise_pressure
    fold_force *= fold_pressure
    continue_force *= max(0.52, 1.0 - params.facing_raise_tightness * (0.22 if decision_node == "facing_raise" else 0.0))
    raise_force *= max(0.38, 1.0 - params.facing_raise_tightness * (0.52 if decision_node == "facing_raise" else 0.0))

    total_raise_share = _clamp(raise_force, 0.0, 1.20)
    raise_drain = 0.40 if decision_node == "facing_raise" else 0.55
    call_share = max(0.02, continue_force - total_raise_share * raise_drain)

    menu = {
        "fold": facing_template.get("fold", 0.0) * max(0.02, fold_force),
        "call": facing_template.get("call", 0.0) * call_share,
        "raise_small": facing_template.get("raise_small", 0.0) * total_raise_share * raise_size_bias["small"],
        "raise_normal": facing_template.get("raise_normal", 0.0) * total_raise_share * raise_size_bias["normal"],
        "raise_big": facing_template.get("raise_big", 0.0) * total_raise_share * raise_size_bias["big"],
    }

    menu = _apply_facing_guardrails(
        menu_weights=menu,
        policy_view=policy_view,
        params=params,
        street=street,
        decision_node=decision_node,
        can_raise=can_raise,
        prior_villain_aggressive_actions=prior_villain_aggressive_actions,
    )

    raise_size_weights = _normalize_weights(
        {
            "small": menu["raise_small"],
            "normal": menu["raise_normal"],
            "big": menu["raise_big"],
        }
    )

    debug = {
        "continue_force": float(continue_force),
        "raise_force": float(raise_force),
        "fold_force": float(fold_force),
        "raw_call_size": float(to_call),
        "size_frac_of_pot": float(_size_frac_of_pot(to_call, pot)),
        "hero_aggr_penalty": float(hero_aggr_penalty),
        "pair_plus_draw_discount": float(pair_plus_draw_discount),
    }
    return menu, raise_size_weights, debug

def build_villain_action_policy(
    *,
    bucket_result: VillainHandBucketResult,
    params: VillainProfileParams,
    street: Street,
    to_call: float,
    pot: float,
    can_raise: bool = True,
    board: list[str] | tuple[str, ...] | None = None,
    node_hint: DecisionNode | None = None,
    villain_is_current_aggressor: bool | None = None,
    villain_is_pfa: bool | None = None,
    prior_villain_aggressive_actions: int = 0,
    prior_hero_aggressive_actions: int = 0,
) -> VillainActionPolicy:
    """
    Build node-aware villain action policy.

    Layering:
    1. broad family defaults from villain profile
    2. a very small set of subgroup nudges
    3. street multipliers
    4. texture multipliers
    5. equity / vulnerability / threshold shaping
    6. node sizing pressure
    7. hard guardrails

    This function intentionally produces both:
    - explicit action-size menu weights
    - collapsed ActionType weights for compatibility / debugging
    """
    decision_node = _classify_decision_node(
        to_call=to_call,
        pot=pot,
        node_hint=node_hint,
    )
    policy_view = policy_view_from_bucket_result(
        bucket_result,
        street=street,
        decision_node=decision_node,
    )
    family = _family_for_policy(policy_view, params)
    subgroup = _effective_subgroup_override(params, policy_view.subgroup_label)
    street_profile = _effective_street_profile(params, street)
    texture_keys, texture_info = _effective_texture_keys_and_info(board)
    texture_profiles = _effective_texture_profiles(params, texture_keys)

    if decision_node == "unopened":
        open_menu_weights, bet_size_weights, debug = _build_open_menu_weights(
            policy_view=policy_view,
            family=family,
            subgroup=subgroup,
            street_profile=street_profile,
            texture_profiles=texture_profiles,
            texture_info=texture_info,
            params=params,
            street=street,
            prior_villain_aggressive_actions=prior_villain_aggressive_actions,
            prior_hero_aggressive_actions=prior_hero_aggressive_actions,
            villain_is_current_aggressor=villain_is_current_aggressor,
            villain_is_pfa=villain_is_pfa,
        )
        facing_menu_weights = {
            "fold": 0.0,
            "call": 0.0,
            "raise_small": 0.0,
            "raise_normal": 0.0,
            "raise_big": 0.0,
        }
        raise_size_weights = {"small": 0.0, "normal": 0.0, "big": 0.0}
        action_weights = _aggregate_open_menu_to_action_weights(open_menu_weights)

    else:
        facing_menu_weights, raise_size_weights, debug = _build_facing_menu_weights(
            policy_view=policy_view,
            family=family,
            subgroup=subgroup,
            street_profile=street_profile,
            texture_profiles=texture_profiles,
            texture_info=texture_info,
            params=params,
            street=street,
            decision_node=decision_node,
            to_call=to_call,
            pot=pot,
            can_raise=can_raise,
            prior_villain_aggressive_actions=prior_villain_aggressive_actions,
            prior_hero_aggressive_actions=prior_hero_aggressive_actions,
            villain_is_current_aggressor=villain_is_current_aggressor,
            villain_is_pfa=villain_is_pfa,
        )
        open_menu_weights = {
            "check": 0.0,
            "bet_small": 0.0,
            "bet_medium": 0.0,
            "bet_big": 0.0,
            "bet_overbet": 0.0,
        }
        bet_size_weights = {"small": 0.0, "medium": 0.0, "big": 0.0, "overbet": 0.0}
        action_weights = _aggregate_facing_menu_to_action_weights(facing_menu_weights)

    debug_payload: dict[str, float | str | bool] = {
        "bucket_label": policy_view.bucket_label,
        "subgroup_label": policy_view.subgroup_label,
        "family_key": policy_view.family_key,
        "river_family_key": policy_view.river_family_key,
        "active_family_key": policy_view.active_family_key,
        "decision_node": decision_node,
        "equity_vs_hero": round(policy_view.equity_vs_hero, 4),
        "draw_strength": round(policy_view.draw_strength, 4),
        "value_strength": round(policy_view.value_strength, 4),
        "vulnerability": round(policy_view.vulnerability, 4),
        "is_nuts": policy_view.is_nuts,
        "is_near_nuts": policy_view.is_near_nuts,
        "is_invulnerable_value": policy_view.is_invulnerable_value,
        "hero_range_source": policy_view.hero_range_source,
        "uses_scenario_hero_range": policy_view.uses_scenario_hero_range,
        **debug,
    }

    return VillainActionPolicy(
        action_weights=action_weights,
        open_menu_weights=open_menu_weights,
        facing_menu_weights=facing_menu_weights,
        bet_size_weights=bet_size_weights,
        raise_size_weights=raise_size_weights,
        policy_bucket=policy_view.family_key,
        river_policy_bucket=policy_view.river_family_key,
        decision_node=decision_node,
        facing_bet=decision_node != "unopened",
        size_frac_of_pot=_size_frac_of_pot(to_call, pot),
        raw_call_size=float(to_call),
        texture_keys=texture_keys,
        debug=debug_payload,
    )