# File: api/app/engine/bucketizer.py
# Summary: Self-contained villain range bucketing logic that classifies concrete combos into
# broad buckets + subgroups using hand strength, draw status, and equity versus a
# villain-specific hybrid of scenario hero ranges from catalog.py and a fixed fallback range.
# Supports standalone manual input of flop/turn/river progression.

from __future__ import annotations

import argparse
import ast
import hashlib
import random
import re
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import combinations
from pathlib import Path
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
VALUE_TO_RANK: dict[int, str] = {value: rank for rank, value in RANK_TO_VALUE.items()}

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
    "Weak Pair + Draw",
    "SDV + Draw",
    "Value + Draw",
]

PAIR_DRAW_BASE_SUBGROUPS = {"Overpair", "Top Pair", "Mid Pair", "Low Pair"}
PAIR_DRAW_TYPES = {"Straight Draw", "Flush Draw", "Combo Draw"}
PAIR_DRAW_SUBGROUPS = {
    f"{base_pair} + {draw_type}"
    for base_pair in PAIR_DRAW_BASE_SUBGROUPS
    for draw_type in PAIR_DRAW_TYPES
}

# Fixed fallback hero comparison range used as the non-scenario component in v7.
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

DEFAULT_CATALOG_PATH = str(Path(__file__).resolve().parents[1] / "data" / "catalog.py")

VILLAIN_SCENARIO_WEIGHTS: dict[str, float] = {
    "erik": 0.95,
    "alex": 0.85,
    "blake": 0.80,
    "dave": 0.70,
    "mike": 0.70,
    "steve": 0.65,
    "tom": 0.65,
}

VILLAIN_PROFILE_ALIASES: dict[str, str] = {
    "erik": "erik",
    "tag": "erik",
    "blake": "blake",
    "loose_reg": "blake",
    "alex": "alex",
    "abc_fit_fold": "alex",
    "dave": "dave",
    "chaser": "dave",
    "steve": "steve",
    "maniac": "steve",
    "mike": "mike",
    "weak_tight": "mike",
    "tom": "tom",
    "calling_station": "tom",
}

VILLAIN_DISPLAY_NAMES: dict[str, str] = {
    "erik": "Erik",
    "blake": "Blake",
    "alex": "Alex",
    "dave": "Dave",
    "steve": "Steve",
    "mike": "Mike",
    "tom": "Tom",
}

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
    3: 500,  # flop
    4: 400,  # turn
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
        "air": 0.23,
        "value": 0.74,
        "nutted_value": 0.90,
    },
    "turn": {
        "air": 0.23,
        "value": 0.75,
        "nutted_value": 0.90,
    },
    "river": {
        "air": 0.20,
        "value": 0.74,
        "nutted_value": 0.90,
    },
}

RANGE_COMPRESSION_THRESHOLD_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "flop": {
        "air": 0.015,
        "value": 0.03,
        "nutted_value": 0.02,
    },
    "turn": {
        "air": 0.02,
        "value": 0.05,
        "nutted_value": 0.02,
    },
    "river": {
        "air": 0.015,
        "value": 0.03,
        "nutted_value": 0.02,
    },
}


RANGE_COMPRESSION_THRESHOLD_FLOORS: dict[str, dict[str, float]] = {
    "flop": {
        "air": 0.22,
        "value": 0.66,
        "nutted_value": 0.875,
    },
    "turn": {
        "air": 0.195,
        "value": 0.68,
        "nutted_value": 0.89,
    },
    "river": {
        "air": 0.17,
        "value": 0.69,
        "nutted_value": 0.875,
    },
}

TURN_HIGH_CARD_CURRENT_SCORE_WEIGHT = 1.00
TURN_HIGH_CARD_EQUITY_WEIGHT = 0.00

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


@lru_cache(maxsize=50000)
def _best_possible_rank_for_board_cached(board_tuple: tuple[str, ...]) -> tuple:
    """Return the theoretical nut hand rank for the current board.

    This enumerates every possible two-card holding that does not conflict with
    the board and finds the highest 7-card rank available. Hands that tie this
    rank are treated as the best possible hand on that board.
    """
    board = list(board_tuple)
    board_set = set(board)
    deck = [f"{rank}{suit}" for rank in RANKS for suit in SUITS]
    available_cards = [card for card in deck if card not in board_set]

    best_rank = None
    for hole in combinations(available_cards, 2):
        hand_rank = rank_7(list(hole) + board)
        if best_rank is None or hand_rank > best_rank:
            best_rank = hand_rank

    return best_rank if best_rank is not None else (0,)


def best_possible_rank_for_board(board: list[str]) -> tuple:
    return _best_possible_rank_for_board_cached(tuple(sorted(board)))


def is_best_possible_hand(hole: tuple[str, str], board: list[str]) -> bool:
    """True when this concrete combo ties the theoretical nut rank."""
    return rank_7(list(hole) + board) == best_possible_rank_for_board(board)


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


def paired_board_ranks(board: list[str]) -> set[int]:
    board_rank_counts = Counter(RANK_TO_VALUE[c[0]] for c in board)
    return {rank for rank, count in board_rank_counts.items() if count >= 2}


def qualifies_as_user_two_pair(
    board: list[str],
    pair_ranks: set[int],
    hole_ranks_in_best: list[int],
) -> bool:
    """Return True when the hand should be displayed as user-made Two Pair."""
    if len(hole_ranks_in_best) != 2:
        return False
    if hole_ranks_in_best[0] == hole_ranks_in_best[1]:
        return False
    if set(hole_ranks_in_best) != pair_ranks:
        return False

    board_ranks = {RANK_TO_VALUE[c[0]] for c in board}
    if not pair_ranks.issubset(board_ranks):
        return False

    board_pair_ranks = paired_board_ranks(board)
    if not board_pair_ranks:
        return True

    top_board_rank = max(board_ranks)
    if top_board_rank not in pair_ranks:
        return False

    non_top_pair_ranks = pair_ranks - {top_board_rank}
    if not non_top_pair_ranks:
        return False

    highest_board_pair_rank = max(board_pair_ranks)
    return max(non_top_pair_ranks) > highest_board_pair_rank


