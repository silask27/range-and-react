# File: api/app/engine/villain_hand_bucket.py
# Summary: Helper for classifying villain's exact hidden hand into the current broad
# action family + subgroup while also returning richer policy signals for the rebuilt
# villain engine, including river-family simplification, equity-driven strength, and
# flop/turn vulnerability.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
import random
from typing import Iterable

from api.app.engine import bucketizer as bz
from api.app.engine.board_texture import evaluate_board_texture
from api.app.engine.cards import ensure_unique_cards, normalize_cards


@dataclass(frozen=True)
class VillainHandBucketResult:
    """
    Result of bucketing villain's exact hidden hand on the current board.

    Compatibility fields are preserved so downstream files do not break while the
    villain-policy rewrite is in progress.

    New action-focused fields:
    - family_key:
        broad family used by the flop/turn action engine
        one of: draw / sdv / value / nutted_value / air
    - river_family_key:
        simplified river family used by the river action engine
        one of: air / sdv / value
    - vulnerability:
        flop/turn-only measure of how likely a made hand is to lose relative
        strength or become uncomfortable on the next street. Always 0 on river.
    - draw_strength:
        coarse 0..1 draw-quality score used to scale draw aggression/continues
    - value_strength:
        coarse 0..1 made-hand strength score used inside Value/Nutted Value
    """

    # Existing / compatibility fields
    bucket_label: str
    subgroup_label: str
    display_subgroup_label: str
    model_subgroup_label: str
    raw_showdown_class: str
    board_made_tag: str | None
    pair_draw_driver: str | None
    draw_hit_contribution: float | None
    draw_miss_contribution: float | None
    equity_vs_hero: float
    user_type: str
    internal_class: str
    has_draw: bool
    villain_profile_id: str
    hero_range_source: str

    best_made_subgroup: str | None
    draw_profile: dict[str, bool | int | list[int]]

    is_nuts: bool
    is_near_nuts: bool
    rank_tier: int

    is_made_hand: bool
    is_pair_plus_draw: bool
    is_strong_draw: bool
    is_weak_draw: bool

    is_invulnerable_value: bool
    is_ace_high_flush: bool
    is_missed_draw_river_air: bool

    # New action-policy fields
    street_key: str
    family_key: str
    river_family_key: str

    vulnerability: float
    draw_strength: float
    value_strength: float

    has_nut_flush_draw: bool
    can_make_nutted_draw: bool
    uses_scenario_hero_range: bool


@lru_cache(maxsize=10_000)
def _cached_fixed_hero_combos() -> tuple[tuple[str, str], ...]:
    """
    Cache the fixed hero comparison range used by the villain engine for all
    villains except Erik.
    """
    return tuple(bz.expand_range_to_combos(list(bz.HERO_RANGE_TOKENS)))


