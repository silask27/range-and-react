# File: api/app/engine/board_texture.py
# Summary: Board-texture helpers for villain action policy. Evaluates whether the
# current board is wet / connected / paired / static / draw-completing so the
# policy engine can adjust aggression, trapping, bluffing, draw continuation,
# vulnerability, and sizing behavior.

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
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


@dataclass(frozen=True)
class BoardTextureInfo:
    """
    Canonical board-texture snapshot used by the villain policy layer.

    Strategic notes:
    - wet_connected:
        board has both flush-draw and straight-draw pressure while neither draw
        has already completed on board
    - static_paired / static_unpaired:
        low-volatility boards where players can trap more often
    - draws_to_nuts_reduced:
        draw continuation / aggression should drop because major draws are
        completed or paired structure makes non-nut draws less appealing
    - vulnerability should generally rise with dynamic / connected boards and
      fall on static paired / monotone / double-paired textures
    """

    board: tuple[str, ...]
    street_len: int

    paired_board: bool
    two_pair_board: bool
    trips_board: bool
    double_paired: bool

    flush_draw_present: bool
    flush_completed: bool
    board_is_monotone: bool
    board_is_double_suited: bool
    monotone_flop: bool
    four_to_flush: bool

    straight_draw_present: bool
    straight_completed: bool
    four_to_straight: bool

    wet_connected: bool
    low_connected: bool
    broadway_static: bool

    dynamic_board: bool
    static_paired: bool
    static_unpaired: bool
    draws_to_nuts_reduced: bool

    max_suit_count: int
    max_straight_window_hits: int
    longest_consecutive_run: int
    high_rank_count: int
    highest_rank: int
    lowest_rank: int

    def texture_keys(self) -> list[str]:
        """
        Return canonical texture-profile keys to be consumed by villain policy.
        """
        keys: list[str] = []

        if self.wet_connected:
            keys.append("wet_connected")
        if self.static_paired:
            keys.append("static_paired")
        if self.static_unpaired:
            keys.append("static_unpaired")
        if self.flush_completed:
            keys.append("flush_completed")
        if self.straight_completed:
            keys.append("straight_completed")
        if self.paired_board:
            keys.append("paired_board")
        if self.monotone_flop:
            keys.append("monotone_flop")
        if self.four_to_flush:
            keys.append("four_to_flush")
        if self.four_to_straight:
            keys.append("four_to_straight")
        if self.double_paired:
            keys.append("double_paired")
        if self.broadway_static:
            keys.append("broadway_static")
        if self.low_connected:
            keys.append("low_connected")

        return keys


def _normalize_card(card: str) -> str:
    card = card.strip()
    if len(card) != 2:
        raise ValueError(f"invalid card '{card}'")
    rank = card[0].upper()
    suit = card[1].lower()
    if rank not in RANKS or suit not in SUITS:
        raise ValueError(f"invalid card '{card}'")
    return f"{rank}{suit}"


def _normalize_board(board: Iterable[str]) -> list[str]:
    out = [_normalize_card(card) for card in board]
    if len(out) not in {3, 4, 5}:
        raise ValueError("board must contain 3, 4, or 5 cards")
    if len(set(out)) != len(out):
        raise ValueError("board contains duplicate cards")
    return out


def _ranks_with_ace_low(cards: Iterable[str]) -> set[int]:
    ranks = {RANK_TO_VALUE[c[0]] for c in cards}
    if 14 in ranks:
        ranks.add(1)
    return ranks


def _straight_high(unique_ranks: set[int]) -> int | None:
    rset = set(unique_ranks)
    if 14 in rset:
        rset.add(1)
    for start in range(10, 0, -1):
        seq = set(range(start, start + 5))
        if seq.issubset(rset):
            return 5 if seq == {1, 2, 3, 4, 5} else (start + 4)
    return None


def _max_hits_in_any_straight_window(unique_ranks: set[int]) -> int:
    """
    For each possible 5-rank straight window, count how many board ranks fall
    into that window. This is a useful board-only measure of straight-draw density.
    """
    rset = set(unique_ranks)
    if 14 in rset:
        rset.add(1)

    best = 0
    for start in range(1, 11):
        window = set(range(start, start + 5))
        best = max(best, len(window & rset))
    return best


def _longest_consecutive_run(unique_ranks: set[int]) -> int:
    """
    Longest consecutive run length across board ranks only.
    Ace-low support is included.
    """
    rset = set(unique_ranks)
    if 14 in rset:
        rset.add(1)

    ordered = sorted(rset)
    if not ordered:
        return 0

    best = 1
    current = 1
    for i in range(1, len(ordered)):
        if ordered[i] == ordered[i - 1] + 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _pair_structure(board: list[str]) -> tuple[bool, bool, bool, bool]:
    """
    Returns:
    - paired_board
    - two_pair_board
    - trips_board
    - double_paired
    """
    rank_counts = Counter(card[0] for card in board)
    counts = sorted(rank_counts.values(), reverse=True)

    paired_board = counts[0] >= 2
    two_pair_board = counts.count(2) >= 2
    trips_board = counts[0] >= 3
    double_paired = two_pair_board
    return paired_board, two_pair_board, trips_board, double_paired