def _empty_straight_draw_info() -> dict[str, bool | int | list[int]]:
    return {
        "straight_draw": False,
        "gutshot": False,
        "oesd": False,
        "double_gutshot": False,
        "out_ranks": [],
        "out_count": 0,
    }


def straight_draw_info(hole: tuple[str, str], board: list[str]) -> dict[str, bool | int | list[int]]:
    """
    Granular, hole-card-aware straight draw detection.

    Important distinction:
    - We count a straight draw only when the hole cards create or improve the draw.
    - We do NOT count board-only runout draws that every hand shares.

    Example:
    - Board J T 9 8: a river Q or 7 can complete a board straight for everyone.
      AA/66/44/33 should not be Pair + Draw just because of that board-only runout.
    - Kx on J T 9 8 does have a Q gutshot because Q makes K-Q-J-T-9, a better
      straight than the board-only Q-J-T-9-8 straight.
    """
    if len(board) >= 5:
        return _empty_straight_draw_info()

    board_ranks = _ranks_with_ace_low(board)
    combined_ranks = _ranks_with_ace_low(list(hole) + list(board))

    # Already-made straights are made hands, not draws.
    if _straight_high(combined_ranks) is not None:
        return _empty_straight_draw_info()

    out_ranks: set[int] = set()
    for add_rank in range(2, 15):
        trial_combined = set(combined_ranks)
        trial_combined.add(add_rank)
        if add_rank == 14:
            trial_combined.add(1)

        combined_high = _straight_high(trial_combined)
        if combined_high is None:
            continue

        trial_board = set(board_ranks)
        trial_board.add(add_rank)
        if add_rank == 14:
            trial_board.add(1)

        board_only_high = _straight_high(trial_board)

        # Count the out only if the villain's hole cards matter. If the same river
        # rank merely creates an equal-or-better board straight, it is a board-only
        # runout and should not turn every pair into Pair + Draw.
        if board_only_high is None or combined_high > board_only_high:
            out_ranks.add(add_rank)

    out_count = len(out_ranks) * 4
    gutshot = len(out_ranks) == 1
    straight_draw = len(out_ranks) >= 2

    # OESD/double-gutshot labels remain approximate, but now based only on
    # hole-card-relevant outs. The bucketizer primarily uses gutshot vs 2+ outs.
    has_four_consecutive = False
    for start in range(1, 11):
        seq4 = set(range(start, start + 4))
        if seq4.issubset(combined_ranks) and not seq4.issubset(board_ranks):
            has_four_consecutive = True
            break

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
    """
    Hole-card-aware flush draw detection.

    We do not count board-only four-flush runouts as a villain flush draw.
    A flush draw requires at least one hole card of the draw suit.
    """
    if len(board) >= 5:
        return {"flush_draw": False, "made_flush": False}

    all_cards = list(hole) + list(board)
    suit_counts = Counter(c[1] for c in all_cards)
    made_flush = any(v >= 5 for v in suit_counts.values())
    if made_flush:
        return {"flush_draw": False, "made_flush": True}

    flush_draw = False
    for suit, total_count in suit_counts.items():
        if total_count != 4:
            continue
        hole_count = sum(1 for card in hole if card[1] == suit)
        if hole_count > 0:
            flush_draw = True
            break

    return {"flush_draw": flush_draw, "made_flush": False}


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
    1. Any non-top, non-bottom board pair made with a hole card, OR
    2. A pocket pair whose rank lies strictly between the top and bottom
       board ranks.

    Example:
    - QJ on A T 7 -> no
    - T9 on A T 7 -> Mid Pair
    - 99 on A T 7 -> Mid Pair
    - QQ on A T 7 -> Mid Pair
    """
    board_ranks = sorted({RANK_TO_VALUE[c[0]] for c in board}, reverse=True)
    if len(board_ranks) < 2:
        return False

    top_board = board_ranks[0]
    bottom_board = board_ranks[-1]

    r1 = RANK_TO_VALUE[hole[0][0]]
    r2 = RANK_TO_VALUE[hole[1][0]]

    if r1 == r2:
        return bottom_board < r1 < top_board

    return any(bottom_board < rank < top_board for rank in (r1, r2) if rank in board_ranks)


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


def _rank_has_available_card(rank_value: int, dead_cards: Iterable[str]) -> bool:
    rank = VALUE_TO_RANK[rank_value]
    dead = set(dead_cards)
    return any(f"{rank}{suit}" not in dead for suit in SUITS)


def _available_card_for_rank(rank_value: int, dead_cards: Iterable[str]) -> str:
    rank = VALUE_TO_RANK[rank_value]
    dead = set(dead_cards)
    return next(f"{rank}{suit}" for suit in SUITS if f"{rank}{suit}" not in dead)


def has_backdoor_eight_out_straight_draw_from_hole(
    hole: tuple[str, str],
    board: list[str],
) -> bool:
    """True when one turn rank can create a hole-card-relevant 8-out straight draw."""
    if len(board) != 3:
        return False

    dead_cards = set(hole) | set(board)
    for turn_rank in range(2, 15):
        if not _rank_has_available_card(turn_rank, dead_cards):
            continue

        trial_board = list(board)
        trial_board.append(_available_card_for_rank(turn_rank, dead_cards))

        info = straight_draw_info(hole, trial_board)
        if int(info["out_count"]) >= 8 and bool(info["oesd"] or info["double_gutshot"]):
            return True

    return False


def has_qualified_backdoor_flush_draw_from_hole(
    hole: tuple[str, str],
    board: list[str],
) -> bool:
    """Backdoor flush SDV requires a meaningful high-card suit contributor."""
    if len(board) != 3:
        return False

    highest_hole_rank = max(RANK_TO_VALUE[card[0]] for card in hole)
    for suit in SUITS:
        board_suit_count = sum(1 for card in board if card[1] == suit)
        hole_cards_of_suit = [card for card in hole if card[1] == suit]
        if not hole_cards_of_suit:
            continue
        if board_suit_count + len(hole_cards_of_suit) != 3:
            continue
        if any(highest_hole_rank - RANK_TO_VALUE[card[0]] <= 2 for card in hole_cards_of_suit):
            return True

    return False


def has_high_card_sdv_backdoor_from_hole(hole: tuple[str, str], board: list[str]) -> bool:
    return (
        has_backdoor_eight_out_straight_draw_from_hole(hole, board)
        or has_qualified_backdoor_flush_draw_from_hole(hole, board)
    )


def pair_draw_type_from_profile(draws: dict[str, bool | int | list[int]]) -> str:
    """Return the displayed draw component for one-pair + draw hands.

    Gutshots and open-ended straight draws are both consolidated into
    "Straight Draw" for pair+draw display purposes. If the hand has both a
    straight draw and a flush draw, use "Combo Draw".
    """
    has_straight_component = bool(draws["straight_draw"] or draws["gutshot"])
    has_flush_component = bool(draws["flush_draw"])

    if has_flush_component and has_straight_component:
        return "Combo Draw"
    if has_flush_component:
        return "Flush Draw"
    if has_straight_component:
        return "Straight Draw"
    return "Straight Draw"


def pair_draw_subgroup_from_parts(
    made_subgroup: str,
    draws: dict[str, bool | int | list[int]],
) -> str:
    return f"{made_subgroup} + {pair_draw_type_from_profile(draws)}"


def is_pair_draw_subgroup(subgroup: str) -> bool:
    return subgroup in PAIR_DRAW_SUBGROUPS


def base_pair_subgroup_from_pair_draw(subgroup: str) -> str | None:
    if not is_pair_draw_subgroup(subgroup):
        return None
    return subgroup.split(" + ", 1)[0]


def board_has_three_or_more_same_suit(board: list[str]) -> bool:
    return any(count >= 3 for count in Counter(card[1] for card in board).values())


def made_hand_has_non_river_sdv_floor(subgroup: str, board: list[str]) -> bool:
    """Flop/turn floors keep intuitive made hands out of Air."""
    if len(board) >= 5:
        return False
    if subgroup in {"Overpair", "Top Pair"} or subgroup in NUTTED_SUBGROUPS:
        return True
    if subgroup == "Mid Pair" and not board_has_three_or_more_same_suit(board):
        return True
    return False


def pair_draw_has_non_river_sdv_floor(subgroup: str, board: list[str]) -> bool:
    """Flop/turn floors keep meaningful pair+draw hands out of Weak Pair + Draw."""
    if len(board) >= 5:
        return False
    base_pair = base_pair_subgroup_from_pair_draw(subgroup)
    if base_pair in {"Overpair", "Top Pair"}:
        return True
    if base_pair == "Mid Pair" and not board_has_three_or_more_same_suit(board):
        return True
    return False


def value_blocked_by_non_river_pair_rule(subgroup: str, board: list[str]) -> bool:
    """Flop/turn Value requires Top Pair+; Mid/Low Pair cannot be Value."""
    if len(board) >= 5:
        return False
    base_pair = base_pair_subgroup_from_pair_draw(subgroup)
    return subgroup in {"Mid Pair", "Low Pair"} or base_pair in {"Mid Pair", "Low Pair"}


def display_subgroup_for_bucket(subgroup: str, broad_bucket: str) -> str:
    """Collapse granular pair+draw internals into simple UI-facing labels."""
    if is_pair_draw_subgroup(subgroup):
        if broad_bucket == "Value":
            return "Value + Draw"
        if broad_bucket == "SDV":
            return "SDV + Draw"
        if broad_bucket == "Draw":
            return "Weak Pair + Draw"
        return subgroup
    return subgroup


def rank_equivalent_pair_component_holes(
    villain_hole: tuple[str, str],
    board: list[str],
) -> list[tuple[str, str]]:
    """Return same-rank hole combos that share the same current pair component."""
    subgroup = subgroup_of(villain_hole, board)
    base_pair_subgroup = base_pair_subgroup_from_pair_draw(subgroup)
    if base_pair_subgroup is None:
        made_subgroup = best_made_subgroup_contributed_by_hole(villain_hole, board)
        if made_subgroup not in PAIR_DRAW_BASE_SUBGROUPS:
            return [villain_hole]
        base_pair_subgroup = made_subgroup

    r1, r2 = villain_hole[0][0], villain_hole[1][0]
    board_set = set(board)
    candidates: list[tuple[str, str]] = []

    if r1 == r2:
        raw_candidates = [(f"{r1}{s1}", f"{r1}{s2}") for s1, s2 in combinations(SUITS, 2)]
    else:
        raw_candidates = [
            (f"{r1}{s1}", f"{r2}{s2}")
            for s1 in SUITS
            for s2 in SUITS
        ]

    for candidate in raw_candidates:
        if candidate[0] == candidate[1]:
            continue
        if candidate[0] in board_set or candidate[1] in board_set:
            continue
        if best_made_subgroup_contributed_by_hole(candidate, board) == base_pair_subgroup:
            candidates.append(candidate)

    return candidates or [villain_hole]


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
        hole_ranks_in_best = [RANK_TO_VALUE[c[0]] for c in hole_in_best]

        if qualifies_as_user_two_pair(board, pair_ranks, hole_ranks_in_best):
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


def best_hand_subgroup_for_board_made_strong_hand(
    hole: tuple[str, str],
    board: list[str],
) -> str | None:
    """
    Return the actual best-5-card made-hand subgroup for strong board-made hands.

    This is intentionally narrow. It only overrides the contribution-aware subgroup
    when the actual best hand is Straight or better. That fixes board-made straights,
    flushes, full houses, quads, and straight flushes without changing the existing
    contribution-aware logic for pairs, two pair, trips, sets, overpairs, top pair,
    mid pair, or low pair.
    """
    raw_class = INTERNAL_CLASSES[int(rank_7(list(hole) + board)[0])]
    if raw_class in {"Straight", "Flush", "Full House", "Quads", "Straight Flush"}:
        return raw_class
    return None


def flush_board_suit(board: list[str]) -> str | None:
    """Return the suit when the board has four or more cards of one suit."""
    counts = Counter(card[1] for card in board)
    for suit, count in counts.items():
        if count >= 4:
            return suit
    return None


def nut_flush_rank_on_flush_board(board: list[str]) -> int | None:
    """
    On a four-or-five-flush board, return the highest rank of the flush suit that
    is not already on the board. Example: As Ts 9s 8s 3h -> Ks.
    """
    suit = flush_board_suit(board)
    if suit is None:
        return None

    board_flush_ranks = {RANK_TO_VALUE[card[0]] for card in board if card[1] == suit}
    for rank_value in range(14, 1, -1):
        if rank_value not in board_flush_ranks:
            return rank_value
    return None


def has_nut_flush_card_on_flush_board(hole: tuple[str, str], board: list[str]) -> bool:
    suit = flush_board_suit(board)
    nut_rank = nut_flush_rank_on_flush_board(board)
    if suit is None or nut_rank is None:
        return False
    return any(card[1] == suit and RANK_TO_VALUE[card[0]] == nut_rank for card in hole)


# =============================================================================
# Equity helpers
# =============================================================================

def expand_range_to_combos(labels: Iterable[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for label in labels:
        out.extend(expand_exact_label_to_combos(label))
    return list(dict.fromkeys(out))


def normalize_villain_profile_id(villain_profile_id: str | None) -> str:
    raw = (villain_profile_id or "steve").strip().lower()
    return VILLAIN_PROFILE_ALIASES.get(raw, raw)


def scenario_weight_for_villain(villain_profile_id: str | None) -> float:
    normalized = normalize_villain_profile_id(villain_profile_id)
    return VILLAIN_SCENARIO_WEIGHTS.get(normalized, VILLAIN_SCENARIO_WEIGHTS["steve"])


@lru_cache(maxsize=4)
def load_scenario_catalog_from_file(catalog_path: str = DEFAULT_CATALOG_PATH) -> dict[str, dict]:
    """Parse scenario names plus hero/villain ranges from catalog.py without importing the app."""
    try:
        with open(catalog_path, "r", encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return {}

    tree = ast.parse(source, filename=catalog_path)
    scenarios: dict[str, dict] = {}

    for node in tree.body:
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "SCENARIOS" for target in node.targets):
                value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "SCENARIOS":
                value_node = node.value

        if not isinstance(value_node, ast.Dict):
            continue

        for key_node, scenario_node in zip(value_node.keys, value_node.values):
            if key_node is None:
                continue
            try:
                scenario_id = ast.literal_eval(key_node)
            except (ValueError, SyntaxError):
                continue
            if not isinstance(scenario_id, str) or not isinstance(scenario_node, ast.Call):
                continue

            keyword_nodes = {kw.arg: kw.value for kw in scenario_node.keywords if kw.arg}
            display_name = scenario_id
            hero_range_tokens: tuple[str, ...] = ()
            villain_range_tokens: tuple[str, ...] = ()

            if "display_name" in keyword_nodes:
                try:
                    display_value = ast.literal_eval(keyword_nodes["display_name"])
                    if isinstance(display_value, str):
                        display_name = display_value
                except (ValueError, SyntaxError):
                    pass

            if "hero_range_tokens" in keyword_nodes:
                try:
                    tokens_value = ast.literal_eval(keyword_nodes["hero_range_tokens"])
                    hero_range_tokens = tuple(str(token) for token in tokens_value)
                except (ValueError, SyntaxError, TypeError):
                    hero_range_tokens = ()

            if "villain_range_tokens" in keyword_nodes:
                try:
                    tokens_value = ast.literal_eval(keyword_nodes["villain_range_tokens"])
                    villain_range_tokens = tuple(str(token) for token in tokens_value)
                except (ValueError, SyntaxError, TypeError):
                    villain_range_tokens = ()

            if hero_range_tokens and villain_range_tokens:
                scenarios[scenario_id] = {
                    "id": scenario_id,
                    "display_name": display_name,
                    "hero_range_tokens": hero_range_tokens,
                    "villain_range_tokens": villain_range_tokens,
                }

    return scenarios


def selected_hero_range_mix(
    villain_profile_id: str | None,
    scenario_hero_range_tokens: Iterable[str] | None,
) -> dict:
    fixed_labels = parse_range_string(HERO_RANGE_TOKENS)
    scenario_labels = (
        parse_range_string(scenario_hero_range_tokens)
        if scenario_hero_range_tokens
        else []
    )

    scenario_weight = scenario_weight_for_villain(villain_profile_id) if scenario_labels else 0.0
    fixed_weight = 1.0 - scenario_weight
    if not scenario_labels:
        fixed_weight = 1.0

    return {
        "villain_profile_id": normalize_villain_profile_id(villain_profile_id),
        "scenario_weight": scenario_weight,
        "fixed_weight": fixed_weight,
        "scenario_labels": scenario_labels,
        "fixed_labels": fixed_labels,
        "scenario_combos": expand_range_to_combos(scenario_labels) if scenario_labels else [],
        "fixed_combos": expand_range_to_combos(fixed_labels),
        "source": "hybrid_scenario_fixed" if scenario_labels else "fixed",
    }


def weighted_hybrid_equity(
    scenario_equity: float | None,
    fixed_equity: float,
    scenario_weight: float,
    fixed_weight: float,
) -> float:
    if scenario_equity is None or scenario_weight <= 0:
        return fixed_equity
    return scenario_weight * scenario_equity + fixed_weight * fixed_equity


def equity_vs_hybrid_hero_range_mc(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_mix: dict,
    iters: int,
    equity_base_seed: int,
    purpose: str,
) -> float:
    fixed_rng = random.Random(stable_combo_rng_seed(equity_base_seed, board, villain_hole, f"{purpose}:fixed"))
    fixed_equity = equity_vs_hero_range_mc(
        villain_hole,
        board,
        list(hero_mix["fixed_combos"]),
        iters,
        fixed_rng,
    )

    scenario_equity = None
    if hero_mix["scenario_combos"] and float(hero_mix["scenario_weight"]) > 0:
        scenario_rng = random.Random(
            stable_combo_rng_seed(equity_base_seed, board, villain_hole, f"{purpose}:scenario")
        )
        scenario_equity = equity_vs_hero_range_mc(
            villain_hole,
            board,
            list(hero_mix["scenario_combos"]),
            iters,
            scenario_rng,
        )

    return weighted_hybrid_equity(
        scenario_equity=scenario_equity,
        fixed_equity=fixed_equity,
        scenario_weight=float(hero_mix["scenario_weight"]),
        fixed_weight=float(hero_mix["fixed_weight"]),
    )


def equity_vs_hybrid_hero_range_river_exact(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_mix: dict,
) -> float:
    fixed_equity = equity_vs_hero_range_river_exact(
        villain_hole,
        board,
        list(hero_mix["fixed_combos"]),
    )
    scenario_equity = None
    if hero_mix["scenario_combos"] and float(hero_mix["scenario_weight"]) > 0:
        scenario_equity = equity_vs_hero_range_river_exact(
            villain_hole,
            board,
            list(hero_mix["scenario_combos"]),
        )

    return weighted_hybrid_equity(
        scenario_equity=scenario_equity,
        fixed_equity=fixed_equity,
        scenario_weight=float(hero_mix["scenario_weight"]),
        fixed_weight=float(hero_mix["fixed_weight"]),
    )


def current_score_vs_hero_range_exact(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_combos: list[tuple[str, str]],
) -> float:
    """Current-street made score: % of board-live hero combos beaten now.

    This intentionally ignores villain-card blockers before the river. Current
    score is meant to describe the intuitive strength of villain's made hand
    against the shape of hero's range on this board. If we remove hero combos
    blocked by villain's exact cards, a weaker hand can appear stronger simply
    because it blocks more of the hands that beat it, e.g. AQo scoring above
    AA/KK on Q-6-3 by blocking QQ. River stays blocker-aware because river
    current score is final hand equity.
    """
    if len(board) == 5:
        return equity_vs_hero_range_river_exact(villain_hole, board, hero_combos)

    board_set = set(board)
    valid_hero = [hc for hc in hero_combos if not (set(hc) & board_set)]
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


def current_score_vs_hybrid_hero_range_exact(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_mix: dict,
) -> float:
    fixed_score = current_score_vs_hero_range_exact(
        villain_hole,
        board,
        list(hero_mix["fixed_combos"]),
    )
    scenario_score = None
    if hero_mix["scenario_combos"] and float(hero_mix["scenario_weight"]) > 0:
        scenario_score = current_score_vs_hero_range_exact(
            villain_hole,
            board,
            list(hero_mix["scenario_combos"]),
        )

    return weighted_hybrid_equity(
        scenario_equity=scenario_score,
        fixed_equity=fixed_score,
        scenario_weight=float(hero_mix["scenario_weight"]),
        fixed_weight=float(hero_mix["fixed_weight"]),
    )


def pair_component_current_score_vs_hero_range_rank_exact(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_combos: list[tuple[str, str]],
) -> float:
    """Rank-level current score for the made-pair part of a pair+draw hand."""
    candidates = rank_equivalent_pair_component_holes(villain_hole, board)
    if not candidates:
        return current_score_vs_hero_range_exact(villain_hole, board, hero_combos)

    scores = [
        current_score_vs_hero_range_exact(candidate, board, hero_combos)
        for candidate in candidates
    ]
    return sum(scores) / len(scores)


def pair_component_current_score_vs_hybrid_hero_range_rank_exact(
    villain_hole: tuple[str, str],
    board: list[str],
    hero_mix: dict,
) -> float:
    fixed_score = pair_component_current_score_vs_hero_range_rank_exact(
        villain_hole=villain_hole,
        board=board,
        hero_combos=list(hero_mix["fixed_combos"]),
    )

    scenario_score = None
    if hero_mix["scenario_combos"] and float(hero_mix["scenario_weight"]) > 0:
        scenario_score = pair_component_current_score_vs_hero_range_rank_exact(
            villain_hole=villain_hole,
            board=board,
            hero_combos=list(hero_mix["scenario_combos"]),
        )

    return weighted_hybrid_equity(
        scenario_equity=scenario_score,
        fixed_equity=fixed_score,
        scenario_weight=float(hero_mix["scenario_weight"]),
        fixed_weight=float(hero_mix["fixed_weight"]),
    )


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


def hero_range_compression_factor(hero_mix: dict | None) -> float:
    """Return how much condensed scenario ranges should lower thresholds.

    Fixed cutoffs work well in wide ranges, but become too strict in condensed
    ranges. Example: AK on K-6-7-8 can be clear Value in a 4-bet pot even if it
    does not beat 79.5% of a very strong hero range. This factor combines range
    narrowness with villain scenario-awareness so broad SRP spots remain mostly
    unchanged while tight 4-bet/3-bet configurations compress more.
    """
    if not hero_mix:
        return 0.0

    scenario_weight = float(hero_mix.get("scenario_weight", 0.0))
    if scenario_weight <= 0:
        return 0.0

    scenario_count = len(hero_mix.get("scenario_combos", ()))
    fixed_count = len(hero_mix.get("fixed_combos", ()))
    if scenario_count <= 0 or fixed_count <= 0:
        return 0.0

    range_narrowness = 1.0 - min(1.0, scenario_count / fixed_count)
    return max(0.0, min(1.0, scenario_weight * range_narrowness))


def equity_thresholds_for_board(
    board: list[str],
    hero_mix: dict | None = None,
) -> dict[str, float]:
    street = street_name_from_board(board)
    base = dict(STREET_EQUITY_THRESHOLDS[street])
    compression = hero_range_compression_factor(hero_mix)
    if compression <= 0:
        return base

    adjustments = RANGE_COMPRESSION_THRESHOLD_ADJUSTMENTS[street]
    floors = RANGE_COMPRESSION_THRESHOLD_FLOORS[street]
    return {
        key: max(min(floors[key], base[key]), base[key] - adjustments[key] * compression)
        for key in base
    }


def high_card_has_sdv_profile(
    hole: tuple[str, str],
    board: list[str],
    made_score: float,
    thresholds: dict[str, float],
    equity_score: float | None = None,
) -> bool:
    """Return whether High Card has enough SDV profile for this street.

    Flop High Card uses current strength plus the highest-available/backdoor
    gates. Turn High Card uses current strength and no backdoor gate.
    River High Card uses final current strength, which is equivalent to equity.
    """
    high_card_score = (
        TURN_HIGH_CARD_CURRENT_SCORE_WEIGHT * made_score
        + TURN_HIGH_CARD_EQUITY_WEIGHT * (
            made_score if equity_score is None else equity_score
        )
        if len(board) == 4
        else made_score
    )

    if high_card_score < thresholds["air"]:
        return False

    if len(board) >= 4:
        return True

    hole_ranks = sorted((RANK_TO_VALUE[card[0]] for card in hole), reverse=True)
    high_rank = hole_ranks[0]

    board_ranks = {RANK_TO_VALUE[card[0]] for card in board}
    highest_available_rank = next(
        rank for rank in range(RANK_TO_VALUE["A"], RANK_TO_VALUE["2"] - 1, -1)
        if rank not in board_ranks
    )

    if high_rank == highest_available_rank:
        return True

    return has_high_card_sdv_backdoor_from_hole(hole, board)


def is_board_made_strong_hand(
    hole: tuple[str, str],
    board: list[str],
    subgroup: str,
) -> bool:
    """True when the best Straight+ hand can be made entirely from the board."""
    if subgroup not in NUTTED_SUBGROUPS:
        return False

    hole_cards = set(hole)
    return any(hole_cards.isdisjoint(best_five) for best_five in best_five_combos(hole, board))


def stable_combo_rng_seed(
    base_seed: int,
    board: list[str],
    hole: tuple[str, str],
    purpose: str,
) -> int:
    seed_text = "|".join(
        [
            str(base_seed),
            purpose,
            ",".join(board),
            ",".join(hole),
        ]
    )
    digest = hashlib.blake2b(seed_text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


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
    actual_strong_subgroup = best_hand_subgroup_for_board_made_strong_hand(hole, board)

    # Board-made / actual best-hand override for Straight+ only.
    # This fixes boards where the best 5-card hand is a board-made straight,
    # flush, full house, quads, or straight flush while deliberately preserving
    # the existing contribution-aware pair / two-pair / trips / set logic.
    if actual_strong_subgroup is not None:
        return actual_strong_subgroup

    # Blanket override:
    # any contributed one-pair hand with a draw becomes an internal granular pair+draw subgroup.
    # True Two Pair stays Two Pair, even if it also has a draw.
    if (
        len(board) < 5
        and has_draw
        and made_subgroup in PAIR_DRAW_BASE_SUBGROUPS
    ):
        return pair_draw_subgroup_from_parts(made_subgroup, draws)

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
    pair_component_equity_vs_hero: float | None = None,
    current_score_vs_hero: float | None = None,
    pair_component_current_score_vs_hero: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> str:
    thresholds = thresholds or equity_thresholds_for_board(board)
    made_score = current_score_vs_hero if current_score_vs_hero is not None else eq_vs_hero

    if subgroup in {"Gutshot", "Straight Draw", "Flush Draw", "Combo Draw"}:
        return "Draw"

    if is_pair_draw_subgroup(subgroup):
        # Pair + Draw placement uses future equity only to stay draw-aware.
        # Value/SDV/weak status comes from the current made-pair component.
        pair_score = (
            pair_component_current_score_vs_hero
            if pair_component_current_score_vs_hero is not None
            else (
                current_score_vs_hero
                if current_score_vs_hero is not None
                else (
                    pair_component_equity_vs_hero
                    if pair_component_equity_vs_hero is not None
                    else eq_vs_hero
                )
            )
        )

        if pair_draw_has_non_river_sdv_floor(subgroup, board):
            if not value_blocked_by_non_river_pair_rule(subgroup, board) and pair_score >= thresholds["value"]:
                return "Value"
            return "SDV"

        if eq_vs_hero < thresholds["air"]:
            return "Draw"

        if value_blocked_by_non_river_pair_rule(subgroup, board):
            return "SDV" if pair_score >= thresholds["air"] else "Draw"
        if pair_score >= thresholds["value"]:
            return "Value"
        if pair_score >= thresholds["air"]:
            return "SDV"
        return "Draw"

    if subgroup == "High Card":
        return (
            "SDV"
            if high_card_has_sdv_profile(
                hole,
                board,
                made_score,
                thresholds,
                equity_score=eq_vs_hero,
            )
            else "Air"
        )

    # Hard nut rule: if this combo ties the theoretical best possible hand on
    # this board, it must be Nutted Value even if its equity is pulled down by
    # chopping against other nut hands in the comparison range. Example:
    # Ax on K-Q-J-T-x is still the nuts despite tying other Ax holdings.
    if is_best_possible_hand(hole, board):
        return "Nutted Value"

    if made_score < thresholds["air"] and is_board_made_strong_hand(hole, board, subgroup):
        return "SDV"

    # Current-street score below the air cutoff is not strong enough to carry
    # made-hand showdown value. Pure draws remain in Draw above.
    if made_score < thresholds["air"]:
        if made_hand_has_non_river_sdv_floor(subgroup, board):
            return "SDV"
        return "Air"

    if subgroup in {"Overpair", "Top Pair", "Mid Pair", "Low Pair"}:
        if value_blocked_by_non_river_pair_rule(subgroup, board):
            return "SDV"
        return "Value" if made_score >= thresholds["value"] else "SDV"

    # On four-or-five-flush boards, non-nut flushes should not become Nutted Value
    # just because their equity clears the normal nutted threshold. Treat only
    # straight flushes and nut-flush-card holdings as eligible for Nutted Value.
    if flush_board_suit(board) is not None:
        if subgroup == "Straight Flush":
            return "Nutted Value"
        if subgroup == "Flush":
            if has_nut_flush_card_on_flush_board(hole, board):
                if made_score >= thresholds["nutted_value"]:
                    return "Nutted Value"
                if made_score >= thresholds["value"]:
                    return "Value"
                return "SDV"
            return "Value" if made_score >= thresholds["value"] else "SDV"

    if subgroup in NUTTED_SUBGROUPS:
        if made_score >= thresholds["nutted_value"]:
            return "Nutted Value"
        if made_score >= thresholds["value"]:
            return "Value"
        return "SDV"

    return "SDV"



def bucket_combo(
    hole: tuple[str, str],
    board: list[str],
    eq_vs_hero: float,
    pair_component_equity_vs_hero: float | None = None,
    current_score_vs_hero: float | None = None,
    pair_component_current_score_vs_hero: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> tuple[str, str]:
    subgroup = subgroup_of(hole, board)
    broad_bucket = broad_bucket_for_subgroup(
        hole,
        board,
        subgroup,
        eq_vs_hero,
        pair_component_equity_vs_hero=pair_component_equity_vs_hero,
        current_score_vs_hero=current_score_vs_hero,
        pair_component_current_score_vs_hero=pair_component_current_score_vs_hero,
        thresholds=thresholds,
    )
    return broad_bucket, subgroup


def _resolve_bucket_for_label_subgroup(
    records: list[dict],
    board: list[str],
    thresholds: dict[str, float] | None = None,
) -> str:
    """
    Keep all combos of the same exact label in the same subgroup under one broad bucket.

    Resolution uses the same averaged metric displayed in the report:
    - normal made hands use average current-street score
    - pair+draw hands use average current pair-component score for Value/SDV placement
    - pure draws remain in Draw

    This avoids a label with an average score above the threshold landing in the
    lower bucket because individual combos straddle the cutoff.
    """
    if not records:
        raise ValueError("cannot resolve bucket for empty record group")

    subgroup = str(records[0].get("subgroup", ""))
    thresholds = thresholds or equity_thresholds_for_board(board)
    avg_eq = sum(float(record["equity_vs_hero"]) for record in records) / len(records)
    avg_current_score = (
        sum(float(record.get("current_score_vs_hero", record["equity_vs_hero"])) for record in records)
        / len(records)
    )

    if subgroup in {"Gutshot", "Straight Draw", "Flush Draw", "Combo Draw"}:
        return "Draw"

    if is_pair_draw_subgroup(subgroup):
        pair_equities = [
            float(
                record.get("pair_component_current_score_vs_hero")
                if record.get("pair_component_current_score_vs_hero") is not None
                else record.get("current_score_vs_hero", record["equity_vs_hero"])
            )
            for record in records
        ]
        avg_pair_score = sum(pair_equities) / len(pair_equities)

        if pair_draw_has_non_river_sdv_floor(subgroup, board):
            if not value_blocked_by_non_river_pair_rule(subgroup, board) and avg_pair_score >= thresholds["value"]:
                return "Value"
            return "SDV"

        if avg_eq < thresholds["air"]:
            return "Draw"

        if value_blocked_by_non_river_pair_rule(subgroup, board):
            return "SDV" if avg_pair_score >= thresholds["air"] else "Draw"
        if avg_pair_score >= thresholds["value"]:
            return "Value"
        if avg_pair_score >= thresholds["air"]:
            return "SDV"
        return "Draw"

    if subgroup == "High Card":
        representative_hole = tuple(records[0]["combo"])
        return (
            "SDV"
            if high_card_has_sdv_profile(
                representative_hole,
                board,
                avg_current_score,
                thresholds,
                equity_score=avg_eq,
            )
            else "Air"
        )

    if all(is_best_possible_hand(tuple(record["combo"]), board) for record in records):
        return "Nutted Value"

    if avg_current_score < thresholds["air"] and any(
        is_board_made_strong_hand(tuple(record["combo"]), board, subgroup)
        for record in records
    ):
        return "SDV"

    if avg_current_score < thresholds["air"]:
        if made_hand_has_non_river_sdv_floor(subgroup, board):
            return "SDV"
        return "Air"

    if subgroup in {"Overpair", "Top Pair", "Mid Pair", "Low Pair"}:
        if value_blocked_by_non_river_pair_rule(subgroup, board):
            return "SDV"
        return "Value" if avg_current_score >= thresholds["value"] else "SDV"

    if flush_board_suit(board) is not None:
        if subgroup == "Straight Flush":
            return "Nutted Value"
        if subgroup == "Flush":
            nut_flush_group = all(
                has_nut_flush_card_on_flush_board(tuple(record["combo"]), board)
                for record in records
            )
            if nut_flush_group and avg_current_score >= thresholds["nutted_value"]:
                return "Nutted Value"
            return "Value" if avg_current_score >= thresholds["value"] else "SDV"

    if subgroup in NUTTED_SUBGROUPS:
        if avg_current_score >= thresholds["nutted_value"]:
            return "Nutted Value"
        if avg_current_score >= thresholds["value"]:
            return "Value"
        return "SDV"

    return "SDV"


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
    - scenario_hero_range_tokens should come from catalog.py's selected scenario.
    - villain_profile_id controls the scenario/fixed hybrid comparison weights.
    """
    input_villain_profile_id = villain_profile_id

    rng = rng or random.Random(42)
    run_iters = resolve_iters(board, iters)
    equity_base_seed = rng.randrange(0, 2**64)

    hero_mix = selected_hero_range_mix(
        villain_profile_id=villain_profile_id,
        scenario_hero_range_tokens=scenario_hero_range_tokens,
    )
    active_thresholds = equity_thresholds_for_board(board, hero_mix)
    base_thresholds = dict(STREET_EQUITY_THRESHOLDS[street_name_from_board(board)])
    threshold_compression = hero_range_compression_factor(hero_mix)
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
            eq = equity_vs_hybrid_hero_range_river_exact(hole, board, hero_mix)
        else:
            eq = equity_vs_hybrid_hero_range_mc(
                villain_hole=hole,
                board=board,
                hero_mix=hero_mix,
                iters=run_iters,
                equity_base_seed=equity_base_seed,
                purpose="total_equity",
            )
        current_score = current_score_vs_hybrid_hero_range_exact(hole, board, hero_mix)

        subgroup = subgroup_of(hole, board)
        pair_component_equity = None
        pair_component_current_score = None
        if len(board) < 5 and is_pair_draw_subgroup(subgroup):
            pair_component_current_score = (
                pair_component_current_score_vs_hybrid_hero_range_rank_exact(
                    villain_hole=hole,
                    board=board,
                    hero_mix=hero_mix,
                )
            )
            pair_component_equity = pair_component_current_score

        initial_broad_bucket = broad_bucket_for_subgroup(
            hole,
            board,
            subgroup,
            eq,
            pair_component_equity_vs_hero=pair_component_equity,
            current_score_vs_hero=current_score,
            pair_component_current_score_vs_hero=pair_component_current_score,
            thresholds=active_thresholds,
        )
        internal_name = internal_hand_class_of(hole, board)
        best_made_subgroup = best_made_subgroup_contributed_by_hole(hole, board)

        evaluated_records.append(
            {
                "label": label,
                "combo": hole,
                "equity_vs_hero": eq,
                "current_score_vs_hero": current_score,
                "pair_component_equity_vs_hero": pair_component_equity,
                "pair_component_current_score_vs_hero": pair_component_current_score,
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
        if record["subgroup"] == "High Card":
            continue
        records_by_label_and_subgroup[(record["label"], record["subgroup"])].append(record)

    for records in records_by_label_and_subgroup.values():
        resolved_bucket = _resolve_bucket_for_label_subgroup(
            records,
            board,
            thresholds=active_thresholds,
        )
        for record in records:
            record["broad_bucket"] = resolved_bucket

    bucket_combo_counts: Counter[str] = Counter()
    subgroup_combo_counts: Counter[str] = Counter()
    bucket_subgroup_combo_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_internal_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_equities: dict[str, list[float]] = defaultdict(list)
    bucket_current_scores: dict[str, list[float]] = defaultdict(list)
    subgroup_equities: dict[str, list[float]] = defaultdict(list)
    subgroup_current_scores: dict[str, list[float]] = defaultdict(list)
    label_bucket_subgroup_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    bucket_combo_details: dict[str, list[dict]] = defaultdict(list)

    for record in evaluated_records:
        label = record["label"]
        hole = record["combo"]
        broad_bucket = record["broad_bucket"]
        internal_subgroup = record["subgroup"]
        display_subgroup = display_subgroup_for_bucket(internal_subgroup, broad_bucket)
        internal_name = record["internal_type"]
        eq = float(record["equity_vs_hero"])
        current_score = float(record.get("current_score_vs_hero", eq))

        bucket_combo_counts[broad_bucket] += 1
        subgroup_combo_counts[display_subgroup] += 1
        bucket_subgroup_combo_counts[broad_bucket][display_subgroup] += 1
        bucket_internal_counts[broad_bucket][internal_name] += 1
        bucket_equities[broad_bucket].append(eq)
        bucket_current_scores[broad_bucket].append(current_score)
        subgroup_equities[display_subgroup].append(eq)
        subgroup_current_scores[display_subgroup].append(current_score)
        label_bucket_subgroup_counts[(broad_bucket, display_subgroup)][label] += 1
        bucket_combo_details[broad_bucket].append(
            {
                "label": label,
                "combo": list(hole),
                "equity_vs_hero": eq,
                "current_score_vs_hero": current_score,
                "pair_component_equity_vs_hero": record.get("pair_component_equity_vs_hero"),
                "pair_component_current_score_vs_hero": record.get("pair_component_current_score_vs_hero"),
                "broad_bucket": broad_bucket,
                "initial_broad_bucket": record["initial_broad_bucket"],
                "subgroup": display_subgroup,
                "internal_subgroup": internal_subgroup,
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
            avg_current_score = (
                sum(
                    detail["current_score_vs_hero"]
                    for detail in bucket_combo_details[broad_bucket]
                    if detail["subgroup"] == subgroup
                )
                / combo_count
            )

            subgroup_details = [
                detail
                for detail in bucket_combo_details[broad_bucket]
                if detail["subgroup"] == subgroup
            ]
            pair_component_values = [
                float(detail["pair_component_equity_vs_hero"])
                for detail in subgroup_details
                if detail.get("pair_component_equity_vs_hero") is not None
            ]
            pair_component_current_values = [
                float(detail["pair_component_current_score_vs_hero"])
                for detail in subgroup_details
                if detail.get("pair_component_current_score_vs_hero") is not None
            ]

            subgroup_map[subgroup] = {
                "combo_count": combo_count,
                "labels": labels,
                "avg_equity_vs_hero": avg_equity,
                "avg_current_score_vs_hero": avg_current_score,
            }
            if pair_component_values:
                subgroup_map[subgroup]["avg_pair_component_equity_vs_hero"] = (
                    sum(pair_component_values) / len(pair_component_values)
                )
            if pair_component_current_values:
                subgroup_map[subgroup]["avg_pair_component_current_score_vs_hero"] = (
                    sum(pair_component_current_values) / len(pair_component_current_values)
                )

        if subgroup_map:
            bucket_subgroups[broad_bucket] = subgroup_map

    return {
        "board": list(board),
        "iters": run_iters,
        "villain_profile_id": input_villain_profile_id,
        "hero_range_source": hero_mix["source"],
        "hero_range_mix": {
            "villain_profile_id": hero_mix["villain_profile_id"],
            "scenario_weight": hero_mix["scenario_weight"],
            "fixed_weight": hero_mix["fixed_weight"],
            "scenario_label_count": len(hero_mix["scenario_labels"]),
            "fixed_label_count": len(hero_mix["fixed_labels"]),
            "scenario_combo_count": len(hero_mix["scenario_combos"]),
            "fixed_combo_count": len(hero_mix["fixed_combos"]),
        },
        "base_thresholds": base_thresholds,
        "active_thresholds": dict(active_thresholds),
        "threshold_compression_factor": threshold_compression,
        "hero_comparison_labels": list(dict.fromkeys(
            list(hero_mix["scenario_labels"]) + list(hero_mix["fixed_labels"])
        )),
        "scenario_hero_comparison_labels": list(hero_mix["scenario_labels"]),
        "fixed_hero_comparison_labels": list(hero_mix["fixed_labels"]),
        "total_combos": total,
        "bucket_combo_counts": dict(bucket_combo_counts),
        "subgroup_combo_counts": dict(subgroup_combo_counts),
        "bucket_subgroup_combo_counts": {
            bucket: dict(counter) for bucket, counter in bucket_subgroup_combo_counts.items()
        },
        "bucket_internal_counts": {k: dict(v) for k, v in bucket_internal_counts.items()},
        "bucket_equities": {k: list(v) for k, v in bucket_equities.items()},
        "bucket_current_scores": {k: list(v) for k, v in bucket_current_scores.items()},
        "subgroup_equities": {k: list(v) for k, v in subgroup_equities.items()},
        "subgroup_current_scores": {k: list(v) for k, v in subgroup_current_scores.items()},
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