@lru_cache(maxsize=10_000)
def _cached_scenario_hero_combos(
    labels: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """
    Cache scenario hero comparison combos for Erik.
    """
    exact_labels = tuple(bz.expand_range_tokens(labels))
    return tuple(bz.expand_range_to_combos(list(exact_labels)))


def _hero_combos_for_villain(
    villain_profile_id: str,
    scenario_hero_range_tokens: Iterable[str] | None,
) -> tuple[tuple[tuple[str, str], ...], str, bool]:
    """
    Return the hero comparison combo set, a label describing its source,
    and whether scenario range logic was used.

    Rules locked in from the design discussion:
    - Erik ("tag") uses scenario hero range when available
    - all other villains use the fixed HERO_RANGE_TOKENS baseline
    """
    if villain_profile_id == "tag" and scenario_hero_range_tokens:
        labels = tuple(str(token).strip() for token in scenario_hero_range_tokens if str(token).strip())
        if labels:
            return _cached_scenario_hero_combos(labels), "scenario", True

    return _cached_fixed_hero_combos(), "fixed", False


@lru_cache(maxsize=1)
def _full_deck() -> tuple[str, ...]:
    return tuple(f"{rank}{suit}" for rank in bz.RANKS for suit in bz.SUITS)


@lru_cache(maxsize=50_000)
def _legal_hole_combos_for_board(
    board: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """
    All legal two-card holdings on this board.
    """
    dead = set(board)
    deck = [card for card in _full_deck() if card not in dead]
    return tuple(tuple(sorted(combo)) for combo in combinations(deck, 2))


@lru_cache(maxsize=50_000)
def _distinct_rank_order_for_board(
    board: tuple[str, ...],
) -> tuple[tuple, ...]:
    """
    Sorted distinct 7-card hand ranks achievable on this board.
    Highest rank first.
    """
    ranks = {
        bz.rank_7(list(hole) + list(board))
        for hole in _legal_hole_combos_for_board(board)
    }
    return tuple(sorted(ranks, reverse=True))


def _rank_tier_for_hole(
    hole: tuple[str, str],
    board: tuple[str, ...],
) -> tuple[int, bool, bool]:
    """
    Returns:
    - rank_tier: 1 = nuts, 2 = second distinct rank tier, ...
    - is_nuts
    - is_near_nuts (top 2 distinct rank tiers)
    """
    villain_rank = bz.rank_7(list(hole) + list(board))
    rank_order = _distinct_rank_order_for_board(board)

    try:
        tier = rank_order.index(villain_rank) + 1
    except ValueError:
        tier = len(rank_order) + 1

    return tier, tier == 1, tier <= 2


def _is_ace_high_flush(
    hole: tuple[str, str],
    board: list[str],
) -> bool:
    """
    True only when the current best hand is a flush (not straight flush) and the
    villain's best flush is ace-high using a hole-card ace of the flush suit.
    """
    best_rank = bz.rank_7(list(hole) + board)
    if int(best_rank[0]) != 5:
        return False

    hole_set = set(hole)
    for best_five in bz.best_five_combos(hole, board):
        if bz.rank_5(tuple(best_five)) != best_rank:
            continue

        suits = {card[1] for card in best_five}
        if len(suits) != 1:
            continue

        flush_suit = next(iter(suits))
        hole_flush_cards = [card for card in best_five if card in hole_set and card[1] == flush_suit]
        if any(card[0] == "A" for card in hole_flush_cards):
            top_rank = max(bz.RANK_TO_VALUE[card[0]] for card in best_five)
            if top_rank == 14:
                return True

    return False


def _has_nut_flush_draw(
    hole: tuple[str, str],
    board: list[str],
    draw_profile: dict[str, bool | int | list[int]],
) -> bool:
    """
    True when villain holds the ace of the relevant flush-draw suit.
    """
    if not bool(draw_profile.get("flush_draw", False)):
        return False

    suit_counts: dict[str, int] = {}
    for card in list(hole) + board:
        suit_counts[card[1]] = suit_counts.get(card[1], 0) + 1

    flush_draw_suit = None
    for suit, count in suit_counts.items():
        if count == 4:
            flush_draw_suit = suit
            break

    if flush_draw_suit is None:
        return False

    return any(card[0] == "A" and card[1] == flush_draw_suit for card in hole)


def _can_make_nutted_draw(
    hole: tuple[str, str],
    board: list[str],
    draw_profile: dict[str, bool | int | list[int]],
) -> bool:
    """
    Very coarse flag used by policy:

    True when the current draw can realistically make nutted value, mainly:
    - nut flush draws
    - some strong straight / combo-draw patterns with near-nut potential
    """
    if _has_nut_flush_draw(hole, board, draw_profile):
        return True

    if bool(draw_profile.get("double_gutshot", False)):
        return True

    if bool(draw_profile.get("straight_draw", False)) and any(card[0] in {"A", "K"} for card in hole):
        return True

    return False


def _is_invulnerable_value(
    subgroup_label: str,
    *,
    is_nuts: bool,
    board: list[str],
    hole: tuple[str, str],
) -> bool:
    """
    "Invulnerable value" is meant for slowplay/trapping logic.
    Conservative definition:
    - always true for full house / quads / straight flush
    - true for ace-high flush
    - often true on river for exact nuts
    """
    if subgroup_label in {"Full House", "Quads", "Straight Flush"}:
        return True

    if subgroup_label == "Flush" and _is_ace_high_flush(hole, board):
        return True

    if len(board) == 5 and is_nuts:
        return True

    return False


def _is_made_hand(subgroup_label: str) -> bool:
    return subgroup_label in {
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


def _is_strong_draw(
    subgroup_label: str,
    draw_profile: dict[str, bool | int | list[int]],
) -> bool:
    if subgroup_label in {"Combo Draw", "Pair + Draw"}:
        return True
    if subgroup_label in {"Straight Draw", "Flush Draw"}:
        return True
    return bool(draw_profile.get("double_gutshot", False))


def _is_weak_draw(
    subgroup_label: str,
    draw_profile: dict[str, bool | int | list[int]],
) -> bool:
    if subgroup_label == "Gutshot":
        return True
    if subgroup_label == "High Card" and bool(draw_profile.get("gutshot", False)):
        return True
    return False


def _is_missed_draw_river_air(
    hole: tuple[str, str],
    board: list[str],
    subgroup_label: str,
) -> bool:
    """
    River-only helper:
    if the current river hand lands in High Card / Air, check whether the hand
    carried a meaningful flop/turn draw that bricked.
    """
    if len(board) != 5:
        return False
    if subgroup_label != "High Card":
        return False

    turn_board = board[:4]
    turn_draws = bz.draw_profile(hole, turn_board)
    return bool(
        turn_draws["straight_draw"]
        or turn_draws["gutshot"]
        or turn_draws["flush_draw"]
    )



UI_SUBGROUPS: list[str] = [
    "Full House+",
    "Flush",
    "Straight",
    "Trips",
    "Set",
    "Two Pair",
    "Overpair",
    "Strong Top Pair",
    "Weak Top Pair",
    "Mid Pair",
    "Low Pair",
    "Underpair",
    "Ace High",
    "Board-Made Hand",
    "Combo Draw",
    "Flush Draw",
    "Straight Draw",
    "Gutshot",
    "Strong Pair + Draw",
    "Weak Pair + Draw",
    "High Card",
    "Missed Draw",
]

STRONG_PAIR_UI_SUBGROUPS = {"Overpair", "Strong Top Pair", "Weak Top Pair"}
WEAK_PAIR_UI_SUBGROUPS = {"Mid Pair", "Low Pair", "Underpair"}


def _card_rank(card: str) -> int:
    return bz.RANK_TO_VALUE[card[0]]


def _unique_board_ranks_desc(board: list[str]) -> list[int]:
    return sorted({_card_rank(card) for card in board}, reverse=True)


def _is_board_made_best_hand(hole: tuple[str, str], board: list[str]) -> bool:
    """
    UI-facing rule: Board-Made Hand means the board itself is villain's best
    5-card hand, or the hole cards do not improve that best 5-card hand.
    This is only possible once five board cards are available.
    """
    if len(board) != 5:
        return False
    board_rank = bz.rank_5(tuple(sorted(board)))
    villain_rank = bz.rank_7(list(hole) + board)
    return villain_rank == board_rank


def _top_pair_kicker_value(hole: tuple[str, str], board: list[str]) -> int:
    top_board_rank = max(_card_rank(card) for card in board)
    hole_ranks = [_card_rank(card) for card in hole]
    kickers = [rank for rank in hole_ranks if rank != top_board_rank]
    return max(kickers) if kickers else 0


def _top_pair_ui_label(hole: tuple[str, str], board: list[str]) -> str:
    return "Strong Top Pair" if _top_pair_kicker_value(hole, board) >= 10 else "Weak Top Pair"


def _paired_rank_from_hole_and_board(hole: tuple[str, str], board: list[str]) -> int | None:
    board_ranks = {_card_rank(card) for card in board}
    for card in hole:
        rank = _card_rank(card)
        if rank in board_ranks:
            return rank
    return None


def _pocket_pair_rank_plays_in_best_hand(hole: tuple[str, str], board: list[str]) -> bool:
    """
    True only when villain's pocket-pair rank actually participates in the
    best 5-card made-hand structure.

    Example: 55 on 6-6-7-7 should not display as Underpair because the
    best hand is board two-pair with a 5 kicker; the pocket pair itself does
    not play. But 88 on K-T-7-6-4 should display as Low Pair because the pair
    is part of the best one-pair hand.
    """
    if hole[0][0] != hole[1][0]:
        return False

    pair_rank = _card_rank(hole[0])
    best_rank = bz.rank_7(list(hole) + board)
    class_idx = int(best_rank[0])

    if class_idx == 1:  # One Pair
        return int(best_rank[1]) == pair_rank
    if class_idx == 2:  # Two Pair
        return pair_rank in {int(best_rank[1]), int(best_rank[2])}
    if class_idx == 3:  # Trips / set
        return int(best_rank[1]) == pair_rank
    if class_idx == 6:  # Full House
        return pair_rank in {int(best_rank[1]), int(best_rank[2])}
    if class_idx == 7:  # Quads
        return int(best_rank[1]) == pair_rank

    return False


def _ui_pair_class(
    hole: tuple[str, str],
    board: list[str],
    made_subgroup: str | None,
) -> str | None:
    """
    User-facing pair hierarchy. This intentionally differs from raw hand class
    on paired boards so the pruning chip matches live-poker language.
    """
    if not board:
        return None

    board_ranks = _unique_board_ranks_desc(board)
    top_rank = board_ranks[0]
    second_rank = board_ranks[1] if len(board_ranks) >= 2 else board_ranks[0]
    lowest_rank = board_ranks[-1]

    r1 = _card_rank(hole[0])
    r2 = _card_rank(hole[1])

    if r1 == r2:
        if not _pocket_pair_rank_plays_in_best_hand(hole, board):
            return None
        pair_rank = r1
        if pair_rank > top_rank:
            return "Overpair"
        if pair_rank >= second_rank and pair_rank < top_rank:
            return "Mid Pair"
        if pair_rank >= lowest_rank:
            return "Low Pair"
        return "Underpair"

    if made_subgroup == "Overpair":
        return "Overpair"
    if made_subgroup == "Top Pair":
        return _top_pair_ui_label(hole, board)
    if made_subgroup not in {"Mid Pair", "Low Pair"}:
        return None

    paired_rank = _paired_rank_from_hole_and_board(hole, board)
    if paired_rank is None:
        return None
    if paired_rank == top_rank:
        return _top_pair_ui_label(hole, board)
    if paired_rank >= second_rank and paired_rank < top_rank:
        return "Mid Pair"
    if paired_rank >= lowest_rank:
        return "Low Pair"
    return None


def _had_meaningful_previous_draw(hole: tuple[str, str], board: list[str]) -> bool:
    if len(board) != 5:
        return False
    for prior_board in (board[:3], board[:4]):
        draws = bz.draw_profile(hole, prior_board)
        if draws["straight_draw"] or draws["gutshot"] or draws["flush_draw"]:
            return True
    return False


def _flush_draw_suit(
    hole: tuple[str, str],
    board: list[str],
    draw_profile: dict[str, bool | int | list[int]],
) -> str | None:
    if not bool(draw_profile.get("flush_draw", False)):
        return None
    suit_counts: dict[str, int] = {}
    for card in list(hole) + board:
        suit_counts[card[1]] = suit_counts.get(card[1], 0) + 1
    for suit, count in suit_counts.items():
        if count == 4:
            return suit
    return None


def _draw_completed_on_runout(
    hole: tuple[str, str],
    original_board: list[str],
    full_board: list[str],
    original_draw_profile: dict[str, bool | int | list[int]],
) -> bool:
    flush_suit = _flush_draw_suit(hole, original_board, original_draw_profile)
    if flush_suit is not None:
        if sum(1 for card in list(hole) + full_board if card[1] == flush_suit) >= 5:
            return True

    if bool(original_draw_profile.get("straight_draw", False)) or bool(original_draw_profile.get("gutshot", False)):
        ranks = bz._ranks_with_ace_low(list(hole) + full_board)
        if bz._straight_high(ranks) is not None:
            return True

    return False


def _pair_draw_equity_components(
    *,
    hole: tuple[str, str],
    board: list[str],
    hero_combos: list[tuple[str, str]],
    draw_profile: dict[str, bool | int | list[int]],
    iters: int,
    seed: int,
) -> tuple[float, float]:
    """
    Split Pair + Draw equity into probability-weighted draw-hit and draw-miss
    contributions. This measures not only how often a draw hits, but whether it
    actually wins/ties/loses against hero's range when it hits.
    """
    if len(board) >= 5:
        return 0.0, 0.0

    board_set = set(board)
    villain_set = set(hole)
    valid_hero = [
        hc for hc in hero_combos if not (set(hc) & board_set) and not (set(hc) & villain_set)
    ]
    if not valid_hero:
        return 0.0, 0.0

    deck = [f"{rank}{suit}" for rank in bz.RANKS for suit in bz.SUITS]
    dead = set(board) | set(hole)
    need = 5 - len(board)
    rng = random.Random(seed)

    draw_hit = 0.0
    draw_miss = 0.0
    total = 0

    for _ in range(max(1, int(iters))):
        hero = rng.choice(valid_hero)
        dead2 = dead | set(hero)
        avail = [card for card in deck if card not in dead2]
        runout = rng.sample(avail, need) if need > 0 else []
        full_board = board + runout

        villain_rank = bz.rank_7(list(hole) + full_board)
        hero_rank = bz.rank_7(list(hero) + full_board)
        contribution = 1.0 if villain_rank > hero_rank else 0.5 if villain_rank == hero_rank else 0.0

        if _draw_completed_on_runout(hole, board, full_board, draw_profile):
            draw_hit += contribution
        else:
            draw_miss += contribution
        total += 1

    if total <= 0:
        return 0.0, 0.0
    return draw_hit / total, draw_miss / total


def _display_subgroup_label(
    *,
    hole: tuple[str, str],
    board: list[str],
    subgroup_label: str,
    best_made_subgroup: str | None,
    draw_profile: dict[str, bool | int | list[int]],
) -> tuple[str, str | None]:
    if _is_board_made_best_hand(hole, board):
        return "Board-Made Hand", "board_best_hand"

    if subgroup_label in {"Full House", "Quads", "Straight Flush"}:
        return "Full House+", None
    if subgroup_label in {"Flush", "Straight", "Trips", "Set", "Two Pair"}:
        return subgroup_label, None

    if subgroup_label == "Pair + Draw":
        pair_class = _ui_pair_class(hole, board, best_made_subgroup)
        if pair_class in STRONG_PAIR_UI_SUBGROUPS:
            return "Strong Pair + Draw", None
        return "Weak Pair + Draw", None

    if subgroup_label in {"Combo Draw", "Flush Draw", "Straight Draw", "Gutshot"}:
        return subgroup_label, None

    pair_class = _ui_pair_class(hole, board, best_made_subgroup or subgroup_label)
    if pair_class is not None:
        return pair_class, None

    has_draw = bool(draw_profile["straight_draw"] or draw_profile["gutshot"] or draw_profile["flush_draw"])
    if len(board) == 5 and not has_draw and _had_meaningful_previous_draw(hole, board):
        return "Missed Draw", None

    if subgroup_label == "High Card" and any(card[0] == "A" for card in hole):
        return "Ace High", None

    return "High Card", None


def _pair_led_bucket_for_pair_draw(
    *,
    display_subgroup_label: str,
    equity_vs_hero: float,
    board: list[str],
) -> str:
    thresholds = bz.equity_thresholds_for_board(board)
    if display_subgroup_label == "Strong Pair + Draw":
        return "Value" if equity_vs_hero >= thresholds["value"] else "SDV"
    return "SDV" if equity_vs_hero >= thresholds["pair_draw_mid_low_sdv"] else "Draw"

def _family_key_from_bucket_label(bucket_label: str) -> str:
    mapping = {
        "Draw": "draw",
        "SDV": "sdv",
        "Value": "value",
        "Nutted Value": "nutted_value",
        "Air": "air",
    }
    return mapping.get(bucket_label, "air")


def _river_family_key_from_bucket_label(bucket_label: str) -> str:
    """
    River engine simplification:
    - Air stays air
    - SDV stays sdv
    - Value + Nutted Value collapse to value
    - Draw also collapses to air on river action logic
    """
    if bucket_label == "SDV":
        return "sdv"
    if bucket_label in {"Value", "Nutted Value"}:
        return "value"
    return "air"


def _draw_strength_score(
    *,
    subgroup_label: str,
    draw_profile: dict[str, bool | int | list[int]],
    equity_vs_hero: float,
    can_make_nutted_draw: bool,
) -> float:
    """
    Coarse 0..1 draw-quality score.

    Intent:
    - very strong pure draws and combo draws grade highest
    - pair+draw is still strong but slightly discounted because it has SDV
      and should raise less than pure strong draws
    - gutshots are clearly weaker
    """
    eq = max(0.0, min(1.0, float(equity_vs_hero)))

    if subgroup_label == "Combo Draw":
        base = 0.92
    elif subgroup_label == "Pair + Draw":
        base = 0.78
    elif subgroup_label in {"Straight Draw", "Flush Draw"}:
        base = 0.70
    elif subgroup_label == "Gutshot":
        base = 0.42
    elif bool(draw_profile.get("double_gutshot", False)):
        base = 0.76
    elif bool(draw_profile.get("straight_draw", False)) or bool(draw_profile.get("flush_draw", False)):
        base = 0.62
    else:
        base = 0.12

    if can_make_nutted_draw:
        base += 0.08

    base += (eq - 0.50) * 0.30
    return max(0.0, min(1.0, base))


def _value_strength_score(
    *,
    subgroup_label: str,
    bucket_label: str,
    equity_vs_hero: float,
    is_nuts: bool,
    is_near_nuts: bool,
    is_ace_high_flush: bool,
) -> float:
    """
    Coarse 0..1 value-strength score used inside Value / Nutted Value families.

    This is intentionally equity-forward rather than purely subgroup-forward.
    """
    eq = max(0.0, min(1.0, float(equity_vs_hero)))

    if bucket_label == "Nutted Value":
        base = 0.90
    elif subgroup_label in {"Straight Flush", "Quads", "Full House"}:
        base = 0.98
    elif subgroup_label in {"Flush", "Straight"}:
        base = 0.86
    elif subgroup_label in {"Set", "Trips"}:
        base = 0.78
    elif subgroup_label == "Two Pair":
        base = 0.72
    elif subgroup_label == "Overpair":
        base = 0.68
    elif subgroup_label == "Top Pair":
        base = 0.58
    elif subgroup_label == "Mid Pair":
        base = 0.46
    elif subgroup_label == "Low Pair":
        base = 0.36
    else:
        base = 0.20

    if is_nuts:
        base = max(base, 1.00)
    elif is_near_nuts:
        base = max(base, 0.92)
    if is_ace_high_flush:
        base = max(base, 0.94)

    base += (eq - 0.50) * 0.40
    return max(0.0, min(1.0, base))


def _vulnerability_score(
    *,
    hole: tuple[str, str],
    board: list[str],
    subgroup_label: str,
    bucket_label: str,
    equity_vs_hero: float,
    is_nuts: bool,
    is_near_nuts: bool,
    is_invulnerable_value: bool,
) -> float:
    """
    Flop/turn-only measure of how vulnerable a made hand is to future cards.

    Key design rules from the villain-action redesign:
    - vulnerability matters mainly for Value / Nutted Value
    - no vulnerability on river because equities are fixed
    - vulnerability is heavily correlated with:
      - board connectivity / wetness
      - how "one-pair-ish" or redraw-light the hand is
      - whether the hand is already invulnerable

    Higher score => more fastplay pressure.
    """
    if len(board) == 5:
        return 0.0

    if bucket_label not in {"Value", "Nutted Value"}:
        return 0.0

    texture = evaluate_board_texture(board)
    eq = max(0.0, min(1.0, float(equity_vs_hero)))

    if subgroup_label in {"Full House", "Quads", "Straight Flush"}:
        base = 0.02
    elif subgroup_label == "Flush":
        base = 0.18
    elif subgroup_label == "Straight":
        base = 0.34
    elif subgroup_label == "Set":
        base = 0.48
    elif subgroup_label == "Trips":
        base = 0.56
    elif subgroup_label == "Two Pair":
        base = 0.60
    elif subgroup_label == "Overpair":
        base = 0.70
    elif subgroup_label == "Top Pair":
        base = 0.76
    elif subgroup_label == "Mid Pair":
        base = 0.74
    elif subgroup_label == "Low Pair":
        base = 0.70
    else:
        base = 0.40

    if texture.wet_connected:
        base += 0.18
    if texture.low_connected:
        base += 0.10
    if texture.flush_draw_present and subgroup_label not in {"Flush", "Straight Flush"}:
        base += 0.10
    if texture.straight_draw_present and subgroup_label not in {"Straight", "Straight Flush"}:
        base += 0.08
    if texture.static_paired or texture.double_paired:
        base -= 0.16
    elif texture.static_unpaired:
        base -= 0.08
    if texture.board_is_monotone:
        base -= 0.06

    if is_invulnerable_value:
        base -= 0.20
    if is_nuts:
        base -= 0.12
    elif is_near_nuts:
        base -= 0.06

    # Higher equity often means stronger current value, but one-pair type hands can
    # still be vulnerable. Use a small moderating effect instead of overriding texture.
    base += (0.62 - eq) * 0.10

    return max(0.0, min(1.0, base))


@lru_cache(maxsize=100_000)
def _bucket_villain_hand_cached(
    hole: tuple[str, str],
    board: tuple[str, ...],
    villain_profile_id: str,
    hero_range_source: str,
    uses_scenario_hero_range: bool,
    hero_combos: tuple[tuple[str, str], ...],
    iters: int,
    seed: int,
) -> VillainHandBucketResult:
    """
    Cached core implementation.
    """
    board_list = list(board)
    hero_combo_list = list(hero_combos)
    rng = random.Random(seed)

    if len(board_list) == 5:
        eq = bz.equity_vs_hero_range_river_exact(hole, board_list, hero_combo_list)
    else:
        eq = bz.equity_vs_hero_range_mc(hole, board_list, hero_combo_list, int(iters), rng)

    bucket_label, subgroup_label = bz.bucket_combo(hole, board_list, eq)

    internal_class = bz.internal_hand_class_of(hole, board_list)
    best_made_subgroup = bz.best_made_subgroup_contributed_by_hole(hole, board_list)

    draw_profile = bz.draw_profile(hole, board_list)
    has_draw = bool(
        draw_profile["straight_draw"]
        or draw_profile["gutshot"]
        or draw_profile["flush_draw"]
    )

    display_subgroup_label, board_made_tag = _display_subgroup_label(
        hole=hole,
        board=board_list,
        subgroup_label=subgroup_label,
        best_made_subgroup=best_made_subgroup,
        draw_profile=draw_profile,
    )
    pair_draw_driver: str | None = None
    draw_hit_contribution: float | None = None
    draw_miss_contribution: float | None = None

    if subgroup_label == "Pair + Draw":
        draw_hit_contribution, draw_miss_contribution = _pair_draw_equity_components(
            hole=hole,
            board=board_list,
            hero_combos=hero_combo_list,
            draw_profile=draw_profile,
            iters=int(iters),
            seed=int(seed) + 7919,
        )
        if draw_hit_contribution >= draw_miss_contribution * 1.15:
            bucket_label = "Draw"
            pair_draw_driver = "draw"
        else:
            bucket_label = _pair_led_bucket_for_pair_draw(
                display_subgroup_label=display_subgroup_label,
                equity_vs_hero=eq,
                board=board_list,
            )
            pair_draw_driver = "pair"

    family_key = _family_key_from_bucket_label(bucket_label)
    river_family_key = _river_family_key_from_bucket_label(bucket_label)

    rank_tier, is_nuts, is_near_nuts = _rank_tier_for_hole(hole, board)
    is_pair_plus_draw = subgroup_label == "Pair + Draw"
    is_made_hand = _is_made_hand(subgroup_label)
    is_strong_draw = _is_strong_draw(subgroup_label, draw_profile)
    is_weak_draw = _is_weak_draw(subgroup_label, draw_profile)
    is_ace_high_flush = _is_ace_high_flush(hole, board_list)
    has_nut_flush_draw = _has_nut_flush_draw(hole, board_list, draw_profile)
    can_make_nutted_draw = _can_make_nutted_draw(hole, board_list, draw_profile)
    is_invulnerable_value = _is_invulnerable_value(
        subgroup_label,
        is_nuts=is_nuts,
        board=board_list,
        hole=hole,
    )
    is_missed_draw_river_air = _is_missed_draw_river_air(hole, board_list, subgroup_label)

    draw_strength = _draw_strength_score(
        subgroup_label=subgroup_label,
        draw_profile=draw_profile,
        equity_vs_hero=eq,
        can_make_nutted_draw=can_make_nutted_draw,
    )
    value_strength = _value_strength_score(
        subgroup_label=subgroup_label,
        bucket_label=bucket_label,
        equity_vs_hero=eq,
        is_nuts=is_nuts,
        is_near_nuts=is_near_nuts,
        is_ace_high_flush=is_ace_high_flush,
    )
    vulnerability = _vulnerability_score(
        hole=hole,
        board=board_list,
        subgroup_label=subgroup_label,
        bucket_label=bucket_label,
        equity_vs_hero=eq,
        is_nuts=is_nuts,
        is_near_nuts=is_near_nuts,
        is_invulnerable_value=is_invulnerable_value,
    )

    street_key = bz.street_name_from_board(board_list)

    return VillainHandBucketResult(
        bucket_label=bucket_label,
        subgroup_label=subgroup_label,
        display_subgroup_label=display_subgroup_label,
        model_subgroup_label=subgroup_label,
        raw_showdown_class=internal_class,
        board_made_tag=board_made_tag,
        pair_draw_driver=pair_draw_driver,
        draw_hit_contribution=draw_hit_contribution,
        draw_miss_contribution=draw_miss_contribution,
        equity_vs_hero=eq,
        user_type=subgroup_label,
        internal_class=internal_class,
        has_draw=has_draw,
        villain_profile_id=villain_profile_id,
        hero_range_source=hero_range_source,
        best_made_subgroup=best_made_subgroup,
        draw_profile=draw_profile,
        is_nuts=is_nuts,
        is_near_nuts=is_near_nuts,
        rank_tier=rank_tier,
        is_made_hand=is_made_hand,
        is_pair_plus_draw=is_pair_plus_draw,
        is_strong_draw=is_strong_draw,
        is_weak_draw=is_weak_draw,
        is_invulnerable_value=is_invulnerable_value,
        is_ace_high_flush=is_ace_high_flush,
        is_missed_draw_river_air=is_missed_draw_river_air,
        street_key=street_key,
        family_key=family_key,
        river_family_key=river_family_key,
        vulnerability=vulnerability,
        draw_strength=draw_strength,
        value_strength=value_strength,
        has_nut_flush_draw=has_nut_flush_draw,
        can_make_nutted_draw=can_make_nutted_draw,
        uses_scenario_hero_range=uses_scenario_hero_range,
    )


def bucket_villain_hand(
    *,
    villain_hand: tuple[str, str] | list[str],
    board: list[str] | tuple[str, ...],
    villain_profile_id: str,
    scenario_hero_range_tokens: Iterable[str] | None = None,
    iters: int | None = None,
    seed: int = 42,
) -> VillainHandBucketResult:
    """
    Bucket villain's exact hidden hand using the same logic as bucketizer.py,
    while exposing richer action-policy signals.

    Equity comparison rule:
    - Erik ("tag") -> scenario hero range when available
    - all other villains -> fixed HERO_RANGE_TOKENS baseline

    Iteration rule:
    - if iters is omitted, fall back to bucketizer.py street defaults via
      bz.resolve_iters(...)
    """
    hole_cards = normalize_cards(list(villain_hand))
    board_cards = normalize_cards(list(board))
    ensure_unique_cards([*hole_cards, *board_cards])

    if len(hole_cards) != 2:
        raise ValueError(f"villain_hand must contain exactly 2 cards, got {len(hole_cards)}")
    if not (3 <= len(board_cards) <= 5):
        raise ValueError(f"board must contain 3 to 5 cards, got {len(board_cards)}")

    hole = tuple(sorted((hole_cards[0], hole_cards[1])))
    hero_combos, hero_range_source, uses_scenario_hero_range = _hero_combos_for_villain(
        villain_profile_id=villain_profile_id,
        scenario_hero_range_tokens=scenario_hero_range_tokens,
    )
    resolved_iters = bz.resolve_iters(board_cards, iters)

    return _bucket_villain_hand_cached(
        hole=hole,
        board=tuple(board_cards),
        villain_profile_id=villain_profile_id,
        hero_range_source=hero_range_source,
        uses_scenario_hero_range=uses_scenario_hero_range,
        hero_combos=hero_combos,
        iters=resolved_iters,
        seed=int(seed),
    )