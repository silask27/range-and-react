# File: api/app/services/prune_service.py
# Summary: Service-layer helpers for initializing row-by-row prune mode and applying
# subgroup-level remove, revert, and save actions to the live villain range.

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import fields
import random
from api.app.data.catalog import get_scenario
from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.engine.cards import available_deck
from api.app.engine.villain_decision import choose_villain_action
from api.app.models.betting import ActionEvent
from api.app.models.enums import ActionType, Player, ResponseColumnType, Street, UIGate
from api.app.models.state import HandState, PruneBucketSnapshot
from api.app.models.villain_profile import DecisionNode
from api.app.storage.memory_store import store
from api.app.services.scoring_service import record_prune_evaluation
from api.app.services.response_matrix_prefill import prepare_response_matrix_for_new_node


AGGRESSIVE_ACTIONS = {ActionType.BET, ActionType.RAISE}
PruneEvaluationScheduler = Callable[[HandState], None]


def _hand_to_store_payload(hand: HandState) -> dict:
    """
    Store a shallow field mapping so nested dataclasses remain typed objects.
    """
    return {f.name: getattr(hand, f.name) for f in fields(HandState)}



def _hand_from_store(hand_id: str) -> HandState:
    payload = store.get_hand(hand_id)
    if payload is None:
        raise ValueError(f"Unknown hand_id: {hand_id}")
    return HandState(**payload)


def _record_or_schedule_prune_evaluation(
    hand: HandState,
    *,
    iters: int | None,
    schedule_prune_evaluation: PruneEvaluationScheduler | None,
) -> None:
    if schedule_prune_evaluation is None:
        record_prune_evaluation(hand, iters=iters)
        return

    schedule_prune_evaluation(deepcopy(hand))



def _deepcopy_combo_map(combo_map: dict[str, list[list[str]]]) -> dict[str, list[list[str]]]:
    return {
        label: [list(combo) for combo in combos]
        for label, combos in combo_map.items()
    }



def _deepcopy_prune_snapshot(snapshot: PruneBucketSnapshot) -> PruneBucketSnapshot:
    out: PruneBucketSnapshot = {}
    for bucket_name, subgroup_map in snapshot.items():
        out[bucket_name] = {}
        for subgroup_name, label_map in subgroup_map.items():
            out[bucket_name][subgroup_name] = _deepcopy_combo_map(label_map)
    return out



def _sorted_combo_lists(combos: list[list[str]]) -> list[list[str]]:
    return sorted([list(combo) for combo in combos], key=lambda combo: (combo[0], combo[1]))



def _build_bucket_view_for_hand(
    hand: HandState,
    *,
    iters: int | None,
) -> dict:
    """
    Always rebuild the current bucket view using hand.bucket_seed so the UI and backend
    stay locked to the same deterministic row/subgroup structure for this hand state.

    If iters is omitted, build_bucket_matrix_view falls back to the street-specific
    defaults defined in bucketizer.py.
    """
    return build_bucket_matrix_view(
        villain_range_combos_live=hand.villain_range_combos_live,
        board=hand.board,
        hero_hand=hand.hero_hand,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        iters=iters,
        seed=int(hand.bucket_seed),
    )



def _row_snapshot_from_bucket_view(bucket_view: dict) -> PruneBucketSnapshot:
    """
    Convert bucket rows into a subgroup-aware snapshot map.

    Structure:
    {
        "SDV": {
            "Top Pair": {
                "QJs": [["Qh", "Jh"], ["Qs", "Js"]],
            },
        },
    }
    """
    out: PruneBucketSnapshot = {}

    for row in bucket_view["rows"]:
        bucket_name = row["bucket_name"]
        subgroup_snapshot: dict[str, dict[str, list[list[str]]]] = {}

        for subgroup in row.get("subgroups", []):
            subgroup_name = subgroup["subgroup_name"]
            label_map: dict[str, list[list[str]]] = {}

            for hand_entry in subgroup.get("hands", []):
                combo_cards = _sorted_combo_lists(hand_entry.get("combo_cards", []))
                if combo_cards:
                    label_map[hand_entry["label"]] = combo_cards

            if label_map:
                subgroup_snapshot[subgroup_name] = label_map

        if subgroup_snapshot:
            out[bucket_name] = subgroup_snapshot

    return out



