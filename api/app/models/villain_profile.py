# File: api/app/models/villain_profile.py
# Summary: Data models for villain metadata and the reworked structured backend
# tendency system used to drive node-aware villain action logic, sizing behavior,
# river thresholds, board adjustments, and hard guardrails.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


VillainFamily = Literal["draw", "sdv", "value", "nutted_value", "air"]
StreetKey = Literal["flop", "turn", "river"]
DecisionNode = Literal[
    "unopened",
    "facing_small_bet",
    "facing_medium_bet",
    "facing_big_bet",
    "facing_overbet",
    "facing_raise",
]
TextureKey = Literal[
    "wet_connected",
    "static_paired",
    "static_unpaired",
    "flush_completed",
    "straight_completed",
    "paired_board",
    "monotone_flop",
    "four_to_flush",
    "four_to_straight",
    "double_paired",
    "broadway_static",
    "low_connected",
]
ActionKey = Literal["check", "bet", "fold", "call", "raise"]
BetSizeKey = Literal["small", "medium", "big", "overbet"]
RaiseSizeKey = Literal["small", "normal", "big"]
OpenMenuKey = Literal["check", "bet_small", "bet_medium", "bet_big", "bet_overbet"]
FacingMenuKey = Literal[
    "fold",
    "call",
    "raise_small",
    "raise_normal",
    "raise_big",
]


@dataclass(frozen=True)
class NumericBand:
    """
    Numeric sampling band for bet or raise sizes.

    The decision layer chooses a size family first, then samples inside the band.
    """

    low: float
    high: float

    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass(frozen=True)
class ActionMenuWeights:
    """
    Raw menu weights before normalization.

    The new decision engine works from explicit menu choices rather than a
    generic action-first / size-second model.

    Unopened menu:
    - check
    - bet_small
    - bet_medium
    - bet_big
    - bet_overbet

    Facing-bet / facing-raise menu:
    - fold
    - call
    - raise_small
    - raise_normal
    - raise_big
    """

    check: float = 0.0
    bet_small: float = 0.0
    bet_medium: float = 0.0
    bet_big: float = 0.0
    bet_overbet: float = 0.0

    fold: float = 0.0
    call: float = 0.0
    raise_small: float = 0.0
    raise_normal: float = 0.0
    raise_big: float = 0.0

    def for_node(self, node: DecisionNode) -> dict[str, float]:
        if node == "unopened":
            return {
                "check": self.check,
                "bet_small": self.bet_small,
                "bet_medium": self.bet_medium,
                "bet_big": self.bet_big,
                "bet_overbet": self.bet_overbet,
            }
        return {
            "fold": self.fold,
            "call": self.call,
            "raise_small": self.raise_small,
            "raise_normal": self.raise_normal,
            "raise_big": self.raise_big,
        }


@dataclass(frozen=True)
class SizeProfile:
    """
    Villain sizing behavior when betting or raising.

    Notes:
    - bet sizes are stored as pot-fraction bands
    - raise sizes are stored as multipliers of the amount being faced
    - larger sizings can be encouraged by equity, vulnerability, polarity,
      player identity, and board dynamics in the policy layer
    """

    small_bet: NumericBand = field(default_factory=lambda: NumericBand(0.25, 0.40))
    medium_bet: NumericBand = field(default_factory=lambda: NumericBand(0.45, 0.70))
    big_bet: NumericBand = field(default_factory=lambda: NumericBand(0.75, 1.10))
    overbet: NumericBand = field(default_factory=lambda: NumericBand(1.10, 1.50))

    small_raise: NumericBand = field(default_factory=lambda: NumericBand(2.20, 2.80))
    normal_raise: NumericBand = field(default_factory=lambda: NumericBand(2.80, 3.50))
    big_raise: NumericBand = field(default_factory=lambda: NumericBand(4.00, 5.00))

    allow_overbet_bet: bool = False
    allow_overbet_raise: bool = False
    dynamic_sizing: bool = False

    equity_size_correlation: float = 0.50
    vulnerability_size_correlation: float = 0.35
    bluff_size_discount: float = 0.10
    polar_overbet_bonus: float = 0.0


@dataclass(frozen=True)
class FamilyTendency:
    """
    Core behavior pattern for one broad villain family.

    The policy layer should treat these as semantic tendencies, not final
    probabilities. Equity is a major within-family driver, while the family
    itself defines the type of action pattern available.
    """

    continue_vs_bet: float
    raise_vs_bet: float
    lead_freq: float
    trap_freq: float

    facing_raise_continue: float = 0.0
    facing_raise_reraise: float = 0.0

    equity_aggression: float = 0.0
    equity_continue: float = 0.0
    vulnerability_fastplay: float = 0.0

    bluff_freq: float = 0.0
    river_bluff_freq: float = 0.0
    thin_value_freq: float = 0.0

    unopened_menu: ActionMenuWeights = field(default_factory=ActionMenuWeights)
    facing_bet_menu: ActionMenuWeights = field(default_factory=ActionMenuWeights)
    facing_raise_menu: ActionMenuWeights = field(default_factory=ActionMenuWeights)


