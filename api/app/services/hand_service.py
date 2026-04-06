# File: api/app/services/hand_service.py
# Summary: Service-layer helpers for starting a new Screen 3 hand, initializing live range state,
# resolving any immediate first actor logic, and retrieving stored hands.

from __future__ import annotations

from dataclasses import fields
import random
from uuid import uuid4

from api.app.data.catalog import get_scenario
from api.app.engine.cards import available_deck, ensure_unique_cards
from api.app.engine.dealing import (
    available_combos_for_label,
    sample_hero_and_villain_hands,
)
from api.app.engine.villain_decision import choose_villain_action
from api.app.models.betting import ActionEvent, BettingRoundState
from api.app.models.enums import (
    ActionType,
    Player,
    ResponseColumnType,
    Street,
    UIGate,
)
from api.app.models.state import HandState, SessionState
from api.app.services.prune_service import initialize_prune_state
from api.app.storage.memory_store import store


_AGGRESSIVE_ACTIONS = {ActionType.BET, ActionType.RAISE}


def _session_from_store(session_id: str) -> SessionState:
    payload = store.get_session(session_id)
    if payload is None:
        raise ValueError(f"Unknown session_id: {session_id}")
    return SessionState(**payload)


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

    Important:
    - Facing a bet/raise => Call / Raise columns
    - Not facing a bet => Check / Bet Small / Bet Big columns

    The *meaning* of the CHECK column can be context-sensitive
    (e.g. IP checkback node after villain checks to hero), but that
    affects response-option validation/rendering, not which columns exist.
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


def _clear_response_matrix_node_state(hand: HandState) -> None:
    hand.response_matrix_saved = {}


def _clear_prune_state(hand: HandState) -> None:
    hand.prune_row_order = []
    hand.prune_row_index = 0
    hand.prune_range_snapshot = {}
    hand.prune_row_originals = {}
    hand.prune_row_saved_versions = {}


def _set_hero_response_matrix_gate(hand: HandState) -> None:
    """
    Put the hand into the hero-side response-matrix step using the
    current node's actual betting state.
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
    Put the hand into the hero-side prune step and initialize the prune rows
    immediately so Screen 3 can open directly into pruning without requiring
    a separate backend call.
    """
    hand.current_actor = Player.HERO
    hand.ui_gate = UIGate.MUST_PRUNE_RANGE
    hand.response_matrix_columns = _response_columns_for_current_hero_node(hand)
    _clear_response_matrix_node_state(hand)
    _clear_prune_state(hand)
    initialize_prune_state(hand, iters=iters)


def _deal_flop(
    *,
    excluded_cards: list[str],
    rng: random.Random,
) -> list[str]:
    deck = available_deck(excluded_cards)
    return rng.sample(deck, 3)


def _initial_live_villain_combo_map(
    *,
    villain_exact_labels: list[str],
    excluded_cards: list[str],
) -> dict[str, list[list[str]]]:
    """
    Build the live villain combo state from exact labels after removing blocked cards.

    Structure:
    {
        "AKs": [["As", "Ks"], ["Ah", "Kh"], ...],
        "77":  [["7c", "7d"], ["7c", "7h"], ...],
    }
    """
    out: dict[str, list[list[str]]] = {}

    for label in villain_exact_labels:
        combos = available_combos_for_label(label, excluded_cards=excluded_cards)
        if combos:
            out[label] = [list(combo) for combo in combos]

    return out


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


def _decision_note(decision) -> str:
    return f"Villain {decision.note}"


def _count_aggressive_actions(
    hand: HandState,
    *,
    actor: Player,
    include_current_street: bool = True,
) -> int:
    """
    Count prior aggressive actions for one player.

    This keeps the service layer and decision engine aligned on the same notion of
    "prior aggression" instead of forcing villain_policy to infer everything from
    the current node alone.
    """
    count = 0
    for event in hand.history.events:
        if event.actor != actor:
            continue
        if not include_current_street and event.street == hand.street:
            continue
        if event.action in _AGGRESSIVE_ACTIONS:
            count += 1
    return count


def _villain_decision_context_for_street_start(hand: HandState) -> dict:
    """
    Build the explicit decision context for a villain action at the start of a street.

    Preserve the existing service call contract even though the predictive model
    now ignores most of these legacy context fields.
    """
    scenario = get_scenario(hand.scenario_id)
    return {
        "node_hint": "unopened",
        "villain_is_current_aggressor": hand.current_aggressor == Player.VILLAIN,
        "villain_is_pfa": scenario.preflop_aggressor == Player.VILLAIN,
        "prior_villain_aggressive_actions": _count_aggressive_actions(
            hand,
            actor=Player.VILLAIN,
        ),
        "prior_hero_aggressive_actions": _count_aggressive_actions(
            hand,
            actor=Player.HERO,
        ),
    }


def _apply_initial_villain_check(
    hand: HandState,
    *,
    note: str,
) -> None:
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
    _set_hero_response_matrix_gate(hand)


