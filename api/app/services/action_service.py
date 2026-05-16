# File: api/app/services/action_service.py
# Summary: Service-layer helpers for validating and applying hero actions, resolving
# the next villain action when needed, and advancing the hand across streets while
# keeping the live villain range card-legal after new board cards are dealt.

from __future__ import annotations

from dataclasses import fields
import random

from api.app.data.catalog import get_scenario
from api.app.engine.cards import available_deck
from api.app.engine.villain_decision import choose_villain_action
from api.app.models.betting import ActionEvent
from api.app.models.enums import ActionType, Player, ResponseColumnType, Street, UIGate
from api.app.models.state import HandState
from api.app.models.villain_profile import DecisionNode
from api.app.services.prune_service import initialize_prune_state
from api.app.services.scoring_service import record_response_matrix_evaluation
from api.app.storage.memory_store import store


AGGRESSIVE_ACTIONS = {ActionType.BET, ActionType.RAISE}


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


def _response_columns_for_current_hero_node(hand: HandState) -> list[str]:
    """
    Return the response-matrix columns for the current hero decision node.

    Facing a bet/raise:
    - Call
    - Raise

    Not facing a bet:
    - Check
    - Bet Small
    - Bet Big
    """
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
    """
    Resolve villain's chosen bet sizing into a concrete amount.

    Uses the decision engine sizing when available, with a sane street-based fallback.
    """
    frac = float(chosen_frac) if chosen_frac is not None else _fallback_bet_frac(street)
    frac = max(0.05, frac)
    raw = round(max(1.0, pot * frac), 2)
    return round(min(raw, villain_stack), 2)


def _resolve_villain_raise_to(
    *,
    current_bet: float,
    villain_contrib: float,
    villain_stack: float,
    chosen_mult: float | None,
) -> float:
    """
    Resolve villain's chosen raise multiplier into a concrete raise-to amount.

    Interpretation:
    - multiplier is applied to the amount villain is facing (`to_call`)
    - if villain has contributed nothing yet, facing a 20 bet with 3.0x => raise to 60
    - if villain already has money in, facing current_bet=60 with villain_contrib=20,
      to_call=40 and 3.0x => raise to 140 (= 20 + 40*3)
    """
    to_call = round(max(0.0, current_bet - villain_contrib), 2)
    mult = float(chosen_mult) if chosen_mult is not None else 3.0
    mult = max(1.2, mult)

    raw_raise_to = round(villain_contrib + to_call * mult, 2)
    min_raise_to = round(current_bet + 1.0, 2)
    max_raise_to = round(villain_contrib + villain_stack, 2)

    return round(max(min_raise_to, min(raw_raise_to, max_raise_to)), 2)


def _street_events(hand: HandState) -> list[ActionEvent]:
    return [event for event in hand.history.events if event.street == hand.street]


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
    """
    Remove any villain live combos that are no longer legal because they conflict
    with the current hero hand or current board.
    """
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


def _clear_response_matrix_node_state(hand: HandState) -> None:
    """
    Clear any saved response-matrix data from the previous node.
    """
    hand.response_matrix_saved = {}


def _has_timeout_saved_response_matrix_for_current_street(hand: HandState) -> bool:
    """
    Return True when the response matrix was auto-saved by the training timer.

    Manual saves still require a complete matrix. Timer-expiry saves are allowed
    to persist blanks and should satisfy the matrix gate so the player is not
    trapped if time expires mid-matrix.
    """
    saved = hand.response_matrix_saved or {}
    if not isinstance(saved, dict):
        return False

    if saved.get("street") != hand.street.value:
        return False

    if saved.get("save_reason") != "timer_expired":
        return False

    if saved.get("allow_partial") is not True:
        return False

    selections = saved.get("selections")
    return isinstance(selections, dict)


def _clear_prune_state(hand: HandState) -> None:
    hand.prune_row_order = []
    hand.prune_row_index = 0
    hand.prune_range_snapshot = {}
    hand.prune_row_originals = {}
    hand.prune_row_saved_versions = {}


def _set_hero_response_matrix_gate(hand: HandState) -> None:
    """
    Move the hand to the hero-side response-matrix step.
    """
    hand.current_actor = Player.HERO
    hand.ui_gate = UIGate.MUST_FILL_RESPONSE_MATRIX
    hand.response_matrix_columns = _response_columns_for_current_hero_node(hand)
    _clear_response_matrix_node_state(hand)
    _clear_prune_state(hand)


