# File: api/app/services/reveal_service.py
# Summary: Service-layer helper for revealing villain hole cards after the hand is over.

from __future__ import annotations

from api.app.models.enums import UIGate
from api.app.models.state import HandState
from api.app.storage.memory_store import store


def _hand_from_store(hand_id: str) -> HandState:
    payload = store.get_hand(hand_id)
    if payload is None:
        raise ValueError(f"Unknown hand_id: {hand_id}")
    return HandState(**payload)


def reveal_villain_hand(hand_id: str) -> dict:
    """
    Reveal villain hole cards only after the hand is over.
    """
    hand = _hand_from_store(hand_id)

    if not hand.hand_over and hand.ui_gate != UIGate.HAND_OVER:
        raise ValueError(
            f"Hand {hand_id} is not over yet; villain hand cannot be revealed"
        )

    return {
        "hand_id": hand.hand_id,
        "session_id": hand.session_id,
        "street": hand.street.value,
        "hero_hand": list(hand.hero_hand),
        "villain_hand": list(hand.villain_hand),
        "board": list(hand.board),
        "pot": hand.pot,
        "hero_stack": hand.hero_stack,
        "villain_stack": hand.villain_stack,
        "hand_over": hand.hand_over,
        "history": [
            {
                "street": event.street.value,
                "actor": event.actor.value,
                "action": event.action.value,
                "amount": event.amount,
                "note": event.note,
                "forced": event.forced,
            }
            for event in hand.history.events
        ],
    }