def _response_columns_for_current_hero_node(hand: HandState) -> list[str]:
    to_call = hand.betting_round.to_call_for(Player.HERO)
    if to_call > 0:
        return [
            ResponseColumnType.CALL.value,
            ResponseColumnType.RAISE.value,
        ]
    return [
        ResponseColumnType.CHECK.value,
        ResponseColumnType.BET_SMALL.value,
        ResponseColumnType.BET_BIG.value,
    ]



def _clear_response_matrix_node_state(hand: HandState) -> None:
    hand.response_matrix_saved = {}



def _clear_prune_state(hand: HandState) -> None:
    hand.prune_row_order = []
    hand.prune_row_index = 0
    hand.prune_range_snapshot = {}
    hand.prune_row_originals = {}
    hand.prune_row_saved_versions = {}



def _set_hero_response_matrix_gate(
    hand: HandState,
    *,
    iters: int | None = None,
) -> None:
    hand.current_actor = Player.HERO
    hand.ui_gate = UIGate.MUST_FILL_RESPONSE_MATRIX
    hand.response_matrix_columns = _response_columns_for_current_hero_node(hand)
    prepare_response_matrix_for_new_node(hand, iters=iters)
    _clear_prune_state(hand)



def _set_hand_over(hand: HandState) -> None:
    hand.hand_over = True
    hand.ui_gate = UIGate.HAND_OVER
    hand.response_matrix_columns = []
    _clear_response_matrix_node_state(hand)
    _clear_prune_state(hand)



def _set_prune_gate_for_hero(
    hand: HandState,
    *,
    iters: int | None,
) -> None:
    """
    Put the hand into prune mode immediately after a normal villain action
    that should be pruned.

    If iters is omitted, prune initialization uses the street-specific defaults
    defined in bucketizer.py.
    """
    hand.current_actor = Player.HERO
    hand.ui_gate = UIGate.MUST_PRUNE_RANGE
    hand.response_matrix_columns = _response_columns_for_current_hero_node(hand)
    _clear_prune_state(hand)
    initialize_prune_state(hand, iters=iters)

    # If nothing exists to prune, continue the flow immediately.
    if not hand.prune_row_order:
        _continue_after_completed_prune(hand, iters=iters)



def _street_events(hand: HandState) -> list[ActionEvent]:
    return [event for event in hand.history.events if event.street == hand.street]



def _latest_villain_street_event(hand: HandState) -> ActionEvent | None:
    for event in reversed(hand.history.events):
        if event.street == hand.street and event.actor == Player.VILLAIN:
            return event
    return None



def _final_aggressor_for_street(hand: HandState) -> Player | None:
    last_aggressor: Player | None = None
    for event in _street_events(hand):
        if event.action in AGGRESSIVE_ACTIONS:
            last_aggressor = event.actor
    return last_aggressor



def _street_is_complete(hand: HandState) -> bool:
    if hand.betting_round.folded:
        return True

    events = _street_events(hand)
    if len(events) < 2:
        return False

    any_aggression = any(
        event.action in AGGRESSIVE_ACTIONS
        for event in events
    )

    if not any_aggression:
        return (
            events[-2].action == ActionType.CHECK
            and events[-1].action == ActionType.CHECK
        )

    return events[-1].action in {ActionType.CALL, ActionType.FOLD}



def _deal_next_board_card(hand: HandState, rng: random.Random) -> str:
    excluded = [*hand.hero_hand, *hand.villain_hand, *hand.board]
    deck = available_deck(excluded)
    return rng.choice(deck)



def _filter_live_range_for_blockers(hand: HandState) -> None:
    blocked = set([*hand.hero_hand, *hand.board])
    filtered: dict[str, list[list[str]]] = {}

    for label, combos in hand.villain_range_combos_live.items():
        legal = []
        for combo in combos:
            if combo[0] in blocked or combo[1] in blocked:
                continue
            legal.append([combo[0], combo[1]])

        if legal:
            filtered[label] = legal

    hand.villain_range_combos_live = filtered



def _decision_note(decision) -> str:
    return f"Villain {decision.note}"



def _count_aggressive_actions(
    hand: HandState,
    *,
    actor: Player,
    include_current_street: bool = True,
) -> int:
    total = 0
    for event in hand.history.events:
        if event.forced:
            continue
        if event.actor != actor:
            continue
        if event.action not in AGGRESSIVE_ACTIONS:
            continue
        if not include_current_street and event.street == hand.street:
            continue
        total += 1
    return total