def _set_prune_gate_for_hero(
    hand: HandState,
    *,
    iters: int | None,
) -> None:
    """
    Move the hand to the hero-side prune step after any villain action that
    should trigger pruning.

    Important:
    - This preserves the existing flow: prune after villain CHECK / CALL / BET / RAISE
      (excluding folds).
    - Prune rows are initialized immediately so the returned hand is already ready
      for the prune UI without relying on a separate frontend start call.
    - If iters is omitted, prune initialization uses the street-specific defaults
      defined in bucketizer.py.
    """
    hand.current_actor = Player.HERO
    hand.ui_gate = UIGate.MUST_PRUNE_RANGE
    hand.response_matrix_columns = _response_columns_for_current_hero_node(hand)
    _clear_response_matrix_node_state(hand)
    _clear_prune_state(hand)
    initialize_prune_state(hand, iters=iters)


def _set_hand_over(hand: HandState) -> None:
    hand.hand_over = True
    hand.current_aggressor = _final_aggressor_for_street(hand)
    hand.ui_gate = UIGate.HAND_OVER
    hand.response_matrix_columns = []
    _clear_response_matrix_node_state(hand)
    _clear_prune_state(hand)


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


def _advance_street_or_end(
    hand: HandState,
    *,
    seed: int,
    iters: int | None,
) -> None:
    """
    Advance to the next street if possible; otherwise end the hand on river completion.

    If iters is omitted, downstream villain-action and bucket paths use the
    street-specific defaults defined in bucketizer.py.
    """
    scenario = get_scenario(hand.scenario_id)
    previous_street_aggressor = _final_aggressor_for_street(hand)

    if hand.street == Street.RIVER:
        _set_hand_over(hand)
        return

    # Use the hand's stable random seed as the base for runouts. The route-level
    # seed can be constant in the UI, so relying on it alone makes turn/river
    # cards repeat across hands. Combining it with bucket_seed and action count
    # keeps runouts per-hand random while preserving deterministic behavior for a
    # given saved hand state.
    runout_seed = int(hand.bucket_seed) + int(seed) + len(hand.history.events) * 97 + len(hand.board) * 1009
    rng = random.Random(runout_seed)

    next_card = _deal_next_board_card(hand, rng)
    hand.board.append(next_card)

    _filter_live_range_for_blockers(hand)

    if hand.street == Street.FLOP:
        hand.street = Street.TURN
    elif hand.street == Street.TURN:
        hand.street = Street.RIVER
    else:
        raise ValueError(f"Unexpected street advance from {hand.street}")

    hand.betting_round.reset_for_new_street()
    hand.current_aggressor = previous_street_aggressor
    _clear_response_matrix_node_state(hand)
    _clear_prune_state(hand)

    first_actor = scenario.first_to_act_postflop

    if first_actor == Player.HERO:
        _set_hero_response_matrix_gate(hand)
        return

    _resolve_villain_turn(
        hand,
        seed=seed + 1,
        iters=iters,
        can_raise=False,
    )


def _finalize_after_villain_non_aggressive_action(
    hand: HandState,
    *,
    seed: int,
    iters: int | None,
) -> None:
    """
    For normal villain CHECK / CALL actions, always stop at prune first.

    Desired Screen 3 flow:
    1. hero acts
    2. villain thinks
    3. villain action is shown
    4. hero prunes / updates villain range
    5. only after prune completes do we advance street or end hand

    Street advancement / hand-over after a closing CHECK or CALL is handled later
    by prune_service._continue_after_completed_prune().
    """
    del seed
    _set_prune_gate_for_hero(hand, iters=iters)


