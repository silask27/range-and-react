# File: api/app/engine/bucketizer.py
# Summary: Self-contained villain range bucketing logic that classifies concrete combos into
# broad buckets + subgroups using hand strength, draw status, and equity versus a fixed
# hero comparison range. Supports standalone manual input of flop/turn/river progression.

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import combinations
from typing import Iterable

RANKS = "23456789TJQKA"
SUITS = "cdhs"

RANK_TO_VALUE: dict[str, int] = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}

INTERNAL_CLASSES: list[str] = [
    "High Card",
    "One Pair",
    "Two Pair",
    "Three of a Kind",
    "Straight",
    "Flush",
    "Full House",
    "Quads",
    "Straight Flush",
]

BUCKETS: list[str] = [
    "Draw",
    "Air",
    "SDV",
    "Value",
    "Nutted Value",
]

SUBGROUPS: list[str] = [
    "High Card",
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
    "Gutshot",
    "Straight Draw",
    "Flush Draw",
    "Combo Draw",
    "Pair + Draw",
]

# Fixed hero comparison range used for all equity calculations.
HERO_RANGE_TOKENS: list[str] = [
    "AA", "AKs", "AQs", "AJs", "ATs", "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
    "AKo", "KK", "KQs", "KJs", "KTs", "K9s", "K8s", "K7s",
    "AQo", "KQo", "QQ", "QJs", "QTs", "Q9s", "Q8s",
    "AJo", "KJo", "QJo", "JJ", "JTs", "J9s",
    "ATo", "KTo", "QTo", "JTo", "TT", "T9s",
    "99", "98s", "97s",
    "88", "87s", "86s",
    "77", "76s", "75s",
    "66", "65s",
    "A5o", "55",
    "44",
    "33",
    "22",
]

NUTTED_SUBGROUPS = {
    "Two Pair",
    "Trips",
    "Set",
    "Straight",
    "Flush",
    "Full House",
    "Quads",
    "Straight Flush",
}

AUTO_ITERS_BY_BOARD_LEN: dict[int, int] = {
    3: 180,  # flop
    4: 110,  # turn
    5: 0,    # river exact
}

BUCKET_STRENGTH_PRIORITY: dict[str, int] = {
    "Air": 0,
    "Draw": 1,
    "SDV": 2,
    "Value": 3,
    "Nutted Value": 4,
}

STREET_EQUITY_THRESHOLDS: dict[str, dict[str, float]] = {
    "flop": {
        "draw_air": 0.10,
        "pair_draw_air": 0.10,
        "air": 0.30,
        "value": 0.65,
        "nutted_value": 0.79,
        "pair_draw_mid_low_sdv": 0.51,
    },
    "turn": {
        "draw_air": 0.18,
        "pair_draw_air": 0.15,
        "air": 0.30,
        "value": 0.65,
        "nutted_value": 0.82,
        "pair_draw_mid_low_sdv": 0.50,
    },
    "river": {
        "draw_air": 0.15,
        "pair_draw_air": 0.15,
        "air": 0.32,
        "value": 0.75,
        "nutted_value": 0.87,
        "pair_draw_mid_low_sdv": 0.48,
    },
}


# =============================================================================
# Standalone exact-label / combo helpers
# =============================================================================

def _rank_sort_key(rank: str) -> int:
    return RANK_TO_VALUE[rank]


def normalize_card(card: str) -> str:
    card = card.strip()
    if len(card) != 2:
        raise ValueError(f"invalid card '{card}'")
    rank = card[0].upper()
    suit = card[1].lower()
    if rank not in RANKS or suit not in SUITS:
        raise ValueError(f"invalid card '{card}'")
    return f"{rank}{suit}"


def normalize_exact_label(label: str) -> str:
    """
    Supports exact labels only:
    - pairs: AA, KK, 77
    - suited: AKs, QJs
    - offsuit: AKo, QTo
    """
    raw = label.strip()
    if not raw:
        raise ValueError("empty range label")

    raw = raw.upper().replace("O", "o").replace("S", "s")
    raw = raw[0].upper() + raw[1:]

    if len(raw) == 2:
        r1, r2 = raw[0], raw[1]
        if r1 not in RANKS or r2 not in RANKS:
            raise ValueError(f"invalid range label '{label}'")
        if r1 != r2:
            raise ValueError(f"non-pair exact label must include 's' or 'o': '{label}'")
        return raw

    if len(raw) == 3:
        r1, r2, suitedness = raw[0], raw[1], raw[2]
        if r1 not in RANKS or r2 not in RANKS:
            raise ValueError(f"invalid range label '{label}'")
        if suitedness not in {"s", "o"}:
            raise ValueError(f"invalid suitedness in label '{label}'")
        if r1 == r2:
            raise ValueError(f"pairs should be written without suitedness: '{label}'")

        ordered = sorted([r1, r2], key=_rank_sort_key, reverse=True)
        return f"{ordered[0]}{ordered[1]}{suitedness}"

    raise ValueError(f"invalid exact label '{label}'")