def _last_non_forced_aggressive_event_for_street(hand: HandState) -> ActionEvent | None:
    for event in reversed(_street_events(hand)):
        if event.forced:
            continue
        if event.action in AGGRESSIVE_ACTIONS:
            return event
    return None



def _villain_node_hint_for_current_spot(hand: HandState) -> DecisionNode | None:
    to_call = hand.betting_round.to_call_for(Player.VILLAIN)
    if to_call <= 0:
        return "unopened"

    last_aggressive_event = _last_non_forced_aggressive_event_for_street(hand)
    if last_aggressive_event is None:
        return None

    if (
        last_aggressive_event.actor == Player.HERO
        and last_aggressive_event.action == ActionType.RAISE
    ):
        return "facing_raise"

    return None



def _choose_villain_action_for_hand(
    hand: HandState,
    *,
    scenario,
    can_raise: bool,
    seed: int,
    iters: int | None,
):
    return choose_villain_action(
        villain_hand=hand.villain_hand,
        board=hand.board,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        street=hand.street,
        to_call=hand.betting_round.to_call_for(Player.VILLAIN),
        pot=hand.pot,
        can_raise=can_raise,
        iters=iters,
        seed=seed,
        node_hint=_villain_node_hint_for_current_spot(hand),
        villain_is_current_aggressor=(hand.current_aggressor == Player.VILLAIN),
        villain_is_pfa=(scenario.preflop_aggressor == Player.VILLAIN),
        prior_villain_aggressive_actions=_count_aggressive_actions(
            hand,
            actor=Player.VILLAIN,
        ),
        prior_hero_aggressive_actions=_count_aggressive_actions(
            hand,
            actor=Player.HERO,
        ),
        scenario_id=hand.scenario_id,
        villain_is_ip=(not scenario.hero_is_ip),
        history_events=hand.history.events,
        effective_stack_size=hand.villain_stack,
    )




def _fallback_bet_frac(street: Street) -> float:
    if street == Street.RIVER:
        return 0.70
    if street == Street.TURN:
        return 0.65
    return 0.60



def _resolve_villain_bet_amount(
    *,
    pot: float,
    street: Street,
    villain_stack: float,
    chosen_frac: float | None,
) -> float:
    frac = float(chosen_frac) if chosen_frac is not None else _fallback_bet_frac(street)
    frac = max(0.05, frac)
    raw = round(max(1.0, pot * frac), 2)
    return round(min(raw, villain_stack), 2)



def _node_seed(hand: HandState, offset: int = 0) -> int:
    return int(hand.bucket_seed) + len(hand.history.events) * 97 + offset



def _advance_to_next_street(
    hand: HandState,
) -> None:
    """
    Advance the hand one street, deal the next board card, and reset betting state.
    """
    previous_street_aggressor = _final_aggressor_for_street(hand)

    if hand.street == Street.FLOP:
        next_street = Street.TURN
    elif hand.street == Street.TURN:
        next_street = Street.RIVER
    else:
        raise ValueError(f"Cannot advance street from {hand.street}")

    rng = random.Random(_node_seed(hand, offset=11))
    next_card = _deal_next_board_card(hand, rng)
    hand.board.append(next_card)
    _filter_live_range_for_blockers(hand)

    hand.street = next_street
    hand.betting_round.reset_for_new_street()
    hand.current_aggressor = previous_street_aggressor
    _clear_prune_state(hand)