def _resolve_villain_turn(
    hand: HandState,
    *,
    seed: int,
    iters: int | None,
    can_raise: bool,
    hero_action_type: ActionType | None = None,
    hero_amount: float | None = None,
    pot_before_action: float | None = None,
) -> None:
    """
    Resolve the next villain action node.

    Updated flow:
    - villain CHECK / CALL:
        - if the street is now complete, advance street or end hand immediately
        - otherwise prune before hero acts
    - villain BET / RAISE -> prune
    - folds end the hand immediately

    If iters is omitted, villain bucketing/equity uses the street-specific
    defaults defined in bucketizer.py.
    """
    scenario = get_scenario(hand.scenario_id)

    decision = _choose_villain_action_for_hand(
        hand,
        scenario=scenario,
        can_raise=can_raise,
        seed=seed,
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

        record_response_matrix_evaluation(
            hand,
            hero_action_type=hero_action_type or ActionType.CHECK,
            hero_amount=hero_amount,
            pot_before_action=pot_before_action,
            villain_action_type=ActionType.CHECK,
            iters=iters,
        )

        _finalize_after_villain_non_aggressive_action(
            hand,
            seed=seed + 20,
            iters=iters,
        )
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

        record_response_matrix_evaluation(
            hand,
            hero_action_type=hero_action_type or ActionType.CHECK,
            hero_amount=hero_amount,
            pot_before_action=pot_before_action,
            villain_action_type=ActionType.BET,
            iters=iters,
        )

        _set_prune_gate_for_hero(hand, iters=iters)
        return

    if decision.action == ActionType.CALL:
        call_amount = hand.betting_round.to_call_for(Player.VILLAIN)
        call_amount = min(call_amount, hand.villain_stack)

        hand.villain_stack = round(hand.villain_stack - call_amount, 2)
        hand.pot = round(hand.pot + call_amount, 2)
        hand.betting_round.villain_contrib = round(
            hand.betting_round.villain_contrib + call_amount, 2
        )

        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.VILLAIN,
                action=ActionType.CALL,
                amount=call_amount,
                note=f"{note} called",
                forced=False,
            )
        )

        record_response_matrix_evaluation(
            hand,
            hero_action_type=hero_action_type or ActionType.CHECK,
            hero_amount=hero_amount,
            pot_before_action=pot_before_action,
            villain_action_type=ActionType.CALL,
            iters=iters,
        )

        _finalize_after_villain_non_aggressive_action(
            hand,
            seed=seed + 20,
            iters=iters,
        )
        return

    if decision.action == ActionType.FOLD:
        hand.betting_round.folded = True
        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.VILLAIN,
                action=ActionType.FOLD,
                amount=0.0,
                note=f"{note} folded",
                forced=False,
            )
        )
        record_response_matrix_evaluation(
            hand,
            hero_action_type=hero_action_type or ActionType.CHECK,
            hero_amount=hero_amount,
            pot_before_action=pot_before_action,
            villain_action_type=ActionType.FOLD,
            iters=iters,
        )
        _set_hand_over(hand)
        return

    if decision.action == ActionType.RAISE:
        raise_to = _resolve_villain_raise_to(
            current_bet=hand.betting_round.current_bet,
            villain_contrib=hand.betting_round.villain_contrib,
            villain_stack=hand.villain_stack,
            chosen_mult=decision.raise_size_mult,
        )
        put_in = round(raise_to - hand.betting_round.villain_contrib, 2)
        previous_bet = hand.betting_round.current_bet

        hand.villain_stack = round(hand.villain_stack - put_in, 2)
        hand.pot = round(hand.pot + put_in, 2)
        hand.betting_round.villain_contrib = raise_to
        hand.betting_round.current_bet = raise_to
        hand.betting_round.last_raise_size = round(raise_to - previous_bet, 2)
        hand.current_aggressor = Player.VILLAIN

        size_note = (
            f" ({decision.raise_size_key}, {round(float(decision.raise_size_mult or 0.0), 2)}x)"
            if decision.raise_size_key is not None
            else ""
        )

        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.VILLAIN,
                action=ActionType.RAISE,
                amount=raise_to,
                note=f"{note} raised{size_note}",
                forced=False,
            )
        )

        record_response_matrix_evaluation(
            hand,
            hero_action_type=hero_action_type or ActionType.CHECK,
            hero_amount=hero_amount,
            pot_before_action=pot_before_action,
            villain_action_type=ActionType.RAISE,
            iters=iters,
        )

        _set_prune_gate_for_hero(hand, iters=iters)
        return

    raise ValueError(f"Unsupported villain action: {decision.action}")


