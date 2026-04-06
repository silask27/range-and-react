# File: api/app/models/enums.py
# Summary: Shared enum definitions for players, streets, actions, UI gates, and response-matrix options used throughout the backend.

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-backed enum base class with cleaner string behavior."""

    def __str__(self) -> str:
        return self.value


class Player(StrEnum):
    HERO = "hero"
    VILLAIN = "villain"


class Street(StrEnum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class ActionType(StrEnum):
    CHECK = "check"
    BET = "bet"
    CALL = "call"
    RAISE = "raise"
    FOLD = "fold"


class UIGate(StrEnum):
    HERO_TO_ACT = "hero_to_act"
    MUST_PRUNE_RANGE = "must_prune_range"
    MUST_FILL_RESPONSE_MATRIX = "must_fill_response_matrix"
    HAND_OVER = "hand_over"


class Position(StrEnum):
    BTN = "BTN"
    SB = "SB"
    BB = "BB"
    CO = "CO"
    HJ = "HJ"
    LJ = "LJ"
    UTG = "UTG"


class ResponseColumnType(StrEnum):
    CHECK = "check"
    BET_SMALL = "bet_small"
    BET_BIG = "bet_big"
    CALL = "call"
    RAISE = "raise"


class CheckResponse(StrEnum):
    BET = "B"
    CHECK = "X"


class AggressionResponse(StrEnum):
    FOLD = "F"
    CALL = "C"
    RAISE = "R"


class CallResponse(StrEnum):
    PASSIVE = "P"
    AGGRESSIVE = "A"


class RangeEditMode(StrEnum):
    FULL_EDIT = "full_edit"
    PRUNE_ONLY = "prune_only"

class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    COACH = "coach"
    MEMBER = "member"