def _apply_initial_villain_bet(
    hand: HandState,
    *,
    note: str,
    chosen_frac: float | None,
    bet_size_key: str | None,
    iters: int | None,
) -> None:
    amount = _resolve_villain_bet_amount(
        pot=hand.pot,
        street=hand.street,
        villain_stack=hand.villain_stack,
        chosen_frac=chosen_frac,
    )

    hand.villain_stack = round(hand.villain_stack - amount, 2)
    hand.pot = round(hand.pot + amount, 2)
    hand.betting_round.current_bet = amount
    hand.betting_round.villain_contrib = amount
    hand.betting_round.last_raise_size = amount
    hand.current_aggressor = Player.VILLAIN

    size_note = (
        f" ({bet_size_key}, {round(float(chosen_frac or 0.0), 2)} pot)"
        if bet_size_key is not None
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


def get_hand(hand_id: str) -> HandState:
    """
    Return a stored hand by id.
    """
    return _hand_from_store(hand_id)


def start_hand(
    session_id: str,
    *,
    seed: int | None = None,
    iters: int | None = None,
) -> HandState:
    """
    Start a new Screen 3 hand from a fully prepared session.

    Flow:
    1. Validate the session is ready
    2. Sample hero/villain hole cards
    3. Deal flop
    4. Initialize live villain combo range
    5. Set current aggressor / first actor
    6. If villain is first:
       - resolve villain's first action immediately with the predictive model
    7. Set the appropriate UI gate and response columns

    Important Screen 3 behavior:
    - when initial villain action is BET, the returned hand is already fully
      prune-ready (rows initialized) so the frontend can wait for the villain
      "thinking" pause and then open straight into pruning.
    - when initial villain action is CHECK, hero goes directly to the response matrix.
    - no extra follow-up call is needed just to initialize prune state.

    Iteration rule:
    - if iters is omitted, the villain bucket/equity path falls back to the
      street-specific defaults defined in bucketizer.py
    """
    session = _session_from_store(session_id)
    if not session.is_ready_for_hand_start():
        raise ValueError(f"Session {session_id} is not ready to start a hand")

    scenario = get_scenario(session.scenario_id)
    if session.hero_range_matrix_saved is None:
        raise ValueError("Session is missing hero_range_matrix_saved")
    if not session.hero_tokens_saved:
        raise ValueError("Session is missing hero_tokens_saved")
    if session.villain_range_matrix_saved is None:
        raise ValueError("Session is missing villain_range_matrix_saved")
    if not session.villain_tokens_saved:
        raise ValueError("Session is missing villain_tokens_saved")

    base_seed = seed if seed is not None else random.SystemRandom().randrange(1, 1_000_000_000)
    rng = random.Random(base_seed)

    hero_exact_labels = list(session.hero_tokens_saved)
    villain_exact_labels = list(session.villain_tokens_saved)

    hero_hand, villain_hand = sample_hero_and_villain_hands(
        hero_labels=hero_exact_labels,
        villain_labels=villain_exact_labels,
        rng=rng,
    )

    flop = _deal_flop(
        excluded_cards=[*hero_hand, *villain_hand],
        rng=rng,
    )
    ensure_unique_cards([*hero_hand, *villain_hand, *flop])

    live_combo_map = _initial_live_villain_combo_map(
        villain_exact_labels=villain_exact_labels,
        excluded_cards=[*hero_hand, *flop],
    )

    hand = HandState(
        hand_id=str(uuid4()),
        session_id=session.session_id,
        user_id=session.user_id,
        scenario_id=scenario.id,
        villain_profile_id=session.villain_profile_id,
        pot=float(session.pot),
        hero_stack=float(session.hero_stack),
        villain_stack=float(session.villain_stack),
        hero_hand=tuple(hero_hand),
        villain_hand=tuple(villain_hand),
        board=list(flop),
        street=Street.FLOP,
        betting_round=BettingRoundState(),
        hero_tokens_saved=list(session.hero_tokens_saved),
        villain_range_matrix_saved=session.villain_range_matrix_saved,
        villain_range_combos_live=live_combo_map,
        current_actor=scenario.first_to_act_postflop,
        current_aggressor=scenario.preflop_aggressor,
        ui_gate=UIGate.HERO_TO_ACT,
        hand_over=False,
        bucket_seed=base_seed,
        response_matrix_columns=[],
        response_matrix_saved={},
        prune_row_order=[],
        prune_row_index=0,
        prune_range_snapshot={},
        prune_row_originals={},
        prune_row_saved_versions={},
    )

    # Case 1: Hero is first to act postflop.
    if hand.current_actor == Player.HERO:
        _set_hero_response_matrix_gate(hand)

    # Case 2: Villain is first to act postflop.
    else:
        decision = choose_villain_action(
            villain_hand=hand.villain_hand,
            board=hand.board,
            villain_profile_id=hand.villain_profile_id,
            scenario_hero_range_tokens=hand.hero_tokens_saved,
            street=hand.street,
            to_call=0.0,
            pot=hand.pot,
            can_raise=False,
            iters=iters,
            seed=base_seed + 1,
            scenario_id=hand.scenario_id,
            villain_is_ip=(not scenario.hero_is_ip),
            history_events=hand.history.events,
            effective_stack_size=hand.villain_stack,
            **_villain_decision_context_for_street_start(hand),
        )

        note = _decision_note(decision)

        if decision.action == ActionType.CHECK:
            _apply_initial_villain_check(hand, note=note)

        elif decision.action == ActionType.BET:
            _apply_initial_villain_bet(
                hand,
                note=note,
                chosen_frac=decision.bet_size_frac,
                bet_size_key=decision.bet_size_key,
                iters=iters,
            )

        else:
            raise ValueError(
                f"Invalid initial villain action at street start: {decision.action}"
            )

    store.create_hand(hand.hand_id, _hand_to_store_payload(hand))
    return hand