@lru_cache(maxsize=512)
def _expand_exact_label_to_combos_cached(label: str) -> tuple[tuple[str, str], ...]:
    label = normalize_exact_label(label)

    if len(label) == 2:
        rank = label[0]
        combos_out: list[tuple[str, str]] = []
        for s1, s2 in combinations(SUITS, 2):
            combos_out.append((f"{rank}{s1}", f"{rank}{s2}"))
        return tuple(combos_out)

    r1, r2, suitedness = label[0], label[1], label[2]
    combos_out = []

    if suitedness == "s":
        for s in SUITS:
            combos_out.append((f"{r1}{s}", f"{r2}{s}"))
        return tuple(combos_out)

    for s1 in SUITS:
        for s2 in SUITS:
            if s1 == s2:
                continue
            combos_out.append((f"{r1}{s1}", f"{r2}{s2}"))
    return tuple(combos_out)


def expand_exact_label_to_combos(label: str) -> list[tuple[str, str]]:
    return list(_expand_exact_label_to_combos_cached(normalize_exact_label(label)))


def expand_range_tokens(tokens: Iterable[str]) -> list[str]:
    """
    Exact-label only expansion for standalone use.
    Examples:
    - ["AKs", "77", "QTo"]
    Returns normalized exact labels.
    """
    out: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        normalized = normalize_exact_label(str(token).strip())
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def available_combos_for_labels(
    labels: Iterable[str],
    excluded_cards: Iterable[str] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    excluded = {normalize_card(c) for c in (excluded_cards or [])}
    out: dict[str, list[tuple[str, str]]] = {}

    for label in expand_range_tokens(labels):
        combos = []
        for combo in expand_exact_label_to_combos(label):
            if combo[0] in excluded or combo[1] in excluded:
                continue
            combos.append(combo)
        out[label] = combos

    return out


# =============================================================================
# Hand ranking / best-hand helpers
# =============================================================================

def _straight_high(unique_ranks: set[int]) -> int | None:
    rset = set(unique_ranks)
    if 14 in rset:
        rset.add(1)
    for start in range(10, 0, -1):
        seq = set(range(start, start + 5))
        if seq.issubset(rset):
            return 5 if seq == {1, 2, 3, 4, 5} else (start + 4)
    return None


@lru_cache(maxsize=200000)
def _rank_5_cached(cards5: tuple[str, ...]) -> tuple:
    ranks = sorted([RANK_TO_VALUE[c[0]] for c in cards5], reverse=True)
    suits = [c[1] for c in cards5]
    counts = Counter(ranks)
    items = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    count_vals = sorted(counts.values(), reverse=True)

    is_flush = len(set(suits)) == 1
    sh = _straight_high(set(ranks))
    is_straight = sh is not None

    if is_flush and is_straight:
        return (8, sh)
    if count_vals[0] == 4:
        quad_rank = items[0][0]
        kicker = max(r for r in ranks if r != quad_rank)
        return (7, quad_rank, kicker)
    if count_vals[0] == 3 and count_vals[1] == 2:
        trips = items[0][0]
        pair = items[1][0]
        return (6, trips, pair)
    if is_flush:
        return (5, *ranks)
    if is_straight:
        return (4, sh)
    if count_vals[0] == 3:
        trips = items[0][0]
        kickers = sorted([r for r in ranks if r != trips], reverse=True)
        return (3, trips, *kickers)
    if count_vals[0] == 2 and count_vals[1] == 2:
        pair1 = items[0][0]
        pair2 = items[1][0]
        hi, lo = max(pair1, pair2), min(pair1, pair2)
        kicker = max(r for r in ranks if r not in (pair1, pair2))
        return (2, hi, lo, kicker)
    if count_vals[0] == 2:
        pair = items[0][0]
        kickers = sorted([r for r in ranks if r != pair], reverse=True)
        return (1, pair, *kickers)
    return (0, *ranks)


def rank_5(cards5: tuple[str, ...]) -> tuple:
    return _rank_5_cached(tuple(sorted(cards5)))


@lru_cache(maxsize=200000)
def _rank_7_cached(cards7: tuple[str, ...]) -> tuple:
    best = None
    for five in combinations(cards7, 5):
        r = rank_5(five)
        if best is None or r > best:
            best = r
    return best if best is not None else (0,)


def rank_7(cards7: list[str]) -> tuple:
    return _rank_7_cached(tuple(sorted(cards7)))


@lru_cache(maxsize=200000)
def _best_five_combos_cached(cards7: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    best_rank = _rank_7_cached(cards7)
    out: list[tuple[str, ...]] = []
    for five in combinations(cards7, 5):
        five_sorted = tuple(sorted(five))
        if rank_5(five_sorted) == best_rank:
            out.append(five_sorted)
    return tuple(dict.fromkeys(out))


def best_five_combos(hole: tuple[str, str], board: list[str]) -> list[tuple[str, ...]]:
    cards7 = tuple(sorted(list(hole) + board))
    return list(_best_five_combos_cached(cards7))


def internal_hand_class_of(hole: tuple[str, str], board: list[str]) -> str:
    """
    Contribution-aware internal class for pair-based hands:

    - Only count One Pair if at least one hole card is used to make that pair in the best 5.
    - Only count Two Pair if both hole cards each pair the board and both are part of the
      final two-pair hand in the best 5.
    - If rank_7 sees a raw Two Pair hand but only one hole card meaningfully contributes
      to the pair structure, collapse that to One Pair for internal classification.
    - Only count Three of a Kind if at least one hole card is used to make the trips.

    Otherwise those cases collapse to High Card for internal classification.
    """
    raw_class = INTERNAL_CLASSES[int(rank_7(list(hole) + board)[0])]
    made_subgroup = best_made_subgroup_contributed_by_hole(hole, board)

    if raw_class == "One Pair":
        return (
            "One Pair"
            if made_subgroup in {"Overpair", "Top Pair", "Mid Pair", "Low Pair"}
            else "High Card"
        )

    if raw_class == "Two Pair":
        if made_subgroup == "Two Pair":
            return "Two Pair"
        if made_subgroup in {"Overpair", "Top Pair", "Mid Pair", "Low Pair"}:
            return "One Pair"
        return "High Card"

    if raw_class == "Three of a Kind":
        return "Three of a Kind" if made_subgroup in {"Trips", "Set"} else "High Card"

    return raw_class


def _ranks_with_ace_low(cards: Iterable[str]) -> set[int]:
    ranks = {RANK_TO_VALUE[c[0]] for c in cards}
    if 14 in ranks:
        ranks.add(1)
    return ranks


def board_has_pair(board: list[str]) -> bool:
    board_ranks = [RANK_TO_VALUE[c[0]] for c in board]
    return len(set(board_ranks)) != len(board_ranks)


def is_pocket_pair(hole: tuple[str, str]) -> bool:
    return hole[0][0] == hole[1][0]


def pair_uses_single_hole_card_on_unpaired_board(
    hole: tuple[str, str],
    board: list[str],
) -> bool:
    if board_has_pair(board):
        return False

    r1 = RANK_TO_VALUE[hole[0][0]]
    r2 = RANK_TO_VALUE[hole[1][0]]
    if r1 == r2:
        return False

    board_ranks = {RANK_TO_VALUE[c[0]] for c in board}
    match_count = int(r1 in board_ranks) + int(r2 in board_ranks)
    return match_count == 1


def straight_draw_info(hole: tuple[str, str], board: list[str]) -> dict[str, bool | int | list[int]]:
    """
    Granular straight draw detection.

    - Gutshot: exactly 1 completing rank (4 outs)
    - Straight Draw: 2+ completing ranks (8+ outs), whether OESD or double gutshot
    """
    if len(board) >= 5:
        return {
            "straight_draw": False,
            "gutshot": False,
            "oesd": False,
            "double_gutshot": False,
            "out_ranks": [],
            "out_count": 0,
        }

    ranks = _ranks_with_ace_low(list(hole) + list(board))
    if _straight_high(ranks) is not None:
        return {
            "straight_draw": False,
            "gutshot": False,
            "oesd": False,
            "double_gutshot": False,
            "out_ranks": [],
            "out_count": 0,
        }

    out_ranks: set[int] = set()
    for add_rank in range(2, 15):
        trial = set(ranks)
        trial.add(add_rank)
        if add_rank == 14:
            trial.add(1)
        if _straight_high(trial) is not None:
            out_ranks.add(add_rank)

    has_four_consecutive = False
    for start in range(1, 11):
        if set(range(start, start + 4)).issubset(ranks):
            has_four_consecutive = True
            break

    out_count = len(out_ranks) * 4
    gutshot = len(out_ranks) == 1
    straight_draw = len(out_ranks) >= 2
    oesd = straight_draw and has_four_consecutive
    double_gutshot = straight_draw and not has_four_consecutive

    return {
        "straight_draw": straight_draw,
        "gutshot": gutshot,
        "oesd": oesd,
        "double_gutshot": double_gutshot,
        "out_ranks": sorted(out_ranks),
        "out_count": out_count,
    }


def flush_draw_info(hole: tuple[str, str], board: list[str]) -> dict[str, bool]:
    if len(board) >= 5:
        return {"flush_draw": False, "made_flush": False}

    suits = [c[1] for c in (list(hole) + list(board))]
    suit_counts = Counter(suits)
    made_flush = any(v >= 5 for v in suit_counts.values())
    flush_draw = (not made_flush) and any(v == 4 for v in suit_counts.values())
    return {"flush_draw": flush_draw, "made_flush": made_flush}


def is_top_pair_from_hole(hole: tuple[str, str], board: list[str]) -> bool:
    r1 = RANK_TO_VALUE[hole[0][0]]
    r2 = RANK_TO_VALUE[hole[1][0]]
    if r1 == r2:
        return False
    top_board = max(RANK_TO_VALUE[c[0]] for c in board)
    return (r1 == top_board) or (r2 == top_board)


def is_mid_pair_from_hole(hole: tuple[str, str], board: list[str]) -> bool:
    """
    Mid Pair is:
    1. Traditional second pair, OR
    2. A pocket pair whose rank lies strictly between the top board rank
       and second-highest board rank.

    Example:
    - QJ on A T 7 -> no
    - T9 on A T 7 -> Mid Pair
    - QQ on A T 7 -> Mid Pair
    """
    board_ranks = sorted({RANK_TO_VALUE[c[0]] for c in board}, reverse=True)
    if len(board_ranks) < 2:
        return False

    top_board = board_ranks[0]
    second_board = board_ranks[1]

    r1 = RANK_TO_VALUE[hole[0][0]]
    r2 = RANK_TO_VALUE[hole[1][0]]

    if r1 == r2:
        return second_board < r1 < top_board

    return (r1 == second_board) or (r2 == second_board)


def is_overpair(hole: tuple[str, str], board: list[str]) -> bool:
    r1 = RANK_TO_VALUE[hole[0][0]]
    r2 = RANK_TO_VALUE[hole[1][0]]
    if r1 != r2:
        return False
    top_board = max(RANK_TO_VALUE[c[0]] for c in board)
    return r1 > top_board


def _one_pair_subgroup(hole: tuple[str, str], board: list[str]) -> str:
    if is_overpair(hole, board):
        return "Overpair"
    if is_top_pair_from_hole(hole, board):
        return "Top Pair"
    if is_mid_pair_from_hole(hole, board):
        return "Mid Pair"
    return "Low Pair"


def draw_profile(hole: tuple[str, str], board: list[str]) -> dict[str, bool | int | list[int]]:
    straight_info = straight_draw_info(hole, board)
    flush_info = flush_draw_info(hole, board)
    return {
        "straight_draw": bool(straight_info["straight_draw"]),
        "gutshot": bool(straight_info["gutshot"]),
        "oesd": bool(straight_info["oesd"]),
        "double_gutshot": bool(straight_info["double_gutshot"]),
        "straight_out_ranks": list(straight_info["out_ranks"]),
        "straight_out_count": int(straight_info["out_count"]),
        "flush_draw": bool(flush_info["flush_draw"]),
    }


# =============================================================================
# Best-hand contribution-aware subgroup logic
# =============================================================================

def _made_subgroup_from_best_five(
    hole: tuple[str, str],
    board: list[str],
    best_five: tuple[str, ...],
    best_rank: tuple,
) -> str | None:
    """
    Return the made-hand subgroup only if the best 5-card hand uses at least one hole card
    to create that made-hand structure.

    Two-pair rule:
    - Count as Two Pair only when both hole cards each pair the board and both are part
      of the final two-pair hand in the best 5.
    - If a raw two-pair hand is actually "board pair + one hole-card pair" or
      "board pair + pocket pair", collapse it back into the appropriate one-pair subgroup.
    """
    hole_set = set(hole)
    hole_in_best = [c for c in best_five if c in hole_set]
    if not hole_in_best:
        return None

    class_idx = int(best_rank[0])

    if class_idx == 8:
        return "Straight Flush"

    if class_idx == 7:
        quad_rank = best_rank[1]
        if any(RANK_TO_VALUE[c[0]] == quad_rank for c in hole_in_best):
            return "Quads"
        return None

    if class_idx == 6:
        trips_rank = best_rank[1]
        pair_rank = best_rank[2]
        if any(RANK_TO_VALUE[c[0]] in {trips_rank, pair_rank} for c in hole_in_best):
            return "Full House"
        return None

    if class_idx == 5:
        return "Flush"

    if class_idx == 4:
        return "Straight"

    if class_idx == 3:
        trips_rank = best_rank[1]
        trip_hole_cards = [c for c in hole_in_best if RANK_TO_VALUE[c[0]] == trips_rank]
        if not trip_hole_cards:
            return None

        r1 = RANK_TO_VALUE[hole[0][0]]
        r2 = RANK_TO_VALUE[hole[1][0]]
        if r1 == r2 == trips_rank:
            return "Set"
        return "Trips"

    if class_idx == 2:
        pair_ranks = {best_rank[1], best_rank[2]}
        board_ranks = {RANK_TO_VALUE[c[0]] for c in board}
        hole_ranks_in_best = [RANK_TO_VALUE[c[0]] for c in hole_in_best]

        if (
            len(hole_in_best) == 2
            and hole_ranks_in_best[0] != hole_ranks_in_best[1]
            and set(hole_ranks_in_best) == pair_ranks
            and pair_ranks.issubset(board_ranks)
        ):
            return "Two Pair"

        if any(rank in pair_ranks for rank in hole_ranks_in_best):
            return _one_pair_subgroup(hole, board)
        return None

    if class_idx == 1:
        pair_rank = best_rank[1]
        if any(RANK_TO_VALUE[c[0]] == pair_rank for c in hole_in_best):
            return _one_pair_subgroup(hole, board)
        return None

    return None


def best_made_subgroup_contributed_by_hole(
    hole: tuple[str, str],
    board: list[str],
) -> str | None:
    cards7 = tuple(sorted(list(hole) + board))
    best_rank = _rank_7_cached(cards7)

    candidates: list[str] = []
    for best_five in _best_five_combos_cached(cards7):
        subgroup = _made_subgroup_from_best_five(hole, board, best_five, best_rank)
        if subgroup is not None:
            candidates.append(subgroup)

    if not candidates:
        return None

    priority = {
        "Straight Flush": 0,
        "Quads": 1,
        "Full House": 2,
        "Flush": 3,
        "Straight": 4,
        "Set": 5,
        "Trips": 6,
        "Two Pair": 7,
        "Overpair": 8,
        "Top Pair": 9,
        "Mid Pair": 10,
        "Low Pair": 11,
    }
    return sorted(candidates, key=lambda s: priority.get(s, 999))[0]


# =============================================================================
# Equity helpers
# =============================================================================

def expand_range_to_combos(labels: Iterable[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for label in labels:
        out.extend(expand_exact_label_to_combos(label))
    return list(dict.fromkeys(out))


def _hero_comparison_labels() -> list[str]:
    return list(HERO_RANGE_TOKENS)


def resolve_iters(board: list[str], iters: int | None) -> int:
    if iters is not None:
        return max(1, int(iters))
    return AUTO_ITERS_BY_BOARD_LEN[len(board)]


def street_name_from_board(board: list[str]) -> str:
    if len(board) == 3:
        return "flop"
    if len(board) == 4:
        return "turn"
    if len(board) == 5:
        return "river"
    raise ValueError("board must contain 3, 4, or 5 cards")


def equity_thresholds_for_board(board: list[str]) -> dict[str, float]:
    return STREET_EQUITY_THRESHOLDS[street_name_from_board(board)]


def equity_vs_hero_range_mc(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_combos: list[tuple[str, str]],
    iters: int,
    rng: random.Random,
) -> float:
    board_set = set(board)
    villain_set = set(villain_hole)

    valid_hero = [
        hc for hc in hero_combos if not (set(hc) & board_set) and not (set(hc) & villain_set)
    ]
    if not valid_hero:
        return 0.0

    deck = [f"{rank}{suit}" for rank in RANKS for suit in SUITS]
    dead = set(board) | set(villain_hole)
    need = 5 - len(board)

    wins = ties = total = 0

    for _ in range(iters):
        hero = rng.choice(valid_hero)
        dead2 = dead | set(hero)
        avail = [c for c in deck if c not in dead2]
        runout = rng.sample(avail, need) if need > 0 else []
        full_board = board + runout

        villain_rank = rank_7(list(villain_hole) + full_board)
        hero_rank = rank_7(list(hero) + full_board)

        total += 1
        if villain_rank > hero_rank:
            wins += 1
        elif villain_rank == hero_rank:
            ties += 1

    return (wins + 0.5 * ties) / total if total else 0.0


def equity_vs_hero_range_river_exact(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_combos: list[tuple[str, str]],
) -> float:
    board_set = set(board)
    villain_set = set(villain_hole)

    valid_hero = [
        hc for hc in hero_combos if not (set(hc) & board_set) and not (set(hc) & villain_set)
    ]
    if not valid_hero:
        return 0.0

    villain_rank = rank_7(list(villain_hole) + board)
    wins = ties = total = 0

    for hero in valid_hero:
        hero_rank = rank_7(list(hero) + board)
        total += 1
        if villain_rank > hero_rank:
            wins += 1
        elif villain_rank == hero_rank:
            ties += 1

    return (wins + 0.5 * ties) / total if total else 0.0


# =============================================================================
# Subgroup + broad bucket logic
# =============================================================================

def subgroup_of(hole: tuple[str, str], board: list[str]) -> str:
    draws = draw_profile(hole, board)
    has_draw = bool(draws["straight_draw"] or draws["gutshot"] or draws["flush_draw"])
    made_subgroup = best_made_subgroup_contributed_by_hole(hole, board)

    # Blanket override:
    # any contributed 1-pair or 2-pair hand with a draw becomes Pair + Draw.
    if (
        len(board) < 5
        and has_draw
        and made_subgroup in {"Overpair", "Top Pair", "Mid Pair", "Low Pair", "Two Pair"}
    ):
        return "Pair + Draw"

    if made_subgroup is not None:
        return made_subgroup

    if len(board) < 5:
        has_straight_draw = bool(draws["straight_draw"])
        has_gutshot = bool(draws["gutshot"])
        has_flush_draw = bool(draws["flush_draw"])

        if has_flush_draw and (has_straight_draw or has_gutshot):
            return "Combo Draw"
        if has_flush_draw:
            return "Flush Draw"
        if has_straight_draw:
            return "Straight Draw"
        if has_gutshot:
            return "Gutshot"

    return "High Card"


def broad_bucket_for_subgroup(
    hole: tuple[str, str],
    board: list[str],
    subgroup: str,
    eq_vs_hero: float,
) -> str:
    thresholds = equity_thresholds_for_board(board)

    if subgroup in {"Gutshot", "Straight Draw", "Flush Draw", "Combo Draw"}:
        return "Air" if eq_vs_hero < thresholds["draw_air"] else "Draw"

    if subgroup == "Pair + Draw":
        if eq_vs_hero < thresholds["pair_draw_air"]:
            return "Air"

        base_pair = best_made_subgroup_contributed_by_hole(hole, board)

        if base_pair in {"Two Pair", "Overpair", "Top Pair"}:
            return "Value" if eq_vs_hero >= thresholds["value"] else "SDV"

        if base_pair in {"Mid Pair", "Low Pair"}:
            return "SDV" if eq_vs_hero >= thresholds["pair_draw_mid_low_sdv"] else "Draw"

        return "Draw"

    if eq_vs_hero < thresholds["air"]:
        return "Air"

    if subgroup == "High Card":
        return "SDV"

    if subgroup == "Overpair":
        return "Value" if eq_vs_hero >= thresholds["value"] else "SDV"

    if subgroup == "Top Pair":
        return "Value" if eq_vs_hero >= thresholds["value"] else "SDV"

    if subgroup == "Mid Pair":
        return "SDV"

    if subgroup == "Low Pair":
        return "SDV"

    if subgroup in NUTTED_SUBGROUPS:
        if eq_vs_hero >= thresholds["nutted_value"]:
            return "Nutted Value"
        if eq_vs_hero >= thresholds["value"]:
            return "Value"
        return "SDV"

    return "SDV"


def bucket_combo(
    hole: tuple[str, str],
    board: list[str],
    eq_vs_hero: float,
) -> tuple[str, str]:
    subgroup = subgroup_of(hole, board)
    broad_bucket = broad_bucket_for_subgroup(hole, board, subgroup, eq_vs_hero)
    return broad_bucket, subgroup


def _resolve_bucket_for_label_subgroup(records: list[dict]) -> str:
    """
    Keep all combos of the same exact label in the same subgroup under one broad bucket.

    Resolution:
    1. Majority broad bucket by combo count.
    2. If tied, use higher average equity among the tied buckets.
    3. If still tied, prefer the stronger bucket deterministically.
    """
    if not records:
        raise ValueError("cannot resolve bucket for empty record group")

    bucket_counts = Counter(record["initial_broad_bucket"] for record in records)
    max_count = max(bucket_counts.values())
    contenders = [bucket for bucket, count in bucket_counts.items() if count == max_count]

    if len(contenders) == 1:
        return contenders[0]

    avg_eq_by_bucket: dict[str, float] = {}
    for bucket in contenders:
        equities = [
            float(record["equity_vs_hero"])
            for record in records
            if record["initial_broad_bucket"] == bucket
        ]
        avg_eq_by_bucket[bucket] = sum(equities) / len(equities)

    best_avg_eq = max(avg_eq_by_bucket.values())
    contenders = [
        bucket for bucket in contenders
        if abs(avg_eq_by_bucket[bucket] - best_avg_eq) < 1e-12
    ]

    if len(contenders) == 1:
        return contenders[0]

    return max(contenders, key=lambda bucket: BUCKET_STRENGTH_PRIORITY.get(bucket, -1))


# =============================================================================
# Parsing + board progression helpers
# =============================================================================

def parse_range_string(range_text: str | Iterable[str]) -> list[str]:
    if isinstance(range_text, str):
        raw_tokens = [tok.strip() for tok in re.split(r"[\s,]+", range_text) if tok.strip()]
    else:
        raw_tokens = [str(tok).strip() for tok in range_text if str(tok).strip()]

    if not raw_tokens:
        return []

    return expand_range_tokens(raw_tokens)


def parse_board_string(board_text: str | Iterable[str]) -> list[str]:
    if isinstance(board_text, str):
        cards = [tok.strip() for tok in re.split(r"[\s,]+", board_text) if tok.strip()]
    else:
        cards = [str(tok).strip() for tok in board_text if str(tok).strip()]

    board = [normalize_card(card) for card in cards]
    if len(board) not in {3, 4, 5}:
        raise ValueError("board must contain 3, 4, or 5 cards")
    if len(set(board)) != len(board):
        raise ValueError("board contains duplicate cards")
    return board


def append_board_card(board: list[str], new_card: str) -> list[str]:
    card = normalize_card(new_card)
    if card in board:
        raise ValueError(f"card '{card}' is already on the board")
    if len(board) >= 5:
        raise ValueError("board already has 5 cards")
    return list(board) + [card]


def build_board(
    flop_text: str | Iterable[str],
    turn_card: str | None = None,
    river_card: str | None = None,
) -> list[str]:
    board = parse_board_string(flop_text)
    if len(board) != 3:
        raise ValueError("flop must contain exactly 3 cards")

    if turn_card:
        board = append_board_card(board, turn_card)
    if river_card:
        board = append_board_card(board, river_card)

    return board


# =============================================================================
# Analysis
# =============================================================================

def analyze_range(
    villain_labels: Iterable[str],
    board: list[str],
    villain_profile_id: str | None = None,
    scenario_hero_range_tokens: Iterable[str] | None = None,
    iters: int | None = None,
    rng: random.Random | None = None,
) -> dict:
    """
    Bucket a live villain range on the current board into:

    Broad Bucket -> Subgroup -> Hand label + live combos / total combos

    Compatibility notes:
    - villain_profile_id and scenario_hero_range_tokens are accepted but ignored.
    - All equity comparisons use the fixed HERO_RANGE_TOKENS baseline.
    """
    input_villain_profile_id = villain_profile_id
    del scenario_hero_range_tokens

    rng = rng or random.Random(42)
    run_iters = resolve_iters(board, iters)

    hero_labels = _hero_comparison_labels()
    hero_combos = expand_range_to_combos(hero_labels)
    normalized_villain_labels = parse_range_string(villain_labels)
    available = available_combos_for_labels(normalized_villain_labels, excluded_cards=board)

    combo_records: list[tuple[str, tuple[str, str]]] = []
    label_combo_total: dict[str, int] = {}
    for label, combos in available.items():
        if combos:
            label_combo_total[label] = len(combos)
            for combo in combos:
                combo_records.append((label, combo))

    evaluated_records: list[dict] = []

    for label, hole in combo_records:
        if len(board) == 5:
            eq = equity_vs_hero_range_river_exact(hole, board, hero_combos)
        else:
            eq = equity_vs_hero_range_mc(hole, board, hero_combos, run_iters, rng)

        initial_broad_bucket, subgroup = bucket_combo(hole, board, eq)
        internal_name = internal_hand_class_of(hole, board)
        best_made_subgroup = best_made_subgroup_contributed_by_hole(hole, board)

        evaluated_records.append(
            {
                "label": label,
                "combo": hole,
                "equity_vs_hero": eq,
                "subgroup": subgroup,
                "initial_broad_bucket": initial_broad_bucket,
                "broad_bucket": initial_broad_bucket,
                "internal_type": internal_name,
                "draw_profile": draw_profile(hole, board),
                "best_made_subgroup": best_made_subgroup,
                "best_five_combos": [list(f) for f in best_five_combos(hole, board)],
            }
        )

    records_by_label_and_subgroup: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in evaluated_records:
        records_by_label_and_subgroup[(record["label"], record["subgroup"])].append(record)

    for records in records_by_label_and_subgroup.values():
        resolved_bucket = _resolve_bucket_for_label_subgroup(records)
        for record in records:
            record["broad_bucket"] = resolved_bucket

    bucket_combo_counts: Counter[str] = Counter()
    subgroup_combo_counts: Counter[str] = Counter()
    bucket_subgroup_combo_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_internal_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_equities: dict[str, list[float]] = defaultdict(list)
    subgroup_equities: dict[str, list[float]] = defaultdict(list)
    label_bucket_subgroup_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    bucket_combo_details: dict[str, list[dict]] = defaultdict(list)

    for record in evaluated_records:
        label = record["label"]
        hole = record["combo"]
        broad_bucket = record["broad_bucket"]
        subgroup = record["subgroup"]
        internal_name = record["internal_type"]
        eq = float(record["equity_vs_hero"])

        bucket_combo_counts[broad_bucket] += 1
        subgroup_combo_counts[subgroup] += 1
        bucket_subgroup_combo_counts[broad_bucket][subgroup] += 1
        bucket_internal_counts[broad_bucket][internal_name] += 1
        bucket_equities[broad_bucket].append(eq)
        subgroup_equities[subgroup].append(eq)
        label_bucket_subgroup_counts[(broad_bucket, subgroup)][label] += 1
        bucket_combo_details[broad_bucket].append(
            {
                "label": label,
                "combo": list(hole),
                "equity_vs_hero": eq,
                "broad_bucket": broad_bucket,
                "initial_broad_bucket": record["initial_broad_bucket"],
                "subgroup": subgroup,
                "internal_type": internal_name,
                "draw_profile": record["draw_profile"],
                "best_made_subgroup": record["best_made_subgroup"],
                "best_five_combos": record["best_five_combos"],
            }
        )

    total = sum(bucket_combo_counts.values())

    bucket_subgroups: dict[str, dict[str, dict]] = {}
    for broad_bucket in BUCKETS:
        subgroup_map: dict[str, dict] = {}
        subgroup_counts = bucket_subgroup_combo_counts.get(broad_bucket, Counter())

        for subgroup in SUBGROUPS:
            combo_count = subgroup_counts.get(subgroup, 0)
            if combo_count <= 0:
                continue

            label_counts = label_bucket_subgroup_counts.get((broad_bucket, subgroup), Counter())
            labels = [
                {
                    "label": label,
                    "live_combos": live_combo_count,
                    "total_combos": label_combo_total.get(label, 0),
                }
                for label, live_combo_count in sorted(
                    label_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ]

            avg_equity = (
                sum(
                    detail["equity_vs_hero"]
                    for detail in bucket_combo_details[broad_bucket]
                    if detail["subgroup"] == subgroup
                )
                / combo_count
            )

            subgroup_map[subgroup] = {
                "combo_count": combo_count,
                "labels": labels,
                "avg_equity_vs_hero": avg_equity,
            }

        if subgroup_map:
            bucket_subgroups[broad_bucket] = subgroup_map

    return {
        "board": list(board),
        "iters": run_iters,
        "villain_profile_id": input_villain_profile_id,
        "hero_range_source": "fixed",
        "hero_comparison_labels": list(hero_labels),
        "total_combos": total,
        "bucket_combo_counts": dict(bucket_combo_counts),
        "subgroup_combo_counts": dict(subgroup_combo_counts),
        "bucket_subgroup_combo_counts": {
            bucket: dict(counter) for bucket, counter in bucket_subgroup_combo_counts.items()
        },
        "bucket_internal_counts": {k: dict(v) for k, v in bucket_internal_counts.items()},
        "bucket_equities": {k: list(v) for k, v in bucket_equities.items()},
        "subgroup_equities": {k: list(v) for k, v in subgroup_equities.items()},
        "bucket_subgroups": bucket_subgroups,
        "bucket_combo_details": dict(bucket_combo_details),
        "label_combo_total": dict(label_combo_total),
    }


def analyze_range_from_text(
    villain_range_text: str,
    board_text: str,
    iters: int | None = None,
    rng: random.Random | None = None,
) -> dict:
    villain_labels = parse_range_string(villain_range_text)
    board = parse_board_string(board_text)
    return analyze_range(villain_labels=villain_labels, board=board, iters=iters, rng=rng)


def analyze_range_progression(
    villain_range_text: str,
    flop_text: str,
    turn_card: str | None = None,
    river_card: str | None = None,
    iters: int | None = None,
    rng: random.Random | None = None,
) -> dict[str, dict]:
    villain_labels = parse_range_string(villain_range_text)
    flop = build_board(flop_text)
    out: dict[str, dict] = {
        "flop": analyze_range(villain_labels=villain_labels, board=flop, iters=iters, rng=rng)
    }

    if turn_card:
        turn_board = append_board_card(flop, turn_card)
        out["turn"] = analyze_range(
            villain_labels=villain_labels,
            board=turn_board,
            iters=iters,
            rng=rng,
        )

        if river_card:
            river_board = append_board_card(turn_board, river_card)
            out["river"] = analyze_range(
                villain_labels=villain_labels,
                board=river_board,
                iters=iters,
                rng=rng,
            )

    return out


# =============================================================================
# Reporting
# =============================================================================

def format_bucket_report(result: dict) -> str:
    lines: list[str] = []
    board_text = " ".join(result["board"])
    lines.append(f"Board: {board_text}")
    lines.append(f"Total live combos: {result['total_combos']}")
    lines.append(
        f"Equity iterations used: {result['iters']}"
        if len(result["board"]) < 5
        else "Equity method: exact river"
    )
    lines.append("")

    bucket_subgroups = result.get("bucket_subgroups", {})
    for broad_bucket in BUCKETS:
        subgroup_map = bucket_subgroups.get(broad_bucket)
        if not subgroup_map:
            continue

        bucket_count = result.get("bucket_combo_counts", {}).get(broad_bucket, 0)
        lines.append(f"{broad_bucket} ({bucket_count})")

        for subgroup in SUBGROUPS:
            subgroup_data = subgroup_map.get(subgroup)
            if not subgroup_data:
                continue

            lines.append(f"  {subgroup} ({subgroup_data['combo_count']})")
            for label_info in subgroup_data["labels"]:
                lines.append(
                    f"    {label_info['label']} "
                    f"{label_info['live_combos']}/{label_info['total_combos']}"
                )

        lines.append("")

    return "\n".join(lines).rstrip()


# =============================================================================
# Standalone CLI
# =============================================================================

if __name__ == "__main__":
    villain_range_text = input(
        "Villain range (e.g. AKs, AKo, KK, AA, TT, 77): "
    ).strip()

    flop_text = input("Flop (3 cards, e.g. Ah Kc 7h): ").strip()
    flop_board = build_board(flop_text)

    print("\n=== FLOP ===")
    flop_result = analyze_range(
        villain_labels=parse_range_string(villain_range_text),
        board=flop_board,
    )
    print(format_bucket_report(flop_result))

    turn_card = input("\nTurn card (optional, press Enter to skip): ").strip()
    if turn_card:
        turn_board = append_board_card(flop_board, turn_card)

        print("\n=== TURN ===")
        turn_result = analyze_range(
            villain_labels=parse_range_string(villain_range_text),
            board=turn_board,
        )
        print(format_bucket_report(turn_result))

        river_card = input("\nRiver card (optional, press Enter to skip): ").strip()
        if river_card:
            river_board = append_board_card(turn_board, river_card)

            print("\n=== RIVER ===")
            river_result = analyze_range(
                villain_labels=parse_range_string(villain_range_text),
                board=river_board,
            )
            print(format_bucket_report(river_result))