def apply_hero_action(
    hand_id: str,
    *,
    action: str,
    amount: float | None = None,
    seed: int = 42,
    iters: int | None = None,
) -> HandState:
    """
    Apply a hero action and continue the hand flow.

    If iters is omitted, villain bucketing/equity and prune initialization use
    the street-specific defaults defined in bucketizer.py.
    """
    hand = _hand_from_store(hand_id)
    pot_before_action = hand.pot

    if (
        hand.ui_gate == UIGate.MUST_FILL_RESPONSE_MATRIX
        and _has_timeout_saved_response_matrix_for_current_street(hand)
    ):
        hand.ui_gate = UIGate.HERO_TO_ACT

    if hand.ui_gate != UIGate.HERO_TO_ACT:
        raise ValueError(
            f"Hand {hand_id} is not in hero_to_act gate; current gate={hand.ui_gate}"
        )
    if hand.current_actor != Player.HERO:
        raise ValueError(f"Hand {hand_id} current_actor is not hero")

    try:
        action_type = ActionType(action)
    except ValueError as exc:
        raise ValueError(f"Invalid hero action: {action}") from exc

    to_call = hand.betting_round.to_call_for(Player.HERO)

    if action_type == ActionType.CHECK:
        if to_call > 0:
            raise ValueError("Hero cannot check when facing a bet")
        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.HERO,
                action=ActionType.CHECK,
                amount=0.0,
                note="Hero checked",
                forced=False,
            )
        )

        if _street_is_complete(hand):
            _advance_street_or_end(hand, seed=seed + 20, iters=iters)
        else:
            hand.current_actor = Player.VILLAIN
            _resolve_villain_turn(
                hand,
                seed=seed + 1,
                iters=iters,
                can_raise=False,
                hero_action_type=ActionType.CHECK,
                hero_amount=0.0,
                pot_before_action=pot_before_action,
            )

    elif action_type == ActionType.BET:
        if to_call > 0:
            raise ValueError("Hero cannot bet when facing a bet; use raise")
        if amount is None:
            raise ValueError("Hero bet requires amount")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Hero bet amount must be > 0")
        if amount > hand.hero_stack:
            raise ValueError("Hero bet amount cannot exceed hero stack")

        hand.hero_stack = round(hand.hero_stack - amount, 2)
        hand.pot = round(hand.pot + amount, 2)
        hand.betting_round.current_bet = amount
        hand.betting_round.hero_contrib = amount
        hand.betting_round.last_raise_size = amount
        hand.current_aggressor = Player.HERO

        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.HERO,
                action=ActionType.BET,
                amount=amount,
                note="Hero bet",
                forced=False,
            )
        )

        hand.current_actor = Player.VILLAIN
        _resolve_villain_turn(
            hand,
            seed=seed + 1,
            iters=iters,
            can_raise=True,
            hero_action_type=ActionType.BET,
            hero_amount=amount,
            pot_before_action=pot_before_action,
        )

    elif action_type == ActionType.FOLD:
        if to_call <= 0:
            raise ValueError("Hero cannot fold when not facing a bet")
        hand.betting_round.folded = True
        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.HERO,
                action=ActionType.FOLD,
                amount=0.0,
                note="Hero folded",
                forced=False,
            )
        )
        _set_hand_over(hand)

    elif action_type == ActionType.CALL:
        if to_call <= 0:
            raise ValueError("Hero cannot call when not facing a bet")
        call_amount = min(to_call, hand.hero_stack)

        hand.hero_stack = round(hand.hero_stack - call_amount, 2)
        hand.pot = round(hand.pot + call_amount, 2)
        hand.betting_round.hero_contrib = round(
            hand.betting_round.hero_contrib + call_amount, 2
        )

        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.HERO,
                action=ActionType.CALL,
                amount=call_amount,
                note="Hero called",
                forced=False,
            )
        )

        if _street_is_complete(hand):
            _advance_street_or_end(hand, seed=seed + 20, iters=iters)
        else:
            hand.current_actor = Player.VILLAIN

    elif action_type == ActionType.RAISE:
        if to_call <= 0:
            raise ValueError("Hero cannot raise when not facing a bet")
        if amount is None:
            raise ValueError("Hero raise requires amount")
        raise_to = round(float(amount), 2)
        if raise_to <= hand.betting_round.current_bet:
            raise ValueError("Hero raise amount must be greater than current bet")
        max_raise_to = round(hand.hero_stack + hand.betting_round.hero_contrib, 2)
        if raise_to > max_raise_to:
            raise ValueError("Hero raise amount cannot exceed hero stack plus contribution")

        put_in = round(raise_to - hand.betting_round.hero_contrib, 2)
        previous_bet = hand.betting_round.current_bet

        hand.hero_stack = round(hand.hero_stack - put_in, 2)
        hand.pot = round(hand.pot + put_in, 2)
        hand.betting_round.hero_contrib = raise_to
        hand.betting_round.current_bet = raise_to
        hand.betting_round.last_raise_size = round(raise_to - previous_bet, 2)
        hand.current_aggressor = Player.HERO

        hand.history.append(
            ActionEvent(
                street=hand.street,
                actor=Player.HERO,
                action=ActionType.RAISE,
                amount=raise_to,
                note="Hero raised",
                forced=False,
            )
        )

        hand.current_actor = Player.VILLAIN
        _resolve_villain_turn(
            hand,
            seed=seed + 1,
            iters=iters,
            can_raise=True,
            hero_action_type=ActionType.RAISE,
            hero_amount=raise_to,
            pot_before_action=pot_before_action,
        )

    else:
        raise ValueError(f"Unsupported hero action: {action_type}")

    store.update_hand(hand_id, _hand_to_store_payload(hand))
    return hand