def _resolve_street_start_after_advance(
    hand: HandState,
    *,
    iters: int | None,
) -> None:
    """
    After a street advance, resolve whoever acts first on the new street.

    This preserves the main app flow while using the predictive model:
    - hero first -> matrix
    - villain first -> villain acts immediately and that action is then pruned
    """
    scenario = get_scenario(hand.scenario_id)
    first_actor = scenario.first_to_act_postflop

    if first_actor == Player.HERO:
        _set_hero_response_matrix_gate(hand, iters=iters)
        return

    decision = _choose_villain_action_for_hand(
        hand,
        scenario=scenario,
        can_raise=False,
        seed=_node_seed(hand, offset=23),
        iters=iters,
    )

    note = _decision_note(decision)

    if decision.action == ActionType.CHECK:
        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.VILLAIN,
                action=ActionType.CHECK,
                amount=0.0,
                note=f"{note} checked",
                forced=False,
            )
        )
        _set_prune_gate_for_hero(hand, iters=iters)
        return

    if decision.action == ActionType.BET:
        amount = _resolve_villain_bet_amount(
            pot=hand.pot,
            street=hand.street,
            villain_stack=hand.villain_stack,
            chosen_frac=decision.bet_size_frac,
        )

        hand.villain_stack = round(hand.villain_stack - amount, 2)
        hand.pot = round(hand.pot + amount, 2)
        hand.betting_round.current_bet = amount
        hand.betting_round.villain_contrib = amount
        hand.betting_round.last_raise_size = amount
        hand.current_aggressor = Player.VILLAIN

        size_note = (
            f" ({decision.bet_size_key}, {round(float(decision.bet_size_frac or 0.0), 2)} pot)"
            if decision.bet_size_key is not None
            else ""
        )

        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.VILLAIN,
                action=ActionType.BET,
                amount=amount,
                note=f"{note} bet{size_note}",
                forced=False,
            )
        )
        _set_prune_gate_for_hero(hand, iters=iters)
        return

    raise ValueError(
        f"Invalid immediate villain street-start action after advance: {decision.action}"
    )



def _continue_after_completed_prune(
    hand: HandState,
    *,
    iters: int | None,
) -> None:
    """
    Continue the game flow after the final prune row is saved.

    Desired flow:
    - villain CHECK:
        - if check/check ended the street -> advance street / end hand
        - otherwise hero acts on same street -> matrix
    - villain CALL:
        - street is complete -> advance street / end hand
    - villain BET / RAISE:
        - hero acts on same street -> matrix
    - villain FOLD:
        - hand over (should normally not reach prune, but safe fallback)
    """
    latest_villain_event = _latest_villain_street_event(hand)
    _clear_prune_state(hand)

    if latest_villain_event is None:
        _set_hero_response_matrix_gate(hand, iters=iters)
        return

    if latest_villain_event.action == ActionType.FOLD:
        _set_hand_over(hand)
        return

    if latest_villain_event.action in {ActionType.BET, ActionType.RAISE}:
        _set_hero_response_matrix_gate(hand, iters=iters)
        return

    if latest_villain_event.action == ActionType.CALL:
        if hand.street == Street.RIVER:
            _set_hand_over(hand)
            return

        _advance_to_next_street(hand)
        _resolve_street_start_after_advance(hand, iters=iters)
        return

    if latest_villain_event.action == ActionType.CHECK:
        if _street_is_complete(hand):
            if hand.street == Street.RIVER:
                _set_hand_over(hand)
                return

            _advance_to_next_street(hand)
            _resolve_street_start_after_advance(hand, iters=iters)
            return

        _set_hero_response_matrix_gate(hand, iters=iters)
        return

    _set_hero_response_matrix_gate(hand, iters=iters)



def initialize_prune_state(
    hand: HandState,
    *,
    iters: int | None = None,
    bucket_view_snapshot: dict | None = None,
) -> None:
    """
    Initialize row-by-row prune state directly on an in-memory hand object.

    This captures:
    - the full live-range snapshot at prune start
    - the locked broad-bucket row order for this prune pass
    - the original and saved subgroup-aware versions of each row

    If iters is omitted, bucketization uses the street-specific defaults defined
    in bucketizer.py.
    """
    bucket_view = bucket_view_snapshot or _build_bucket_view_for_hand(hand, iters=iters)
    row_order = [
        row["bucket_name"]
        for row in sorted(
            bucket_view["rows"],
            key=lambda row: (
                -float(row.get("bucket_percent", 0.0)),
                -int(row.get("combo_count", 0)),
                row["bucket_name"],
            ),
        )
    ]
    row_snapshots = _row_snapshot_from_bucket_view(bucket_view)

    hand.prune_range_snapshot = _deepcopy_combo_map(hand.villain_range_combos_live)
    hand.prune_row_order = row_order
    hand.prune_row_index = 0
    hand.prune_row_originals = _deepcopy_prune_snapshot(row_snapshots)
    hand.prune_row_saved_versions = _deepcopy_prune_snapshot(row_snapshots)



