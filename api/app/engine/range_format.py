# File: api/app/engine/range_format.py
# Summary: Utilities for converting between scenario range tokens and 13x13 matrix hand-label states used by the app.

from __future__ import annotations

from typing import Iterable

MATRIX_RANKS: tuple[str, ...] = ("A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2")
RANK_INDEX: dict[str, int] = {rank: idx for idx, rank in enumerate(MATRIX_RANKS)}


def _validate_rank(rank: str) -> str:
    rank = rank.upper()
    if rank not in RANK_INDEX:
        raise ValueError(f"Invalid rank: {rank!r}")
    return rank


def build_hand_label(row_rank: str, col_rank: str, row_idx: int, col_idx: int) -> str:
    """
    Returns a standard 13x13 matrix hand label:
    - pairs on diagonal: AA
    - suited above diagonal: AKs
    - offsuit below diagonal: AKo
    """
    row_rank = _validate_rank(row_rank)
    col_rank = _validate_rank(col_rank)

    if row_idx == col_idx:
        return f"{row_rank}{col_rank}"
    if row_idx < col_idx:
        return f"{row_rank}{col_rank}s"
    return f"{col_rank}{row_rank}o"


def all_matrix_labels() -> list[str]:
    """Return all 169 canonical 13x13 matrix labels in row-major order."""
    labels: list[str] = []
    for row_idx, row_rank in enumerate(MATRIX_RANKS):
        for col_idx, col_rank in enumerate(MATRIX_RANKS):
            labels.append(build_hand_label(row_rank, col_rank, row_idx, col_idx))
    return labels


def empty_matrix_state(default: bool = False) -> dict[str, bool]:
    """Return a 169-cell matrix mapping hand label -> included bool."""
    return {label: default for label in all_matrix_labels()}


def normalize_exact_label(label: str) -> str:
    """
    Normalize an exact hand label like 'aks', 'AKO', or 'qq' into canonical matrix form.
    """
    raw = label.strip().upper()

    if len(raw) == 2:
        r1, r2 = raw[0], raw[1]
        _validate_rank(r1)
        _validate_rank(r2)
        if r1 != r2:
            raise ValueError(f"Two-character non-pair label is invalid: {label!r}")
        return f"{r1}{r2}"

    if len(raw) != 3:
        raise ValueError(f"Invalid exact hand label: {label!r}")

    r1, r2, suitedness = raw[0], raw[1], raw[2].lower()
    r1 = _validate_rank(r1)
    r2 = _validate_rank(r2)

    if r1 == r2:
        raise ValueError(f"Pairs must not have suitedness suffix: {label!r}")
    if suitedness not in {"s", "o"}:
        raise ValueError(f"Invalid suitedness in label: {label!r}")

    high, low = sorted((r1, r2), key=lambda r: RANK_INDEX[r])
    return f"{high}{low}{suitedness}"


def _expand_pair_plus(token: str) -> set[str]:
    """
    Expand pair-plus notation like 22+ into all pairs from that rank up to AA.
    """
    base_rank = _validate_rank(token[0])
    start_idx = RANK_INDEX[base_rank]
    return {f"{rank}{rank}" for rank in MATRIX_RANKS[: start_idx + 1]}


def _expand_pair_interval(token: str) -> set[str]:
    """
    Expand pair interval notation like 77-QQ or QQ-77.
    """
    left, right = token.split("-")
    if len(left) != 2 or len(right) != 2 or left[0] != left[1] or right[0] != right[1]:
        raise ValueError(f"Invalid pair interval token: {token!r}")

    left_rank = _validate_rank(left[0])
    right_rank = _validate_rank(right[0])

    left_idx = RANK_INDEX[left_rank]
    right_idx = RANK_INDEX[right_rank]
    lo_idx, hi_idx = min(left_idx, right_idx), max(left_idx, right_idx)

    return {f"{rank}{rank}" for rank in MATRIX_RANKS[lo_idx : hi_idx + 1]}


def _expand_nonpair_plus(token: str) -> set[str]:
    """
    Expand suited/offsuit plus notation like:
    - A2s+ -> A2s, A3s, ..., AKs
    - K5s+ -> K5s, K6s, ..., KQs
    - A7o+ -> A7o, A8o, ..., AKo
    - T8s+ -> T8s, T9s
    """
    if len(token) != 4 or token[3] != "+":
        raise ValueError(f"Invalid plus token: {token!r}")

    r1 = _validate_rank(token[0])
    r2 = _validate_rank(token[1])
    suitedness = token[2].lower()

    if suitedness not in {"s", "o"}:
        raise ValueError(f"Invalid suitedness in plus token: {token!r}")
    if r1 == r2:
        raise ValueError(f"Pair plus tokens should use pair notation: {token!r}")

    top_idx = RANK_INDEX[r1]
    low_idx = RANK_INDEX[r2]
    if top_idx >= low_idx:
        raise ValueError(f"Invalid plus token ordering: {token!r}")

    out: set[str] = set()
    for idx in range(low_idx, top_idx, -1):
        kicker = MATRIX_RANKS[idx]
        out.add(f"{r1}{kicker}{suitedness}")
    return out


