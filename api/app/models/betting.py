# File: api/app/models/betting.py
# Summary: Dataclasses for per-street betting state and action history records used by the hand state and engine layers.

from __future__ import annotations

from dataclasses import dataclass, field

from api.app.models.enums import ActionType, Player, Street


def _round_amount(value: float) -> float:
    return round(float(value or 0.0), 2)


@dataclass
class ActionEvent:
    """
    Immutable-style record of a single applied action in the hand history.
    """

    street: Street
    actor: Player
    action: ActionType
    amount: float = 0.0
    note: str = ""
    forced: bool = False

    def __post_init__(self) -> None:
        self.amount = _round_amount(self.amount)


@dataclass
class BettingRoundState:
    """
    Per-street betting state used to track contributions, current bet size,
    raise sizing, and whether the hand has ended by fold.
    """

    current_bet: float = 0.0
    hero_contrib: float = 0.0
    villain_contrib: float = 0.0
    last_raise_size: float = 0.0
    folded: bool = False

    def __post_init__(self) -> None:
        self.current_bet = _round_amount(self.current_bet)
        self.hero_contrib = _round_amount(self.hero_contrib)
        self.villain_contrib = _round_amount(self.villain_contrib)
        self.last_raise_size = _round_amount(self.last_raise_size)

    def contrib_for(self, player: Player) -> float:
        if player == Player.HERO:
            return self.hero_contrib
        return self.villain_contrib

    def set_contrib_for(self, player: Player, value: float) -> None:
        if player == Player.HERO:
            self.hero_contrib = _round_amount(value)
        else:
            self.villain_contrib = _round_amount(value)

    def to_call_for(self, player: Player) -> float:
        return _round_amount(max(0.0, self.current_bet - self.contrib_for(player)))

    def reset_for_new_street(self) -> None:
        self.current_bet = 0.0
        self.hero_contrib = 0.0
        self.villain_contrib = 0.0
        self.last_raise_size = 0.0
        self.folded = False


@dataclass
class ActionHistory:
    """
    Ordered container of action events for the current hand.
    """

    events: list[ActionEvent] = field(default_factory=list)

    def append(self, event: ActionEvent) -> None:
        self.events.append(event)

    def last(self) -> ActionEvent | None:
        if not self.events:
            return None
        return self.events[-1]
