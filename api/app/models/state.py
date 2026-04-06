# File: api/app/models/state.py
# Summary: Dataclasses for persistent session state and live hand state used throughout
# the training flow, including subgroup-aware prune snapshots for Screen 3.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.app.models.betting import ActionHistory, BettingRoundState
from api.app.models.enums import Player, Street, UIGate


# Broad bucket -> subgroup -> label -> live combo cards
# Example:
# {
#   "SDV": {
#       "Top Pair": {
#           "QJs": [["Qh", "Jh"], ["Qs", "Js"]],
#       },
#       "Mid Pair": {
#           "TT": [["Tc", "Td"]],
#       },
#   },
# }
PruneBucketSnapshot = dict[str, dict[str, dict[str, list[list[str]]]]]


@dataclass
class SessionState:
    """
    Persistent state created after villain selection and enriched on Screen 2.

    This state survives across screens and stores the selected villain, selected
    scenario, generated stack sizes, default pot, the selected Train-mode timer,
    and the saved starting hero and villain range matrices that will seed the hand
    on Screen 3.
    """

    session_id: str
    user_id: str
    villain_profile_id: str

    # Train-mode timer selection persisted across Screen 1 -> Screen 3.
    # None means no Train timer has been set yet.
    # 0 means Train timer is explicitly Off.
    # Positive values represent countdown seconds (10 / 30 / 60).
    train_timer_seconds: int | None = None

    scenario_id: str | None = None

    pot: float | None = None
    hero_stack: float | None = None
    villain_stack: float | None = None

    hero_range_matrix_saved: dict[str, Any] | None = None
    hero_tokens_saved: list[str] = field(default_factory=list)

    villain_range_matrix_saved: dict[str, Any] | None = None
    villain_tokens_saved: list[str] = field(default_factory=list)

    hero_range_confirmed: bool = False
    villain_range_confirmed: bool = False

    def is_ready_for_hand_start(self) -> bool:
        return (
            self.scenario_id is not None
            and self.pot is not None
            and self.hero_stack is not None
            and self.villain_stack is not None
            and self.hero_range_matrix_saved is not None
            and self.villain_range_matrix_saved is not None
            and self.hero_range_confirmed
            and self.villain_range_confirmed
        )


@dataclass
class HandState:
    """
    Live postflop hand state for Screen 3.

    This is the canonical backend state object for the active hand, including:
    board cards, hole cards, action history, betting round, saved hero range,
    live villain range, actor turn state, UI gating, response-matrix state, and prune bookkeeping.
    """

    hand_id: str
    session_id: str
    user_id: str
    scenario_id: str
    villain_profile_id: str

    pot: float
    hero_stack: float
    villain_stack: float

    hero_hand: tuple[str, str]
    villain_hand: tuple[str, str]
    board: list[str]

    street: Street
    betting_round: BettingRoundState = field(default_factory=BettingRoundState)
    history: ActionHistory = field(default_factory=ActionHistory)

    hero_tokens_saved: list[str] = field(default_factory=list)

    villain_range_matrix_saved: dict[str, Any] | None = None
    villain_range_combos_live: dict[str, list[list[str]]] = field(default_factory=dict)
    current_actor: Player = Player.HERO
    current_aggressor: Player | None = None
    ui_gate: UIGate = UIGate.HERO_TO_ACT
    hand_over: bool = False

    # Stable per-hand seed used whenever bucket rows are regenerated.
    # This prevents bucket rows / prune rows from reshuffling across requests.
    bucket_seed: int = 42

    response_matrix_columns: list[str] = field(default_factory=list)
    response_matrix_saved: dict[str, Any] = field(default_factory=dict)

    prune_row_order: list[str] = field(default_factory=list)
    prune_row_index: int = 0

    # Full-range snapshot captured when the current prune node begins.
    # Used as the baseline for bucket re-computation and revert behavior.
    prune_range_snapshot: dict[str, list[list[str]]] = field(default_factory=dict)

    # Row-level snapshots captured at the beginning of prune mode.
    # Updated shape:
    # {
    #   "SDV": {
    #       "Top Pair": {
    #           "QJs": [["Qh", "Jh"], ...],
    #       },
    #       "Mid Pair": {
    #           "TT": [["Tc", "Td"], ...],
    #       },
    #   },
    #   ...
    # }
    prune_row_originals: PruneBucketSnapshot = field(default_factory=dict)

    # Last saved row versions for the current prune node.
    # Initially this will usually match prune_row_originals.
    # Revert should restore to this saved version.
    prune_row_saved_versions: PruneBucketSnapshot = field(default_factory=dict)

    def stack_for(self, player: Player) -> float:
        if player == Player.HERO:
            return self.hero_stack
        return self.villain_stack

    def set_stack_for(self, player: Player, value: float) -> None:
        if player == Player.HERO:
            self.hero_stack = value
        else:
            self.villain_stack = value

    def next_prune_bucket(self) -> str | None:
        if self.prune_row_index >= len(self.prune_row_order):
            return None
        return self.prune_row_order[self.prune_row_index]

    def advance_prune_row(self) -> None:
        if self.prune_row_index < len(self.prune_row_order):
            self.prune_row_index += 1

    def all_prune_rows_complete(self) -> bool:
        return self.prune_row_index >= len(self.prune_row_order)

    def current_prune_row_saved_version(self) -> dict[str, dict[str, list[list[str]]]] | None:
        bucket_name = self.next_prune_bucket()
        if bucket_name is None:
            return None
        return self.prune_row_saved_versions.get(bucket_name)

    def current_prune_row_original(self) -> dict[str, dict[str, list[list[str]]]] | None:
        bucket_name = self.next_prune_bucket()
        if bucket_name is None:
            return None
        return self.prune_row_originals.get(bucket_name)