def _current_row_draft(
    hand: HandState,
    bucket_name: str,
) -> dict[str, dict[str, list[list[str]]]]:
    """
    Return the current live draft for one prune row.

    Membership is anchored to the original row snapshot captured at prune start,
    so removing one subgroup from this row never touches same-label combos that
    started in a different subgroup or broad bucket.
    """
    original_row = hand.prune_row_originals.get(bucket_name, {})
    live = hand.villain_range_combos_live

    out: dict[str, dict[str, list[list[str]]]] = {}
    for subgroup_name, label_map in original_row.items():
        subgroup_out: dict[str, list[list[str]]] = {}

        for label, original_combos in label_map.items():
            allowed = {tuple(combo) for combo in original_combos}
            live_row_combos = [
                list(combo)
                for combo in live.get(label, [])
                if tuple(combo) in allowed
            ]
            if live_row_combos:
                subgroup_out[label] = _sorted_combo_lists(live_row_combos)

        if subgroup_out:
            out[subgroup_name] = subgroup_out

    return out



def _apply_row_version_to_live(
    hand: HandState,
    *,
    bucket_name: str,
    row_version: dict[str, dict[str, list[list[str]]]],
) -> None:
    """
    Replace the current live contents of one prune row with a saved row version,
    while preserving same-label combos that belong to other subgroups / rows.
    """
    original_row = hand.prune_row_originals.get(bucket_name, {})
    new_live = _deepcopy_combo_map(hand.villain_range_combos_live)

    row_original_by_label: dict[str, set[tuple[str, str]]] = {}
    for subgroup_name, label_map in original_row.items():
        del subgroup_name
        for label, combos in label_map.items():
            row_original_by_label.setdefault(label, set()).update(tuple(combo) for combo in combos)

    row_version_by_label: dict[str, list[list[str]]] = {}
    for subgroup_name, label_map in row_version.items():
        del subgroup_name
        for label, combos in label_map.items():
            row_version_by_label.setdefault(label, [])
            row_version_by_label[label].extend([list(combo) for combo in combos])

    all_labels = set(row_original_by_label.keys()) | set(row_version_by_label.keys())
    for label in all_labels:
        row_combo_set = row_original_by_label.get(label, set())
        current_live_label = [list(combo) for combo in new_live.get(label, [])]

        outside_row = [
            list(combo)
            for combo in current_live_label
            if tuple(combo) not in row_combo_set
        ]
        restored_row = _sorted_combo_lists(row_version_by_label.get(label, []))

        merged = _sorted_combo_lists(outside_row + restored_row)
        if merged:
            new_live[label] = merged
        else:
            new_live.pop(label, None)

    hand.villain_range_combos_live = new_live



def start_prune_mode(
    hand_id: str,
    *,
    iters: int | None = None,
    seed: int = 42,
) -> HandState:
    """
    Initialize row-by-row prune mode for the current hand.

    The optional seed argument is accepted for backward compatibility but ignored.
    If iters is omitted, prune initialization uses the street-specific defaults
    defined in bucketizer.py.
    """
    del seed

    hand = _hand_from_store(hand_id)
    if hand.ui_gate != UIGate.MUST_PRUNE_RANGE:
        raise ValueError(
            f"Hand {hand_id} is not in must_prune_range gate; current gate={hand.ui_gate}"
        )

    initialize_prune_state(hand, iters=iters)

    if not hand.prune_row_order:
        _continue_after_completed_prune(hand, iters=iters)

    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand



def remove_subgroup_from_current_row(
    hand_id: str,
    *,
    subgroup_name: str,
    bucket_matrix_view_snapshot: dict | None = None,
    elapsed_ms: int | None = None,
) -> HandState:
    """
    Remove an entire subgroup from the current prune row, while preserving same-label
    combos that belong to other subgroups or rows.
    """
    hand = _hand_from_store(hand_id)
    bucket_name = hand.next_prune_bucket()
    if bucket_name is None:
        raise ValueError(f"Hand {hand_id} has no active prune row")

    current_row = _current_row_draft(hand, bucket_name)
    current_subgroup = current_row.get(subgroup_name)
    if not current_subgroup:
        raise ValueError(
            f"Subgroup {subgroup_name!r} is not present in current prune row {bucket_name!r}"
        )

    removed_combo_count = sum(len(combos) for combos in current_subgroup.values())
    before_live_combos = sum(len(combos) for combos in hand.villain_range_combos_live.values())
    targets_by_label = {
        label: {tuple(combo) for combo in combos}
        for label, combos in current_subgroup.items()
    }

    for label, targets in targets_by_label.items():
        current_live_label = [list(combo) for combo in hand.villain_range_combos_live.get(label, [])]
        updated = [
            list(combo)
            for combo in current_live_label
            if tuple(combo) not in targets
        ]

        if updated:
            hand.villain_range_combos_live[label] = _sorted_combo_lists(updated)
        else:
            hand.villain_range_combos_live.pop(label, None)

    after_live_combos = sum(len(combos) for combos in hand.villain_range_combos_live.values())
    hand.replay_events.append({
        "kind": "prune_remove_subgroup",
        "street": hand.street.value,
        "board": list(hand.board),
        "details": {
            "bucket": bucket_name,
            "subgroup": subgroup_name,
            "removed_combo_count": removed_combo_count,
            "before_live_combos": before_live_combos,
            "after_live_combos": after_live_combos,
            "history_event_count": len(hand.history.events),
            "labels": sorted(current_subgroup.keys()),
            "elapsed_ms": max(0, int(elapsed_ms or 0)),
            "bucket_matrix_view": dict(bucket_matrix_view_snapshot or {}),
        },
    })
    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand



def revert_current_row(
    hand_id: str,
) -> HandState:
    """
    Restore the current prune row to its last saved version.
    """
    hand = _hand_from_store(hand_id)
    bucket_name = hand.next_prune_bucket()
    if bucket_name is None:
        raise ValueError(f"Hand {hand_id} has no active prune row")

    saved_version = hand.prune_row_saved_versions.get(bucket_name)
    if saved_version is None:
        raise ValueError(f"No saved version found for current prune row {bucket_name!r}")

    _apply_row_version_to_live(
        hand,
        bucket_name=bucket_name,
        row_version=_deepcopy_prune_snapshot({bucket_name: saved_version})[bucket_name],
    )

    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand



def save_current_row_and_advance(
    hand_id: str,
    *,
    iters: int | None = None,
    schedule_prune_evaluation: PruneEvaluationScheduler | None = None,
) -> HandState:
    """
    Save the current prune row draft as the new saved version, then advance to the next row.

    When the final row is saved, the app flow continues exactly as before:
    - villain CHECK / CALL / BET / RAISE were all pruned
    - after final prune row, continue to the proper next state

    If iters is omitted, downstream villain-action and bucket paths use the
    street-specific defaults defined in bucketizer.py.
    """
    hand = _hand_from_store(hand_id)
    bucket_name = hand.next_prune_bucket()
    if bucket_name is None:
        raise ValueError(f"Hand {hand_id} has no active prune row")

    current_row = _current_row_draft(hand, bucket_name)
    hand.prune_row_saved_versions[bucket_name] = _deepcopy_prune_snapshot(
        {bucket_name: current_row}
    )[bucket_name]
    hand.advance_prune_row()

    if hand.all_prune_rows_complete():
        _record_or_schedule_prune_evaluation(
            hand,
            iters=iters,
            schedule_prune_evaluation=schedule_prune_evaluation,
        )
        _continue_after_completed_prune(hand, iters=iters)

    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand

def save_full_prune_step_and_continue(
    hand_id: str,
    *,
    iters: int | None = None,
    schedule_prune_evaluation: PruneEvaluationScheduler | None = None,
) -> HandState:
    """
    Finalize the entire prune step exactly as the live range currently stands,
    then continue the normal post-prune game flow.

    This is used by the training timer when the user times out during the prune
    step. The timer applies to the full prune step, not row-by-row.

    Behavior:
    - preserves all live removals already made across any prune rows
    - does not force-save row-by-row snapshots
    - simply accepts the current villain_range_combos_live as the final pruned range
    - clears prune state and continues to the next proper gate

    If prune state has not been initialized yet for the current must-prune gate,
    initialize it first so the downstream flow remains consistent.
    """
    hand = _hand_from_store(hand_id)

    if hand.ui_gate != UIGate.MUST_PRUNE_RANGE:
        raise ValueError(
            f"Hand {hand_id} is not in must_prune_range gate; current gate={hand.ui_gate}"
        )

    if not hand.prune_row_order:
        initialize_prune_state(hand, iters=iters)

    if hand.prune_row_order:
        _record_or_schedule_prune_evaluation(
            hand,
            iters=iters,
            schedule_prune_evaluation=schedule_prune_evaluation,
        )

    _continue_after_completed_prune(hand, iters=iters)

    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand
