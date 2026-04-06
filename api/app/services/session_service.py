# File: api/app/services/session_service.py
# Summary: Service-layer helpers for creating sessions, attaching scenarios, generating starting stacks/ranges, and saving the preflop starting matrices for hero and villain.
from __future__ import annotations

from dataclasses import asdict
import random
from uuid import uuid4

from api.app.data.catalog import SCENARIOS, get_scenario
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.engine.range_format import (
    all_matrix_labels,
    exact_tokens_from_matrix_state,
    matrix_state_from_tokens,
)
from api.app.models.state import SessionState
from api.app.storage.memory_store import store


_TIMER_UNSET = object()


def _round_to_nearest_five(value: float) -> float:
    return float(int(round(value / 5.0) * 5))


def _sample_stack_for_villain(villain_profile_id: str, rng: random.Random) -> float:
    """
    Generate a starting stack weighted by villain type.

    These can be tuned later, but for now they preserve the intended feel:
    - splashier / looser villains trend deeper
    - tighter / more straightforward villains trend a bit shallower
    """
    if villain_profile_id in {"calling_station", "chaser", "maniac"}:
        raw = rng.triangular(120.0, 450.0, 240.0)
    elif villain_profile_id in {"weak_tight", "abc_fit_fold", "tag"}:
        raw = rng.triangular(80.0, 260.0, 150.0)
    else:  # loose_reg
        raw = rng.triangular(100.0, 320.0, 180.0)

    return _round_to_nearest_five(raw)


def _validate_matrix_state(matrix_state: dict[str, bool]) -> None:
    expected = set(all_matrix_labels())
    actual = set(matrix_state.keys())

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            "matrix_state must contain exactly the 169 canonical matrix labels. "
            f"Missing={missing[:5]} Extra={extra[:5]}"
        )

    if not all(isinstance(value, bool) for value in matrix_state.values()):
        raise ValueError("matrix_state values must all be bool")


def _validate_actor(actor: str) -> None:
    if actor not in {"hero", "villain"}:
        raise ValueError("actor must be either 'hero' or 'villain'")


def _validate_train_timer_seconds(train_timer_seconds: int | None) -> None:
    if train_timer_seconds not in {None, 0, 10, 30, 60}:
        raise ValueError(
            "train_timer_seconds must be one of: None, 0, 10, 30, 60"
        )


def _session_from_store(session_id: str) -> SessionState:
    payload = store.get_session(session_id)
    if payload is None:
        raise ValueError(f"Unknown session_id: {session_id}")
    return SessionState(**payload)


def create_session(
    user_id: str,
    villain_profile_id: str,
    *,
    train_timer_seconds: int | None = None,
) -> SessionState:
    """
    Create a new session immediately after Screen 1 villain selection.

    train_timer_seconds semantics:
    - None -> no Train timer has been selected / timer not applicable
    - 0    -> Train timer explicitly Off
    - 10/30/60 -> active Train countdown selection
    """
    if villain_profile_id not in VILLAIN_PROFILES:
        raise ValueError(f"Unknown villain_profile_id: {villain_profile_id}")

    _validate_train_timer_seconds(train_timer_seconds)

    session = SessionState(
        session_id=str(uuid4()),
        user_id=user_id,
        villain_profile_id=villain_profile_id,
        train_timer_seconds=train_timer_seconds,
    )
    store.create_session(session.session_id, asdict(session))
    return session


def get_session(session_id: str) -> SessionState:
    """
    Return a stored session.
    """
    return _session_from_store(session_id)


def set_session_scenario(
    session_id: str,
    scenario_id: str,
    *,
    seed: int | None = None,
    train_timer_seconds: int | None | object = _TIMER_UNSET,
) -> SessionState:
    """
    Attach a scenario to the session, generate pot/stacks, and load the default
    hero and villain starting range matrices for the preflop editor.

    When train_timer_seconds is supplied, persist it onto the session.
    When omitted, preserve the session's current timer selection.
    """
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario_id: {scenario_id}")

    session = _session_from_store(session_id)
    scenario = get_scenario(scenario_id)

    if train_timer_seconds is _TIMER_UNSET:
        resolved_train_timer_seconds = session.train_timer_seconds
    else:
        _validate_train_timer_seconds(train_timer_seconds)
        resolved_train_timer_seconds = train_timer_seconds

    rng = random.Random(seed)
    hero_stack = _sample_stack_for_villain(session.villain_profile_id, rng)
    villain_stack = _sample_stack_for_villain(session.villain_profile_id, rng)

    hero_default_matrix = matrix_state_from_tokens(scenario.hero_range_tokens)
    hero_default_tokens = exact_tokens_from_matrix_state(hero_default_matrix)

    villain_default_matrix = matrix_state_from_tokens(scenario.villain_range_tokens)
    villain_default_tokens = exact_tokens_from_matrix_state(villain_default_matrix)

    updated = SessionState(
        session_id=session.session_id,
        user_id=session.user_id,
        villain_profile_id=session.villain_profile_id,
        train_timer_seconds=resolved_train_timer_seconds,
        scenario_id=scenario.id,
        pot=scenario.default_pot,
        hero_stack=hero_stack,
        villain_stack=villain_stack,
        hero_range_matrix_saved=hero_default_matrix,
        hero_tokens_saved=hero_default_tokens,
        villain_range_matrix_saved=villain_default_matrix,
        villain_tokens_saved=villain_default_tokens,
        hero_range_confirmed=False,
        villain_range_confirmed=False,
    )

    store.update_session(session_id, asdict(updated))
    return updated


def save_starting_range(
    session_id: str,
    actor: str,
    matrix_state: dict[str, bool],
) -> SessionState:
    """
    Save the finalized starting range matrix for either hero or villain.
    """
    _validate_actor(actor)
    _validate_matrix_state(matrix_state)

    session = _session_from_store(session_id)

    if session.scenario_id is None:
        raise ValueError("Cannot save a starting range before selecting a scenario")

    exact_tokens = exact_tokens_from_matrix_state(matrix_state)

    updated = SessionState(
        session_id=session.session_id,
        user_id=session.user_id,
        villain_profile_id=session.villain_profile_id,
        train_timer_seconds=session.train_timer_seconds,
        scenario_id=session.scenario_id,
        pot=session.pot,
        hero_stack=session.hero_stack,
        villain_stack=session.villain_stack,
        hero_range_matrix_saved=(
            matrix_state if actor == "hero" else session.hero_range_matrix_saved
        ),
        hero_tokens_saved=(
            exact_tokens if actor == "hero" else session.hero_tokens_saved
        ),
        villain_range_matrix_saved=(
            matrix_state if actor == "villain" else session.villain_range_matrix_saved
        ),
        villain_tokens_saved=(
            exact_tokens if actor == "villain" else session.villain_tokens_saved
        ),
        hero_range_confirmed=(
            True if actor == "hero" else session.hero_range_confirmed
        ),
        villain_range_confirmed=(
            True if actor == "villain" else session.villain_range_confirmed
        ),
    )

    store.update_session(session_id, asdict(updated))
    return updated