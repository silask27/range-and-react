# File: api/app/engine/dealing.py
# Summary: Utilities for expanding hand labels into concrete combos and sampling legal hole cards from saved ranges while respecting card removal.

from __future__ import annotations

import random
from itertools import combinations
from typing import Iterable

from api.app.engine.cards import SUITS, ensure_unique_cards, normalize_card
from api.app.engine.range_format import normalize_exact_label


def _pair_combos(rank: str) -> list[tuple[str, str]]:
    cards = [f"{rank}{suit}" for suit in SUITS]
    return [tuple(combo) for combo in combinations(cards, 2)]


def _suited_combos(high_rank: str, low_rank: str) -> list[tuple[str, str]]:
    return [(f"{high_rank}{suit}", f"{low_rank}{suit}") for suit in SUITS]


def _offsuit_combos(high_rank: str, low_rank: str) -> list[tuple[str, str]]:
    combos: list[tuple[str, str]] = []
    for suit_a in SUITS:
        for suit_b in SUITS:
            if suit_a == suit_b:
                continue
            combos.append((f"{high_rank}{suit_a}", f"{low_rank}{suit_b}"))
    return combos


def expand_exact_label_to_combos(label: str) -> list[tuple[str, str]]:
    """
    Expand a canonical exact hand label into all concrete 2-card combos.

    Examples:
    - AA  -> 6 combos
    - AKs -> 4 combos
    - AKo -> 12 combos
    """
    label = normalize_exact_label(label)

    if len(label) == 2:
        return _pair_combos(label[0])

    high_rank, low_rank, suitedness = label[0], label[1], label[2]
    if suitedness == "s":
        return _suited_combos(high_rank, low_rank)
    return _offsuit_combos(high_rank, low_rank)


def combo_is_unblocked(
    combo: tuple[str, str],
    excluded_cards: Iterable[str] | None = None,
) -> bool:
    """
    Return True if neither card in the combo appears in excluded_cards.
    """
    excluded = {normalize_card(card) for card in (excluded_cards or [])}
    a, b = combo
    return normalize_card(a) not in excluded and normalize_card(b) not in excluded


def available_combos_for_label(
    label: str,
    excluded_cards: Iterable[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Return all legal concrete combos for an exact hand label after card removal.
    """
    combos = expand_exact_label_to_combos(label)
    return [combo for combo in combos if combo_is_unblocked(combo, excluded_cards)]


def available_combos_for_labels(
    labels: Iterable[str],
    excluded_cards: Iterable[str] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """
    Return legal concrete combos for each exact label after card removal.
    """
    excluded = list(excluded_cards or [])
    return {
        normalize_exact_label(label): available_combos_for_label(label, excluded)
        for label in labels
    }


def sample_combo_from_label(
    label: str,
    excluded_cards: Iterable[str] | None = None,
    rng: random.Random | None = None,
) -> tuple[str, str]:
    """
    Randomly sample one legal combo from an exact hand label.
    Raises ValueError if no legal combos remain.
    """
    rng = rng or random
    combos = available_combos_for_label(label, excluded_cards)
    if not combos:
        raise ValueError(f"No legal combos available for label {label!r}")
    return rng.choice(combos)


def sample_combo_from_labels(
    labels: Iterable[str],
    excluded_cards: Iterable[str] | None = None,
    rng: random.Random | None = None,
) -> tuple[str, str]:
    """
    Randomly sample one legal combo from a set of exact labels, weighting each
    concrete combo equally across the full range.
    """
    rng = rng or random
    combo_pool: list[tuple[str, str]] = []

    for label in labels:
        combo_pool.extend(available_combos_for_label(label, excluded_cards))

    if not combo_pool:
        raise ValueError("No legal combos available from provided labels")

    return rng.choice(combo_pool)


def sample_hero_and_villain_hands(
    hero_labels: Iterable[str],
    villain_labels: Iterable[str],
    rng: random.Random | None = None,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """
    Sample legal hero and villain hole-card combos from their respective exact-label ranges.
    Villain sampling respects hero card removal.
    """
    rng = rng or random

    hero_combo = sample_combo_from_labels(hero_labels, excluded_cards=None, rng=rng)
    villain_combo = sample_combo_from_labels(
        villain_labels,
        excluded_cards=hero_combo,
        rng=rng,
    )

    ensure_unique_cards([*hero_combo, *villain_combo])
    return hero_combo, villain_combo