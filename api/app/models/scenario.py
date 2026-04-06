# File: api/app/models/scenario.py
# Summary: Data model for preflop scenarios, including positions, aggressor, default pot, and default hero/villain starting ranges.

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from api.app.models.enums import Player, Position


@dataclass(frozen=True)
class Scenario:
    """
    Canonical preflop scenario definition used to initialize a training session.
    """

    id: str
    display_name: str
    description: str

    hero_position: Position
    villain_position: Position
    hero_is_ip: bool
    preflop_aggressor: Player

    default_pot: float
    hero_range_tokens: Tuple[str, ...]
    villain_range_tokens: Tuple[str, ...]
    hero_scenario_name: str
    villain_scenario_name: str
    hero_action_bubble: str
    villain_action_bubble: str
    non_aggressor_previous_action: str | None
    players_not_folded_hero_action: Tuple[str, ...]
    players_not_folded_villain_action: Tuple[str, ...]

    @property
    def oop_player(self) -> Player:
        """
        Return the player who is out of position postflop and therefore acts first.
        """
        return Player.VILLAIN if self.hero_is_ip else Player.HERO

    @property
    def ip_player(self) -> Player:
        """
        Return the player who is in position postflop and therefore acts second.
        """
        return Player.HERO if self.hero_is_ip else Player.VILLAIN

    @property
    def first_to_act_postflop(self) -> Player:
        """
        Return the first actor on postflop streets.
        """
        return self.oop_player