@dataclass(frozen=True)
class SubgroupOverride:
    """
    Optional lightweight override for a specific subgroup.

    The new villain system should rely much less on micro subgroup tuning than
    the old version. These overrides are intended only for a few strategic flags:
    - pair+draw should usually raise less than pure strong draws
    - invulnerable nutted hands can trap more
    - especially dead / weak draws can continue less
    """

    continue_delta: float = 0.0
    raise_delta: float = 0.0
    lead_delta: float = 0.0
    bluff_delta: float = 0.0
    thin_value_delta: float = 0.0
    vulnerability_delta: float = 0.0

    prefer_trap: bool = False
    prefer_fastplay: bool = False
    pair_plus_draw_discount: bool = False
    dead_draw_penalty: bool = False


@dataclass(frozen=True)
class StreetProfile:
    """
    Street-level multipliers.

    These let the policy layer encode broad truths such as:
    - flop draw aggression > turn draw aggression for many players
    - turn value fast-play > flop value fast-play
    - river bluffing / thin value are player-specific threshold behaviors
    """

    continue_mult: float = 1.0
    raise_mult: float = 1.0
    lead_mult: float = 1.0
    bluff_mult: float = 1.0
    thin_value_mult: float = 1.0
    fastplay_mult: float = 1.0
    trap_mult: float = 1.0


@dataclass(frozen=True)
class TextureProfile:
    """
    Board-texture adjustment profile.

    These are villain-specific reactions to global texture concepts:
    - fast play more on wet connected boards
    - trap more on static paired boards
    - give up more with weak draws on completed boards
    - go thinner for value on some static runouts
    """

    value_fastplay_mult: float = 1.0
    nutted_fastplay_mult: float = 1.0
    draw_aggression_mult: float = 1.0
    draw_continue_mult: float = 1.0
    sdv_continue_mult: float = 1.0
    bluff_mult: float = 1.0
    thin_value_mult: float = 1.0
    trap_mult: float = 1.0
    vulnerability_mult: float = 1.0


@dataclass(frozen=True)
class RiverThresholdProfile:
    """
    River-only thresholds and line-based modifiers.

    River logic is intentionally simpler than flop/turn logic:
    - Air -> bluff or give up
    - SDV -> bluff-catch / check back / rarely bluff
    - Value -> value bet / raise / check some medium strength
    """

    thin_value_threshold: float = 0.60
    strong_value_threshold: float = 0.78
    bluff_threshold: float = 0.20
    sdv_call_threshold: float = 0.42

    prior_aggression_bluff_bonus: float = 0.20
    prior_hero_aggression_call_penalty: float = 0.15


@dataclass(frozen=True)
class GuardrailProfile:
    """
    Hard constraints and sanity guardrails for randomization.

    These exist so the final action sampling never produces nonsense.
    """

    near_zero_equity_cutoff: float = 0.08
    weak_equity_cutoff: float = 0.20
    strong_value_cutoff: float = 0.65
    nutted_value_cutoff: float = 0.82

    force_raise_river_nuts_if_possible: bool = True
    force_continue_strong_draws_vs_small_bets: bool = True
    never_call_river_near_zero_air: bool = True
    never_fold_nutted_value: bool = True

    max_air_call_freq: float = 0.15
    max_sdv_raise_freq: float = 0.08
    max_passive_draw_raise_freq: float = 0.10

    invulnerable_slowplay_bonus: float = 0.0
    completed_board_draw_aggression_penalty: float = 0.0
    completed_board_draw_continue_penalty: float = 0.0


@dataclass(frozen=True)
class VillainProfileParams:
    """
    Full structured backend tendency parameters for one villain.

    Design goals for the reworked engine:
    1. broad family defaults
    2. a very small set of subgroup nudges
    3. street adjustments
    4. texture adjustments
    5. node-aware size / equity / vulnerability adjustments
    6. river thresholds
    7. hard guardrails
    """

    family_profiles: dict[VillainFamily, FamilyTendency]
    subgroup_overrides: dict[str, SubgroupOverride] = field(default_factory=dict)
    street_profiles: dict[StreetKey, StreetProfile] = field(default_factory=dict)
    texture_profiles: dict[TextureKey, TextureProfile] = field(default_factory=dict)

    size_profile: SizeProfile = field(default_factory=SizeProfile)
    river_thresholds: RiverThresholdProfile = field(default_factory=RiverThresholdProfile)
    guardrails: GuardrailProfile = field(default_factory=GuardrailProfile)

    passive: bool = False
    aggressive: bool = False
    thinking_player: bool = False
    maniac: bool = False
    calling_station: bool = False

    overcall_bias: float = 0.0
    bluff_bias: float = 0.0
    trap_bias: float = 0.0
    thin_value_bias: float = 0.0

    raw_dollar_sensitivity: float = 0.0
    pot_fraction_sensitivity: float = 1.0
    current_aggressor_bluff_bonus: float = 0.0
    current_aggressor_value_bonus: float = 0.0
    non_pfa_bluff_penalty: float = 0.0
    facing_raise_tightness: float = 0.0
    turn_fastplay_bias: float = 0.0
    turn_draw_aggression_penalty: float = 0.0


@dataclass(frozen=True)
class VillainProfileMeta:
    """UI-facing metadata for a villain profile."""

    id: str
    display_name: str
    type_label: str
    description: str
    image_name: str


@dataclass(frozen=True)
class VillainProfile:
    """Combined villain profile object containing UI metadata and backend params."""

    meta: VillainProfileMeta
    params: VillainProfileParams