def _expand_nonpair_interval(token: str) -> set[str]:
    """
    Expand suited/offsuit interval notation like:
    - A2s-AJs
    - KTo-KQo
    - A5s-A4s

    Both ends must share the same first rank and same suitedness.
    Endpoint order may be ascending or descending; expansion is inclusive.
    """
    left, right = token.split("-")
    if len(left) != 3 or len(right) != 3:
        raise ValueError(f"Invalid non-pair interval token: {token!r}")

    r1_left = _validate_rank(left[0])
    r2_left = _validate_rank(left[1])
    suit_left = left[2].lower()

    r1_right = _validate_rank(right[0])
    r2_right = _validate_rank(right[1])
    suit_right = right[2].lower()

    if suit_left not in {"s", "o"} or suit_right not in {"s", "o"}:
        raise ValueError(f"Invalid suitedness in non-pair interval token: {token!r}")
    if r1_left != r1_right or suit_left != suit_right:
        raise ValueError(f"Mismatched interval endpoints: {token!r}")
    if r1_left == r2_left or r1_right == r2_right:
        raise ValueError(f"Non-pair interval cannot contain pairs: {token!r}")

    top_rank = r1_left
    top_idx = RANK_INDEX[top_rank]
    left_idx = RANK_INDEX[r2_left]
    right_idx = RANK_INDEX[r2_right]

    if top_idx >= left_idx or top_idx >= right_idx:
        raise ValueError(f"Invalid non-pair interval token: {token!r}")

    lo_idx, hi_idx = min(left_idx, right_idx), max(left_idx, right_idx)

    out: set[str] = set()
    for idx in range(lo_idx, hi_idx + 1):
        kicker = MATRIX_RANKS[idx]
        out.add(f"{top_rank}{kicker}{suit_left}")
    return out


def expand_range_token(token: str) -> set[str]:
    """
    Expand a single range token into a set of exact 13x13 hand labels.

    Supported formats:
    - exact pair: AA
    - exact non-pair: AKs, AKo
    - pair plus: 22+
    - pair interval: 77-QQ, QQ-77
    - non-pair plus: A2s+, K5s+, A7o+
    - non-pair interval: A2s-AJs, KTo-KQo, A5s-A4s
    """
    token = token.strip()
    if not token:
        return set()

    if token.endswith("+") and len(token) == 3 and token[0] == token[1]:
        return _expand_pair_plus(token)

    if "-" in token and len(token) == 5 and token[0] == token[1] and token[3] == token[4]:
        return _expand_pair_interval(token)

    if token.endswith("+") and len(token) == 4:
        return _expand_nonpair_plus(token)

    if "-" in token and len(token) == 7:
        return _expand_nonpair_interval(token)

    return {normalize_exact_label(token)}


def expand_range_tokens(tokens: Iterable[str]) -> set[str]:
    """Expand many range tokens into a deduplicated set of exact matrix labels."""
    out: set[str] = set()
    for token in tokens:
        out.update(expand_range_token(token))
    return out


def matrix_state_from_tokens(tokens: Iterable[str]) -> dict[str, bool]:
    """
    Convert range tokens into a full 169-cell matrix state where included hands are True.
    """
    included = expand_range_tokens(tokens)
    state = empty_matrix_state(default=False)
    for label in included:
        if label not in state:
            raise ValueError(f"Expanded label not present in matrix: {label}")
        state[label] = True
    return state


def exact_tokens_from_matrix_state(matrix_state: dict[str, bool]) -> list[str]:
    """
    Convert a matrix state into sorted exact included hand labels.

    Note: this intentionally returns exact labels rather than compressed range syntax.
    That keeps the backend simple and lossless for now.
    """
    included = [label for label, is_included in matrix_state.items() if is_included]
    return sorted(included, key=lambda label: (len(label), label))


def included_labels(matrix_state: dict[str, bool]) -> set[str]:
    """Return the set of currently included exact hand labels from a matrix state."""
    return {label for label, is_included in matrix_state.items() if is_included}