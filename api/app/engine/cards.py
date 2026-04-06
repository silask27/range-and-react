# File: api/app/engine/cards.py
# Summary: Card utility functions for validating, normalizing, and working with a standard 52-card deck throughout the backend.

from __future__ import annotations

from itertools import combinations

RANKS: tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
SUITS: tuple[str, ...] = ("c", "d", "h", "s")

RANK_TO_VALUE: dict[str, int] = {rank: index + 2 for index, rank in enumerate(RANKS)}
VALUE_TO_RANK: dict[int, str] = {value: rank for rank, value in RANK_TO_VALUE.items()}


def all_cards() -> list[str]:
    """Return a full 52-card deck using rank+suit strings like 'As' and 'Td'."""
    return [f"{rank}{suit}" for rank in RANKS for suit in SUITS]


def normalize_card(card: str) -> str:
    """Normalize a card string into canonical rank+suit format like 'As' or 'Td'."""
    card = card.strip()
    if len(card) != 2:
        raise ValueError(f"Invalid card format: {card!r}")

    rank = card[0].upper()
    suit = card[1].lower()

    if rank not in RANK_TO_VALUE:
        raise ValueError(f"Invalid card rank: {rank!r}")
    if suit not in SUITS:
        raise ValueError(f"Invalid card suit: {suit!r}")

    return f"{rank}{suit}"


def validate_card(card: str) -> None:
    """Raise ValueError if the input is not a valid canonical card string."""
    normalize_card(card)


def normalize_cards(cards: list[str] | tuple[str, ...]) -> list[str]:
    """Normalize a sequence of cards and preserve input order."""
    return [normalize_card(card) for card in cards]


def ensure_unique_cards(cards: list[str] | tuple[str, ...]) -> list[str]:
    """Normalize a sequence of cards and raise if any duplicate card appears."""
    normalized = normalize_cards(cards)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"Duplicate cards detected: {normalized}")
    return normalized


def card_rank(card: str) -> str:
    """Return the rank character for a card."""
    return normalize_card(card)[0]


def card_suit(card: str) -> str:
    """Return the suit character for a card."""
    return normalize_card(card)[1]


def card_value(card: str) -> int:
    """Return the numeric value of a card rank, where Ace is high."""
    return RANK_TO_VALUE[card_rank(card)]


def sort_cards_desc(cards: list[str] | tuple[str, ...]) -> list[str]:
    """Return cards sorted by descending rank value, then suit."""
    normalized = normalize_cards(cards)
    return sorted(normalized, key=lambda c: (card_value(c), card_suit(c)), reverse=True)


def available_deck(excluded_cards: list[str] | tuple[str, ...] | None = None) -> list[str]:
    """Return the deck with any excluded cards removed."""
    excluded = set(ensure_unique_cards(excluded_cards or []))
    return [card for card in all_cards() if card not in excluded]


def two_card_combos_from_deck(
    excluded_cards: list[str] | tuple[str, ...] | None = None,
) -> list[tuple[str, str]]:
    """Return all unordered two-card combinations from the remaining deck."""
    deck = available_deck(excluded_cards)
    return list(combinations(deck, 2))