def _flush_texture(board: list[str]) -> tuple[bool, bool, bool, bool, bool, int]:
    """
    Returns:
    - flush_draw_present
    - flush_completed
    - board_is_monotone
    - board_is_double_suited
    - four_to_flush
    - max_suit_count
    """
    suit_counts = Counter(card[1] for card in board)
    max_suit_count = max(suit_counts.values())

    board_is_monotone = len(board) == 3 and max_suit_count == 3
    board_is_double_suited = len(board) >= 3 and max_suit_count >= 2
    four_to_flush = len(board) >= 4 and max_suit_count >= 4

    if len(board) == 3:
        flush_completed = False
        flush_draw_present = max_suit_count >= 2
    elif len(board) == 4:
        flush_completed = max_suit_count >= 4
        flush_draw_present = (max_suit_count == 3) and not flush_completed
    else:
        # On river a board with 3+ of one suit means flushes are available.
        flush_completed = max_suit_count >= 3
        flush_draw_present = False

    return (
        flush_draw_present,
        flush_completed,
        board_is_monotone,
        board_is_double_suited,
        four_to_flush,
        max_suit_count,
    )


def _straight_texture(board: list[str]) -> tuple[bool, bool, bool, int, int]:
    """
    Returns:
    - straight_draw_present
    - straight_completed
    - four_to_straight
    - max_straight_window_hits
    - longest_consecutive_run
    """
    ranks = _ranks_with_ace_low(board)
    straight_completed = _straight_high(ranks) is not None
    max_hits = _max_hits_in_any_straight_window(ranks)
    longest_run = _longest_consecutive_run(ranks)

    if len(board) == 5:
        straight_draw_present = False
    else:
        # Board-only "straight draw present" heuristic:
        # if the board already clusters at least 3 ranks inside some straight
        # window, the texture is straight-draw rich enough to matter.
        straight_draw_present = (max_hits >= 3) and not straight_completed

    # Four-to-straight is most useful on turn/river runouts where the board itself
    # is one card from making a straight, but that straight is not yet completed.
    four_to_straight = (len(board) >= 4) and (max_hits >= 4) and not straight_completed

    return (
        straight_draw_present,
        straight_completed,
        four_to_straight,
        max_hits,
        longest_run,
    )


def _rank_extremes(board: list[str]) -> tuple[int, int, int]:
    values = sorted(RANK_TO_VALUE[card[0]] for card in board)
    highest = values[-1]
    lowest = values[0]
    high_rank_count = sum(1 for value in values if value >= 10)
    return highest, lowest, high_rank_count


def evaluate_board_texture(board: Iterable[str]) -> BoardTextureInfo:
    """
    Compute board texture info used by villain policy.

    Strategic interpretation:
    - wet_connected:
        both straight and flush pressure exist and neither is complete yet
    - dynamic_board:
        board where later streets can meaningfully shift relative hand strength
    - static_paired / static_unpaired:
        low-volatility boards where trapping increases
    - draws_to_nuts_reduced:
        draw continuation/aggression should drop because paired boards or already-
        completed major draws reduce how attractive many draws are
    - broadway_static:
        dry high-card textures where good players may trap more and size more
        thoughtfully rather than just auto-fastplay
    - low_connected:
        low coordinated boards that tend to increase vulnerability for one-pair
        and medium-strength made hands
    """
    board_list = _normalize_board(board)

    paired_board, two_pair_board, trips_board, double_paired = _pair_structure(board_list)
    (
        flush_draw_present,
        flush_completed,
        board_is_monotone,
        board_is_double_suited,
        four_to_flush,
        max_suit_count,
    ) = _flush_texture(board_list)
    (
        straight_draw_present,
        straight_completed,
        four_to_straight,
        max_straight_window_hits,
        longest_consecutive_run,
    ) = _straight_texture(board_list)
    highest_rank, lowest_rank, high_rank_count = _rank_extremes(board_list)

    monotone_flop = board_is_monotone

    wet_connected = (
        flush_draw_present
        and straight_draw_present
        and not flush_completed
        and not straight_completed
    )

    dynamic_board = (
        wet_connected
        or flush_draw_present
        or straight_draw_present
        or flush_completed
        or straight_completed
        or four_to_flush
        or four_to_straight
    )

    static_paired = paired_board and not dynamic_board
    static_unpaired = (not paired_board) and not dynamic_board

    draws_to_nuts_reduced = (
        paired_board
        or flush_completed
        or straight_completed
        or four_to_flush
        or four_to_straight
    )

    broadway_static = (
        static_unpaired
        and high_rank_count >= 2
        and highest_rank >= 12
    )

    low_connected = (
        longest_consecutive_run >= 3
        and highest_rank <= 9
    )

    return BoardTextureInfo(
        board=tuple(board_list),
        street_len=len(board_list),
        paired_board=paired_board,
        two_pair_board=two_pair_board,
        trips_board=trips_board,
        double_paired=double_paired,
        flush_draw_present=flush_draw_present,
        flush_completed=flush_completed,
        board_is_monotone=board_is_monotone,
        board_is_double_suited=board_is_double_suited,
        monotone_flop=monotone_flop,
        four_to_flush=four_to_flush,
        straight_draw_present=straight_draw_present,
        straight_completed=straight_completed,
        four_to_straight=four_to_straight,
        wet_connected=wet_connected,
        low_connected=low_connected,
        broadway_static=broadway_static,
        dynamic_board=dynamic_board,
        static_paired=static_paired,
        static_unpaired=static_unpaired,
        draws_to_nuts_reduced=draws_to_nuts_reduced,
        max_suit_count=max_suit_count,
        max_straight_window_hits=max_straight_window_hits,
        longest_consecutive_run=longest_consecutive_run,
        high_rank_count=high_rank_count,
        highest_rank=highest_rank,
        lowest_rank=lowest_rank,
    )