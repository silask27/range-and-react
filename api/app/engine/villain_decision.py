
from __future__ import annotations

"""Predictive villain action engine backed by the finalized calibration-lab stack.

This runtime keeps the existing public contract (`choose_villain_action` and
`VillainDecisionResult`) but swaps the internals to:
- build the richer v1-style predictor set
- query v1/v2/v3/v4/v5 expert action models
- score them with the trained v6 villain-prioritized meta stacker
- select the deterministic top action from the blended distribution
- preserve close/mixed probability metadata for scoring and debriefs
- use size-model-v3 for bet / raise sizing
"""

from dataclasses import dataclass
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import pickle
import random
from typing import Iterable, Sequence, Any

from api.app.data.catalog import get_scenario
from api.app.data.villain_profiles import get_villain_profile
from api.app.engine import bucketizer as bz
from api.app.engine.action_model_features_v6 import (
    ACTIONS_BY_NODE_V6,
    MODEL_ORDER_V6,
    build_action_meta_features_v6,
)
from api.app.engine.board_texture import evaluate_board_texture
from api.app.engine.cards import normalize_cards
from api.app.models.betting import ActionEvent
from api.app.models.enums import ActionType, Street

MODEL_DIR = Path(__file__).resolve().parents[1] / "model_artifacts" / "villain_models"
TRAINED_MODELS_DIR = MODEL_DIR / "trained_models"
TRAINED_MODELS_V2_DIR = MODEL_DIR / "trained_models_v2"
TRAINED_MODELS_V3_DIR = MODEL_DIR / "trained_models_v3"
TRAINED_MODELS_V4_DIR = MODEL_DIR / "trained_models_v4"
TRAINED_MODELS_V5_DIR = MODEL_DIR / "trained_models_v5"
TRAINED_MODELS_V6_DIR = MODEL_DIR / "trained_models_v6"
TRAINED_MODELS_SIZE_V2_DIR = MODEL_DIR / "trained_models_size_v2"
TRAINED_MODELS_SIZE_V3_DIR = MODEL_DIR / "trained_models_size_v3"

OPEN_ACTION_MODEL_FILE = TRAINED_MODELS_DIR / "open_action_model.pkl"
FACING_BET_FOLD_CONTINUE_MODEL_FILE = TRAINED_MODELS_DIR / "facing_bet_fold_continue_model.pkl"
FACING_BET_CALL_RAISE_MODEL_FILE = TRAINED_MODELS_DIR / "facing_bet_call_raise_model.pkl"
FACING_RAISE_FOLD_CONTINUE_MODEL_FILE = TRAINED_MODELS_DIR / "facing_raise_fold_continue_model.pkl"
FACING_RAISE_CALL_RERAISE_MODEL_FILE = TRAINED_MODELS_DIR / "facing_raise_call_reraise_model.pkl"

OPEN_ACTION_MODEL_V2_FILE = TRAINED_MODELS_V2_DIR / "open_action_model_v2.pkl"
FACING_BET_FOLD_CONTINUE_MODEL_V2_FILE = TRAINED_MODELS_V2_DIR / "facing_bet_fold_continue_model_v2.pkl"
FACING_BET_CALL_RAISE_MODEL_V2_FILE = TRAINED_MODELS_V2_DIR / "facing_bet_call_raise_model_v2.pkl"
FACING_RAISE_FOLD_CONTINUE_MODEL_V2_FILE = TRAINED_MODELS_V2_DIR / "facing_raise_fold_continue_model_v2.pkl"
FACING_RAISE_CALL_RERAISE_MODEL_V2_FILE = TRAINED_MODELS_V2_DIR / "facing_raise_call_reraise_model_v2.pkl"

OPEN_ACTION_PROB_MODEL_V3_FILE = TRAINED_MODELS_V3_DIR / "open_action_prob_model_v3.pkl"
FACING_BET_CONTINUE_PROB_MODEL_V3_FILE = TRAINED_MODELS_V3_DIR / "facing_bet_continue_prob_model_v3.pkl"
FACING_BET_RAISE_GIVEN_CONTINUE_PROB_MODEL_V3_FILE = TRAINED_MODELS_V3_DIR / "facing_bet_raise_given_continue_prob_model_v3.pkl"
FACING_RAISE_CONTINUE_PROB_MODEL_V3_FILE = TRAINED_MODELS_V3_DIR / "facing_raise_continue_prob_model_v3.pkl"
FACING_RAISE_RERAISE_GIVEN_CONTINUE_PROB_MODEL_V3_FILE = TRAINED_MODELS_V3_DIR / "facing_raise_reraise_given_continue_prob_model_v3.pkl"

OPEN_ACTION_PROB_MODEL_V4_FILE = TRAINED_MODELS_V4_DIR / "open_action_prob_model_v4.pkl"
FACING_BET_CONTINUE_PROB_MODEL_V4_FILE = TRAINED_MODELS_V4_DIR / "facing_bet_continue_prob_model_v4.pkl"
FACING_BET_RAISE_GIVEN_CONTINUE_PROB_MODEL_V4_FILE = TRAINED_MODELS_V4_DIR / "facing_bet_raise_given_continue_prob_model_v4.pkl"
FACING_RAISE_CONTINUE_PROB_MODEL_V4_FILE = TRAINED_MODELS_V4_DIR / "facing_raise_continue_prob_model_v4.pkl"
FACING_RAISE_RERAISE_GIVEN_CONTINUE_PROB_MODEL_V4_FILE = TRAINED_MODELS_V4_DIR / "facing_raise_reraise_given_continue_prob_model_v4.pkl"

V5_BLEND_CONFIG_FILE = TRAINED_MODELS_V5_DIR / "blend_config_v5.json"

OPEN_ACTION_META_MODEL_V6_FILE = TRAINED_MODELS_V6_DIR / "open_action_meta_model_v6.pkl"
FACING_BET_META_MODEL_V6_FILE = TRAINED_MODELS_V6_DIR / "facing_bet_meta_model_v6.pkl"
FACING_RAISE_META_MODEL_V6_FILE = TRAINED_MODELS_V6_DIR / "facing_raise_meta_model_v6.pkl"

OPEN_BET_SIZE_MODEL_V2_FILE = TRAINED_MODELS_SIZE_V2_DIR / "open_bet_size_model_v2.pkl"
RAISE_VS_BET_SIZE_MODEL_V2_FILE = TRAINED_MODELS_SIZE_V2_DIR / "raise_vs_bet_size_model_v2.pkl"
RERAISE_VS_RAISE_SIZE_MODEL_V2_FILE = TRAINED_MODELS_SIZE_V2_DIR / "reraise_vs_raise_size_model_v2.pkl"

OPEN_BET_SIZE_MODEL_V3_FILE = TRAINED_MODELS_SIZE_V3_DIR / "open_bet_size_model_v3.pkl"
RAISE_VS_BET_SIZE_MODEL_V3_FILE = TRAINED_MODELS_SIZE_V3_DIR / "raise_vs_bet_size_model_v3.pkl"
RERAISE_VS_RAISE_SIZE_MODEL_V3_FILE = TRAINED_MODELS_SIZE_V3_DIR / "reraise_vs_raise_size_model_v3.pkl"

ALLOWED_CALIBRATION_VILLAIN_NAMES = {"Dave", "Mike", "Blake", "Tom", "Steve", "Erik", "Alex"}
MODEL_ORDER_V5 = ["v1", "v2", "v3", "v4"]


@dataclass(frozen=True)
class BoardStateFlags:
    paired: bool
    rainbow: bool
    monotone: bool
    two_tone: bool
    flush_completed: bool
    straight_completed: bool
    connected: bool


@dataclass(frozen=True)
class FacingActionState:
    kind: str
    amount: float | None = None


@dataclass(frozen=True)
class PriorActionEventState:
    street: str
    actor: str
    action: str
    amount: float | None = None


@dataclass(frozen=True)
class RuntimeSpot:
    spot_id: str
    villain_type: str
    scenario_id: str
    street: str
    node: str
    open_action_type: str | None
    villain_is_ip: bool
    pot_size: float
    effective_stack_size: float
    board: list[str]
    villain_hand: list[str]
    prior_actions: list[PriorActionEventState]
    facing_action: FacingActionState
    legal_actions: list[str]


@dataclass(frozen=True)
class VillainDecisionResult:
    action: ActionType
    node: str
    note: str
    probabilities: dict[str, float]
    bet_size_key: str | None = None
    bet_size_frac: float | None = None
    raise_size_key: str | None = None
    raise_size_mult: float | None = None
    sampled_menu_key: str | None = None
    selection_mode: str | None = None
    pred_top_action: str | None = None
    pred_top_action_probability: float | None = None
    pred_second_action: str | None = None
    pred_second_action_probability: float | None = None
    pred_top_action_margin: float | None = None
    selection_confidence_band: str | None = None


@lru_cache(maxsize=1)
def _load_runtime_modules():
    try:
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
        import sklearn  # noqa: F401 # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Predictive villain runtime requires numpy, pandas, scikit-learn, and catboost."
        ) from exc
    return np, pd


@lru_cache(maxsize=None)
def _load_artifact(path_str: str) -> dict:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Missing predictive villain model artifact: {path}")
    try:
        with path.open("rb") as f:
            return pickle.load(f)
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "Failed to load predictive villain model artifacts. Install CatBoost and scikit-learn."
        ) from exc


@lru_cache(maxsize=1)
def _load_v5_blend_config() -> dict:
    if not V5_BLEND_CONFIG_FILE.exists():
        raise FileNotFoundError(f"Missing V5 blend config: {V5_BLEND_CONFIG_FILE}")
    data = json.loads(V5_BLEND_CONFIG_FILE.read_text(encoding="utf-8"))
    for key in ("node_global_blend_weights", "villain_node_blend_weights", "villain_node_street_blend_weights"):
        data.setdefault(key, {})
    return data


@lru_cache(maxsize=1)
def _fixed_hero_combos() -> tuple[tuple[str, str], ...]:
    return tuple(bz.expand_range_to_combos(list(bz.HERO_RANGE_TOKENS)))


def _safe_prob_for_label(classes: list[str], probs, label: str) -> float:
    if label not in classes:
        return 0.0
    idx = classes.index(label)
    return float(probs[idx])


def _stable_seed(*parts: object) -> int:
    material = "||".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _resolved_seed(base_seed: int | None, *parts: object) -> int:
    if base_seed is None:
        return _stable_seed("system", *parts)
    return _stable_seed(base_seed, *parts)


def _make_rng(base_seed: int | None, *parts: object) -> random.Random:
    return random.Random(_resolved_seed(base_seed, *parts))


def _normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    total = float(sum(max(0.0, float(v)) for v in probs.values()))
    if total <= 0.0:
        n = len(probs) or 1
        return {k: 1.0 / n for k in probs} if probs else {}
    return {k: max(0.0, float(v)) / total for k, v in probs.items()}


def _sample_action_from_probs(probs: dict[str, float], rng: random.Random) -> str:
    positive = [(label, max(0.0, float(prob))) for label, prob in probs.items()]
    total = sum(prob for _, prob in positive)
    if total <= 0:
        return max(probs, key=probs.get)
    roll = rng.random() * total
    cumulative = 0.0
    for label, prob in positive:
        cumulative += prob
        if roll <= cumulative:
            return label
    return positive[-1][0]


def _action_tie_break_index(label: str) -> int:
    # Stable deterministic ordering for exact ties. Aggressive/continue options are
    # preferred over folds so reps advance through the most instructive line.
    tie_break_order = ["b", "r", "c", "x", "f"]
    try:
        return tie_break_order.index(label)
    except ValueError:
        return len(tie_break_order)


def _select_top_action_from_probs(probs: dict[str, float]) -> str:
    normalized = _normalize_probs(probs)
    if not normalized:
        raise ValueError("cannot select action from empty probability map")

    return max(
        normalized,
        key=lambda label: (
            float(normalized.get(label, 0.0)),
            -_action_tie_break_index(label),
        ),
    )


def _action_selection_metadata(probs: dict[str, float]) -> dict[str, object]:
    normalized = _normalize_probs(probs)
    ranked = sorted(
        normalized.items(),
        key=lambda item: (-float(item[1]), _action_tie_break_index(item[0]), item[0]),
    )

    top_action = ranked[0][0] if ranked else None
    top_prob = float(ranked[0][1]) if ranked else 0.0
    second_action = ranked[1][0] if len(ranked) > 1 else None
    second_prob = float(ranked[1][1]) if len(ranked) > 1 else 0.0
    margin = top_prob - second_prob

    if top_prob >= 0.70 or margin >= 0.25:
        band = "clear"
    elif margin >= 0.10:
        band = "lean"
    else:
        band = "mixed"

    return {
        "selection_mode": "top_action",
        "pred_top_action": top_action,
        "pred_top_action_probability": top_prob,
        "pred_second_action": second_action,
        "pred_second_action_probability": second_prob,
        "pred_top_action_margin": margin,
        "selection_confidence_band": band,
    }


def _selection_result_kwargs(selection_meta: dict[str, object]) -> dict[str, object]:
    return {
        "selection_mode": str(selection_meta["selection_mode"]),
        "pred_top_action": selection_meta["pred_top_action"],
        "pred_top_action_probability": float(selection_meta["pred_top_action_probability"]),
        "pred_second_action": selection_meta["pred_second_action"],
        "pred_second_action_probability": float(selection_meta["pred_second_action_probability"]),
        "pred_top_action_margin": float(selection_meta["pred_top_action_margin"]),
        "selection_confidence_band": str(selection_meta["selection_confidence_band"]),
    }


def _clip_prob(value: float) -> float:
    np, _ = _load_runtime_modules()
    return float(np.clip(value, 0.0, 1.0))


def _clip_open_bet_pct_pot(value: float) -> float:
    np, _ = _load_runtime_modules()
    return float(np.clip(value, 0.25, 2.00))


def _clip_raise_multiple(value: float) -> float:
    np, _ = _load_runtime_modules()
    return float(np.clip(value, 2.00, 7.00))


def _clip_reraise_multiple(value: float) -> float:
    np, _ = _load_runtime_modules()
    return float(np.clip(value, 2.00, 10.00))


def _bet_size_key_from_fraction(fraction: float) -> str:
    if fraction <= 0.50:
        return "small"
    if fraction <= 1.00:
        return "medium"
    if fraction <= 1.25:
        return "big"
    return "overbet"


def _raise_size_key_from_multiple(mult: float) -> str:
    if mult <= 2.75:
        return "small"
    if mult <= 4.00:
        return "normal"
    return "big"


def _normalize_node(node_hint: str | None, to_call: float) -> str:
    if node_hint == "unopened":
        return "open_action"
    if node_hint == "facing_raise":
        return "facing_raise"
    if to_call > 0:
        return "facing_bet"
    return "open_action"


def _events_for_street(history_events: Iterable[ActionEvent] | None, street_name: str) -> list[ActionEvent]:
    if not history_events:
        return []
    out: list[ActionEvent] = []
    for event in history_events:
        if getattr(event, "forced", False):
            continue
        event_street = event.street.value if hasattr(event.street, "value") else str(event.street)
        if event_street == street_name:
            out.append(event)
    return out


def _previous_street_name(street: str) -> str | None:
    return {"turn": "flop", "river": "turn"}.get(street)


def _sum_action_amounts(events: list[ActionEvent]) -> float:
    return float(sum(float(event.amount or 0.0) for event in events))


def _street_start_pot_for(scenario_id: str, history_events: Iterable[ActionEvent] | None, target_street: str) -> float:
    scenario = get_scenario(scenario_id)
    pot = round(max(1.0, float(scenario.default_pot)), 1)
    for street_name in ("flop", "turn", "river"):
        if street_name == target_street:
            return float(pot)
        pot = round(max(1.0, pot + _sum_action_amounts(_events_for_street(history_events, street_name))), 1)
    return float(pot)


def _derive_board_state_flags(board: Sequence[str]) -> BoardStateFlags:
    texture = evaluate_board_texture(list(board))
    monotone = bool(texture.board_is_monotone)
    flush_completed = bool(texture.flush_completed)
    two_tone = bool(texture.flush_draw_present and not flush_completed and not monotone)
    rainbow = bool((not texture.flush_draw_present) and (not flush_completed) and (not monotone))
    connected = bool(texture.straight_draw_present and not texture.straight_completed)
    return BoardStateFlags(
        paired=bool(texture.paired_board),
        rainbow=rainbow,
        monotone=monotone,
        two_tone=two_tone,
        flush_completed=flush_completed,
        straight_completed=bool(texture.straight_completed),
        connected=connected,
    )


def _derive_board_high_card_bucket(board: Sequence[str]) -> str:
    high_ranks = {"Q", "K", "A"}
    max_rank = max((card[0] for card in board), key=lambda rank: bz.RANK_TO_VALUE[rank])
    return "high" if max_rank in high_ranks else "low"


def _scenario_hero_range_tokens(scenario_id: str) -> tuple[str, ...] | None:
    try:
        scenario = get_scenario(scenario_id)
    except Exception:
        return None
    tokens = getattr(scenario, "hero_range_tokens", None)
    if not tokens:
        return None
    return tuple(str(token) for token in tokens)


def _compute_hand_strength_context(
    *,
    villain_type: str,
    scenario_id: str,
    street: str,
    villain_hand: Sequence[str],
    board: Sequence[str],
    iters: int | None,
) -> tuple[float, float, str]:
    normalized_board = normalize_cards(list(board))
    normalized_hole = normalize_cards(list(villain_hand))
    hole = tuple(sorted((normalized_hole[0], normalized_hole[1])))
    scenario_tokens = _scenario_hero_range_tokens(scenario_id)
    hero_mix = bz.selected_hero_range_mix(
        villain_profile_id=villain_type,
        scenario_hero_range_tokens=scenario_tokens,
    )
    if len(normalized_board) == 5:
        equity = bz.equity_vs_hybrid_hero_range_river_exact(hole, normalized_board, hero_mix)
    else:
        resolved_iters = bz.resolve_iters(normalized_board, iters)
        equity = bz.equity_vs_hybrid_hero_range_mc(
            villain_hole=hole,
            board=normalized_board,
            hero_mix=hero_mix,
            iters=resolved_iters,
            equity_base_seed=_stable_seed(villain_type, scenario_id, street, ''.join(normalized_board), ''.join(normalized_hole)),
            purpose="runtime_predictor_equity",
        )
    current_strength = bz.current_score_vs_hybrid_hero_range_exact(hole, normalized_board, hero_mix)
    subgroup = bz.subgroup_of(hole, normalized_board)
    return float(equity), float(current_strength), subgroup


def _previous_action_summary(street: str, history_events: Iterable[ActionEvent] | None) -> str:
    if street == "flop" or not history_events:
        return "NA"
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return "NA"
    previous_events = _events_for_street(history_events, previous_street)
    if not previous_events:
        return "NA"
    return ">".join(
        f"{event.actor.value if hasattr(event.actor, 'value') else str(event.actor)}_"
        f"{event.action.value if hasattr(event.action, 'value') else str(event.action)}"
        for event in previous_events
    )


def _derive_current_aggressor(street: str, history_events: Iterable[ActionEvent] | None) -> str:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return "NA"
    last_aggressor: str | None = None
    for event in _events_for_street(history_events, previous_street):
        action = event.action.value if hasattr(event.action, 'value') else str(event.action)
        if action in {"bet", "raise"}:
            last_aggressor = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
    return last_aggressor or "none"


def _derive_previous_street_villain_last_action(street: str, history_events: Iterable[ActionEvent] | None) -> str:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return "NA"
    villain_events = [event for event in _events_for_street(history_events, previous_street) if (event.actor.value if hasattr(event.actor,'value') else str(event.actor)) == 'villain']
    if not villain_events:
        return "NA"
    action = villain_events[-1].action.value if hasattr(villain_events[-1].action, 'value') else str(villain_events[-1].action)
    return action if action in {"check", "call", "bet", "raise"} else "NA"


def _derive_hero_prev_street_last_action_type(street: str, history_events: Iterable[ActionEvent] | None) -> str:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return "NA"
    hero_events = [event for event in _events_for_street(history_events, previous_street) if (event.actor.value if hasattr(event.actor,'value') else str(event.actor)) == 'hero']
    if not hero_events:
        return "NA"
    last_event = hero_events[-1]
    action = last_event.action.value if hasattr(last_event.action, 'value') else str(last_event.action)
    if action == 'check':
        return 'check'
    if action == 'bet':
        return 'bet'
    if action == 'raise':
        return 'raise'
    if action == 'call':
        had_previous_raise = any((e.action.value if hasattr(e.action,'value') else str(e.action)) == 'raise' for e in _events_for_street(history_events, previous_street))
        return 'call_raise' if had_previous_raise else 'call_bet'
    return 'NA'


def _derive_hero_prev_street_last_aggressive_size_pct_pot(street: str, scenario_id: str, history_events: Iterable[ActionEvent] | None) -> float:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return 0.0
    street_start_pot = _street_start_pot_for(scenario_id, history_events, previous_street)
    if street_start_pot <= 0:
        return 0.0
    hero_aggressive = [e for e in _events_for_street(history_events, previous_street) if (e.actor.value if hasattr(e.actor,'value') else str(e.actor)) == 'hero' and ((e.action.value if hasattr(e.action,'value') else str(e.action)) in {'bet','raise'})]
    if not hero_aggressive:
        return 0.0
    return float(round(float(hero_aggressive[-1].amount or 0.0) / street_start_pot, 6))


def _derive_hero_prev_street_total_investment_pct_pot(street: str, scenario_id: str, history_events: Iterable[ActionEvent] | None) -> float:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return 0.0
    street_start_pot = _street_start_pot_for(scenario_id, history_events, previous_street)
    if street_start_pot <= 0:
        return 0.0
    total = sum(float(e.amount or 0.0) for e in _events_for_street(history_events, previous_street) if (e.actor.value if hasattr(e.actor,'value') else str(e.actor)) == 'hero' and ((e.action.value if hasattr(e.action,'value') else str(e.action)) in {'bet','raise','call'}))
    return float(round(total / street_start_pot, 6))


def _derive_hero_prev_street_called_raise(street: str, history_events: Iterable[ActionEvent] | None) -> bool:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return False
    events = _events_for_street(history_events, previous_street)
    for idx, event in enumerate(events):
        actor = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
        action = event.action.value if hasattr(event.action, 'value') else str(event.action)
        if actor == 'hero' and action == 'call':
            if any((e.action.value if hasattr(e.action,'value') else str(e.action)) == 'raise' for e in events[:idx]):
                return True
    return False


def _derive_previous_street_ended_aggressive(street: str, history_events: Iterable[ActionEvent] | None) -> bool:
    previous_street = _previous_street_name(street)
    if previous_street is None:
        return False
    return any((e.action.value if hasattr(e.action,'value') else str(e.action)) in {'bet','raise'} for e in _events_for_street(history_events, previous_street))


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _derive_opponent_perceived_strength(
    *,
    street: str,
    node: str,
    scenario_id: str,
    history_events: Iterable[ActionEvent] | None,
) -> float:
    last_action_type = _derive_hero_prev_street_last_action_type(street, history_events)
    if last_action_type == 'NA':
        return 0.0
    last_aggr_size_pct_pot = _derive_hero_prev_street_last_aggressive_size_pct_pot(street, scenario_id, history_events)
    total_invest_pct_pot = _derive_hero_prev_street_total_investment_pct_pot(street, scenario_id, history_events)
    called_raise = _derive_hero_prev_street_called_raise(street, history_events)
    ended_aggressive = _derive_previous_street_ended_aggressive(street, history_events)
    current_aggressor = _derive_current_aggressor(street, history_events)
    base = {'check': -0.80, 'call_bet': 0.08, 'call_raise': 0.58, 'bet': 0.80, 'raise': 1.18}.get(last_action_type, 0.0)
    size_bonus = _clamp(0.55 * float(last_aggr_size_pct_pot), 0.0, 0.85)
    invest_bonus = _clamp(0.18 * float(total_invest_pct_pot), 0.0, 0.45)
    facing_bonus = 0.18 if node == 'facing_bet' else (0.42 if node == 'facing_raise' else 0.0)
    aggressor_bonus = 0.15 if current_aggressor == 'hero' else 0.0
    line_bonus = 0.10 if ended_aggressive and last_action_type in {'bet', 'raise'} else 0.0
    call_raise_bonus = 0.14 if called_raise else 0.0
    score = base
    if last_action_type in {'bet', 'raise'}:
        score += size_bonus
    score += invest_bonus + facing_bonus + aggressor_bonus + line_bonus + call_raise_bonus
    if last_action_type == 'check' and not ended_aggressive:
        score -= 0.08
    return round(_clamp(score, -2.5, 2.5), 6)


def _is_made_hand_subgroup(subgroup: str) -> bool:
    return subgroup in {
        'Overpair', 'Top Pair', 'Mid Pair', 'Low Pair', 'Two Pair', 'Trips', 'Set',
        'Straight', 'Flush', 'Full House', 'Quads', 'Straight Flush',
    }


def _compute_vulnerability_score(*, street: str, villain_is_ip: bool, hand_equity: float, hand_subgroup: str, board_state: BoardStateFlags) -> float:
    if street == 'river' or not _is_made_hand_subgroup(hand_subgroup):
        return 0.0
    texture_pressure = (0.65 * float(board_state.connected)) + (0.35 * float(board_state.two_tone))
    if texture_pressure <= 0.0:
        return 0.0
    position_multiplier = 1.0 if villain_is_ip else 1.10
    return float(round(max(0.0, hand_equity * texture_pressure * position_multiplier), 6))


def _equity_bucket(hand_equity: float) -> str:
    value = float(hand_equity)
    if value < 0.15:
        return 'eq_00_15'
    if value < 0.30:
        return 'eq_15_30'
    if value < 0.45:
        return 'eq_30_45'
    if value < 0.60:
        return 'eq_45_60'
    if value < 0.75:
        return 'eq_60_75'
    if value < 0.90:
        return 'eq_75_90'
    return 'eq_90_100'


def _opponent_perceived_strength_bucket(score: float) -> str:
    if score <= -0.75:
        return 'very_weak'
    if score <= -0.15:
        return 'weak'
    if score < 0.35:
        return 'neutral'
    if score < 0.95:
        return 'strong'
    return 'very_strong'


def _spr_bucket(spr: float) -> str:
    value = float(spr)
    if value < 2.0:
        return 'spr_lt_2'
    if value < 4.0:
        return 'spr_2_4'
    if value < 8.0:
        return 'spr_4_8'
    return 'spr_ge_8'


def _facing_size_bucket(facing_size_pct_pot: float) -> str:
    value = float(facing_size_pct_pot)
    if value <= 0.33:
        return 'tiny'
    if value <= 0.66:
        return 'small'
    if value <= 1.00:
        return 'medium'
    if value <= 1.50:
        return 'large'
    return 'overbet'


def _board_type_compact(flags: BoardStateFlags) -> str:
    if flags.flush_completed and flags.straight_completed:
        return 'flush_and_straight_complete'
    if flags.flush_completed:
        return 'flush_complete'
    if flags.straight_completed:
        return 'straight_complete'
    pair_tag = 'paired' if flags.paired else 'unpaired'
    if flags.monotone:
        tone_tag = 'monotone'
    elif flags.two_tone:
        tone_tag = 'two_tone'
    elif flags.rainbow:
        tone_tag = 'rainbow'
    else:
        tone_tag = 'mixed'
    conn_tag = 'connected' if flags.connected else 'disconnected'
    return f'{pair_tag}_{tone_tag}_{conn_tag}'


def _derive_draw_missed(*, street: str, flags: BoardStateFlags) -> bool:
    if street != 'river':
        return False
    missed_flush = bool(flags.two_tone and not flags.flush_completed)
    missed_straight = bool(flags.connected and not flags.straight_completed)
    return bool(missed_flush or missed_straight)


def _vulnerability_bucket(vulnerability_score: float, hand_subgroup: str) -> str:
    subgroup = str(hand_subgroup or 'NA')
    if subgroup in {'Air', 'Gutshot', 'Straight Draw', 'Flush Draw', 'Combo Draw'} or 'Draw' in subgroup:
        return 'not_applicable'
    value = float(vulnerability_score)
    if value <= 0.05:
        return 'very_low'
    if value <= 0.20:
        return 'low'
    if value <= 0.40:
        return 'medium'
    if value <= 0.65:
        return 'high'
    return 'very_high'


def _pot_size_bucket(pot_size: float) -> str:
    value = float(pot_size)
    if value < 10.0:
        return 'pot_lt_10'
    if value < 25.0:
        return 'pot_10_25'
    if value < 60.0:
        return 'pot_25_60'
    if value < 120.0:
        return 'pot_60_120'
    return 'pot_ge_120'


def _adapt_spot(*, villain_type: str, scenario_id: str, street: str, node: str, villain_is_ip: bool, pot: float, effective_stack_size: float, facing_size_raw: float, villain_hand: Sequence[str], board: Sequence[str], history_events: Iterable[ActionEvent] | None) -> RuntimeSpot:
    open_action_type = None
    if node == 'open_action':
        open_action_type = 'checked_to' if villain_is_ip else 'first_to_act'
    facing_kind = 'none' if node == 'open_action' else ('bet' if node == 'facing_bet' else 'raise')
    legal_actions = ['x','b'] if node == 'open_action' else ['f','c','r']
    parts = [villain_type, scenario_id, street, node, ''.join(sorted(villain_hand)), ''.join(sorted(board)), f'{pot:.3f}', f'{effective_stack_size:.3f}', f'{facing_size_raw:.3f}']
    spot_id = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:20]
    adapted_events: list[PriorActionEventState] = []
    for event in history_events or []:
        if getattr(event, 'forced', False):
            continue
        adapted_events.append(PriorActionEventState(
            street=event.street.value if hasattr(event.street,'value') else str(event.street),
            actor=event.actor.value if hasattr(event.actor,'value') else str(event.actor),
            action=event.action.value if hasattr(event.action,'value') else str(event.action),
            amount=float(event.amount or 0.0),
        ))
    return RuntimeSpot(
        spot_id=spot_id,
        villain_type=villain_type,
        scenario_id=scenario_id,
        street=street,
        node=node,
        open_action_type=open_action_type,
        villain_is_ip=bool(villain_is_ip),
        pot_size=float(pot),
        effective_stack_size=float(effective_stack_size),
        board=list(board),
        villain_hand=list(villain_hand),
        prior_actions=adapted_events,
        facing_action=FacingActionState(kind=facing_kind, amount=None if facing_kind == 'none' else float(facing_size_raw)),
        legal_actions=legal_actions,
    )


def _derive_flat_predictors(*, villain_type: str, scenario_id: str, street: str, node: str, villain_is_ip: bool, pot: float, effective_stack_size: float, facing_size_raw: float, villain_hand: Sequence[str], board: Sequence[str], history_events: Iterable[ActionEvent] | None, iters: int | None) -> dict[str, object]:
    hand_equity, current_strength, hand_subgroup = _compute_hand_strength_context(villain_type=villain_type, scenario_id=scenario_id, street=street, villain_hand=villain_hand, board=board, iters=iters)
    board_state = _derive_board_state_flags(board)
    spr = float(effective_stack_size / pot) if pot > 0 else 0.0
    facing_size_pct_pot = float(facing_size_raw / pot) if pot > 0 else 0.0
    facing_size_pct_stack = float(facing_size_raw / effective_stack_size) if effective_stack_size > 0 else 0.0
    current_aggressor = _derive_current_aggressor(street, history_events)
    previous_street_villain_last_action = _derive_previous_street_villain_last_action(street, history_events)
    hero_prev_street_last_action_type = _derive_hero_prev_street_last_action_type(street, history_events)
    hero_prev_street_last_aggressive_size_pct_pot = _derive_hero_prev_street_last_aggressive_size_pct_pot(street, scenario_id, history_events)
    hero_prev_street_total_investment_pct_pot = _derive_hero_prev_street_total_investment_pct_pot(street, scenario_id, history_events)
    hero_prev_street_called_raise = _derive_hero_prev_street_called_raise(street, history_events)
    previous_street_ended_aggressive = _derive_previous_street_ended_aggressive(street, history_events)
    opponent_perceived_strength = _derive_opponent_perceived_strength(street=street, node=node, scenario_id=scenario_id, history_events=history_events)
    board_high_card_bucket = _derive_board_high_card_bucket(board)
    vulnerability_score = _compute_vulnerability_score(street=street, villain_is_ip=villain_is_ip, hand_equity=hand_equity, hand_subgroup=hand_subgroup, board_state=board_state)
    return {
        'feature_version': 'v4',
        'villain_type': villain_type,
        'scenario_id': scenario_id,
        'street': street,
        'node': node,
        'open_action_type': ('checked_to' if villain_is_ip else 'first_to_act') if node == 'open_action' else None,
        'villain_is_ip': bool(villain_is_ip),
        'pot_size': float(pot),
        'effective_stack_size': float(effective_stack_size),
        'spr': float(spr),
        'facing_size_raw': float(facing_size_raw),
        'facing_size_pct_pot': float(facing_size_pct_pot),
        'facing_size_pct_stack': float(facing_size_pct_stack),
        'hand_equity': float(hand_equity),
        'current_strength': float(current_strength),
        'hand_subgroup': hand_subgroup,
        'previous_action_summary': _previous_action_summary(street, history_events),
        'current_aggressor': current_aggressor,
        'previous_street_villain_last_action': previous_street_villain_last_action,
        'hero_prev_street_last_action_type': hero_prev_street_last_action_type,
        'hero_prev_street_last_aggressive_size_pct_pot': float(hero_prev_street_last_aggressive_size_pct_pot),
        'hero_prev_street_total_investment_pct_pot': float(hero_prev_street_total_investment_pct_pot),
        'hero_prev_street_called_raise': bool(hero_prev_street_called_raise),
        'previous_street_ended_aggressive': bool(previous_street_ended_aggressive),
        'opponent_perceived_strength': float(opponent_perceived_strength),
        'board_high_card_bucket': board_high_card_bucket,
        'board_paired': board_state.paired,
        'board_rainbow': board_state.rainbow,
        'board_monotone': board_state.monotone,
        'board_two_tone': board_state.two_tone,
        'board_flush_completed': board_state.flush_completed,
        'board_straight_completed': board_state.straight_completed,
        'board_connected': board_state.connected,
        'vulnerability_score': float(vulnerability_score),
    }


def _build_v2_action_feature_dict(flat: dict[str, object], *, node: str) -> dict[str, object]:
    villain_type = str(flat.get('villain_type') or 'NA')
    hand_equity = float(flat.get('hand_equity') or 0.0)
    spr = float(flat.get('spr') or 0.0)
    facing_size_pct_pot = float(flat.get('facing_size_pct_pot') or 0.0)
    opp_strength = float(flat.get('opponent_perceived_strength') or 0.0)
    flags = BoardStateFlags(
        paired=bool(flat.get('board_paired')),
        rainbow=bool(flat.get('board_rainbow')),
        monotone=bool(flat.get('board_monotone')),
        two_tone=bool(flat.get('board_two_tone')),
        flush_completed=bool(flat.get('board_flush_completed')),
        straight_completed=bool(flat.get('board_straight_completed')),
        connected=bool(flat.get('board_connected')),
    )
    hand_eq_bucket = _equity_bucket(hand_equity)
    opp_bucket = _opponent_perceived_strength_bucket(opp_strength)
    spr_bucket = _spr_bucket(spr)
    facing_bucket = _facing_size_bucket(facing_size_pct_pot)
    board_type = _board_type_compact(flags)
    vuln_bucket = _vulnerability_bucket(float(flat.get('vulnerability_score') or 0.0), str(flat.get('hand_subgroup') or 'NA'))
    draw_missed = _derive_draw_missed(street=str(flat.get('street') or 'NA'), flags=flags)
    out = {
        'feature_version': 'v4',
        'villain_type': villain_type,
        'scenario_id': flat.get('scenario_id'),
        'street': flat.get('street'),
        'open_action_type': flat.get('open_action_type'),
        'current_aggressor': flat.get('current_aggressor'),
        'previous_action_summary': flat.get('previous_action_summary'),
        'board_type_compact': board_type,
        'draw_missed': draw_missed,
        'hand_subgroup': flat.get('hand_subgroup'),
        'hand_equity': hand_equity,
        'hand_equity_bucket': hand_eq_bucket,
        'opponent_perceived_strength': opp_strength,
        'opponent_perceived_strength_bucket': opp_bucket,
        'spr': spr,
        'spr_bucket': spr_bucket,
        'facing_size_raw': flat.get('facing_size_raw'),
        'facing_size_pct_pot': flat.get('facing_size_pct_pot'),
        'facing_size_bucket': facing_bucket,
        'vulnerability_score': flat.get('vulnerability_score'),
        'vulnerability_bucket': vuln_bucket,
        'vx_hand_subgroup': f"{villain_type}__{flat.get('hand_subgroup')}",
        'vx_hand_equity_bucket': f"{villain_type}__{hand_eq_bucket}",
        'vx_previous_action_summary': f"{villain_type}__{flat.get('previous_action_summary')}",
        'vx_current_aggressor': f"{villain_type}__{flat.get('current_aggressor')}",
        'vx_scenario_id': f"{villain_type}__{flat.get('scenario_id')}",
        'vx_street': f"{villain_type}__{flat.get('street')}",
        'vx_spr_bucket': f"{villain_type}__{spr_bucket}",
        'vx_facing_size_bucket': f"{villain_type}__{facing_bucket}",
        'vx_vulnerability_bucket': f"{villain_type}__{vuln_bucket}",
        'vx_board_type_compact': f"{villain_type}__{board_type}",
    }
    return out


def _build_size_feature_dict_compact(flat: dict[str, object], model_kind: str) -> dict[str, object]:
    villain_type = str(flat.get('villain_type') or 'NA')
    hand_subgroup = str(flat.get('hand_subgroup') or 'NA')
    scenario_id = str(flat.get('scenario_id') or 'NA')
    street = str(flat.get('street') or 'NA')
    hand_equity = float(flat.get('hand_equity') or 0.0)
    current_strength = float(flat.get('current_strength') or 0.0)
    spr = float(flat.get('spr') or 0.0)
    vulnerability_score = float(flat.get('vulnerability_score') or 0.0)
    facing_size_raw = float(flat.get('facing_size_raw') or 0.0)
    facing_size_pct_pot = float(flat.get('facing_size_pct_pot') or 0.0)
    pot_size = float(flat.get('pot_size') or 0.0)
    flags = BoardStateFlags(
        paired=bool(flat.get('board_paired')),
        rainbow=bool(flat.get('board_rainbow')),
        monotone=bool(flat.get('board_monotone')),
        two_tone=bool(flat.get('board_two_tone')),
        flush_completed=bool(flat.get('board_flush_completed')),
        straight_completed=bool(flat.get('board_straight_completed')),
        connected=bool(flat.get('board_connected')),
    )
    hand_equity_bucket = _equity_bucket(hand_equity)
    current_strength_bucket = _equity_bucket(current_strength)
    spr_bucket = _spr_bucket(spr)
    vulnerability_bucket = _vulnerability_bucket(vulnerability_score, hand_subgroup)
    facing_size_bucket = _facing_size_bucket(facing_size_pct_pot)
    pot_size_bucket = _pot_size_bucket(pot_size)
    board_type_compact = _board_type_compact(flags)
    out: dict[str, object] = {
        'villain_type': villain_type,
        'hand_equity': hand_equity,
        'current_strength': current_strength,
        'current_strength_bucket': current_strength_bucket,
        'hand_equity_bucket': hand_equity_bucket,
        'hand_subgroup': hand_subgroup,
        'scenario_id': scenario_id,
        'street': street,
        'spr': spr,
        'spr_bucket': spr_bucket,
        'vulnerability_score': vulnerability_score,
        'vulnerability_bucket': vulnerability_bucket,
        'villain_is_ip': int(bool(flat.get('villain_is_ip'))),
        'vx_hand_equity_bucket': f'{villain_type}__{hand_equity_bucket}',
        'vx_current_strength_bucket': f'{villain_type}__{current_strength_bucket}',
        'vx_hand_subgroup': f'{villain_type}__{hand_subgroup}',
        'vx_scenario_id': f'{villain_type}__{scenario_id}',
        'vx_street': f'{villain_type}__{street}',
        'vx_spr_bucket': f'{villain_type}__{spr_bucket}',
        'vx_vulnerability_bucket': f'{villain_type}__{vulnerability_bucket}',
    }
    if model_kind == 'open_bet':
        out.update({
            'pot_size': pot_size,
            'pot_size_bucket': pot_size_bucket,
            'board_type_compact': board_type_compact,
            'vx_pot_size_bucket': f'{villain_type}__{pot_size_bucket}',
            'vx_board_type_compact': f'{villain_type}__{board_type_compact}',
        })
    else:
        out.update({
            'facing_size_raw': facing_size_raw,
            'facing_size_pct_pot': facing_size_pct_pot,
            'facing_size_bucket': facing_size_bucket,
            'vx_facing_size_bucket': f'{villain_type}__{facing_size_bucket}',
        })
    return out


def _build_size_feature_dict_context(flat: dict[str, object], model_kind: str) -> dict[str, object]:
    villain_type = str(flat.get('villain_type') or 'NA')
    hand_subgroup = str(flat.get('hand_subgroup') or 'NA')
    scenario_id = str(flat.get('scenario_id') or 'NA')
    street = str(flat.get('street') or 'NA')
    previous_action_summary = str(flat.get('previous_action_summary') or 'NA')
    current_aggressor = str(flat.get('current_aggressor') or 'NA')
    previous_street_villain_last_action = str(flat.get('previous_street_villain_last_action') or 'NA')
    hero_prev_street_last_action_type = str(flat.get('hero_prev_street_last_action_type') or 'NA')
    board_high_card_bucket = str(flat.get('board_high_card_bucket') or 'NA')
    hand_equity = float(flat.get('hand_equity') or 0.0)
    current_strength = float(flat.get('current_strength') or 0.0)
    spr = float(flat.get('spr') or 0.0)
    vulnerability_score = float(flat.get('vulnerability_score') or 0.0)
    facing_size_raw = float(flat.get('facing_size_raw') or 0.0)
    facing_size_pct_pot = float(flat.get('facing_size_pct_pot') or 0.0)
    facing_size_pct_stack = float(flat.get('facing_size_pct_stack') or 0.0)
    pot_size = float(flat.get('pot_size') or 0.0)
    effective_stack_size = float(flat.get('effective_stack_size') or 0.0)
    opp_strength = float(flat.get('opponent_perceived_strength') or 0.0)
    flags = BoardStateFlags(
        paired=bool(flat.get('board_paired')),
        rainbow=bool(flat.get('board_rainbow')),
        monotone=bool(flat.get('board_monotone')),
        two_tone=bool(flat.get('board_two_tone')),
        flush_completed=bool(flat.get('board_flush_completed')),
        straight_completed=bool(flat.get('board_straight_completed')),
        connected=bool(flat.get('board_connected')),
    )
    hand_equity_bucket = _equity_bucket(hand_equity)
    current_strength_bucket = _equity_bucket(current_strength)
    spr_bucket = _spr_bucket(spr)
    vulnerability_bucket = _vulnerability_bucket(vulnerability_score, hand_subgroup)
    facing_size_bucket = _facing_size_bucket(facing_size_pct_pot)
    pot_size_bucket = _pot_size_bucket(pot_size)
    board_type_compact = _board_type_compact(flags)
    out = {
        'villain_type': villain_type,
        'scenario_id': scenario_id,
        'street': street,
        'villain_is_ip': int(bool(flat.get('villain_is_ip'))),
        'pot_size': pot_size,
        'effective_stack_size': effective_stack_size,
        'spr': spr,
        'hand_equity': hand_equity,
        'current_strength': current_strength,
        'hand_subgroup': hand_subgroup,
        'previous_action_summary': previous_action_summary,
        'current_aggressor': current_aggressor,
        'previous_street_villain_last_action': previous_street_villain_last_action,
        'hero_prev_street_last_action_type': hero_prev_street_last_action_type,
        'hero_prev_street_last_aggressive_size_pct_pot': float(flat.get('hero_prev_street_last_aggressive_size_pct_pot') or 0.0),
        'hero_prev_street_total_investment_pct_pot': float(flat.get('hero_prev_street_total_investment_pct_pot') or 0.0),
        'hero_prev_street_called_raise': int(bool(flat.get('hero_prev_street_called_raise'))),
        'previous_street_ended_aggressive': int(bool(flat.get('previous_street_ended_aggressive'))),
        'opponent_perceived_strength': str(flat.get('opponent_perceived_strength') if flat.get('opponent_perceived_strength') is not None else 'NA'),
        'board_high_card_bucket': board_high_card_bucket,
        'board_paired': int(flags.paired),
        'board_rainbow': int(flags.rainbow),
        'board_monotone': int(flags.monotone),
        'board_two_tone': int(flags.two_tone),
        'board_flush_completed': int(flags.flush_completed),
        'board_straight_completed': int(flags.straight_completed),
        'board_connected': int(flags.connected),
        'vulnerability_score': vulnerability_score,
        'hand_equity_bucket': hand_equity_bucket,
        'current_strength_bucket': current_strength_bucket,
        'spr_bucket': spr_bucket,
        'vulnerability_bucket': vulnerability_bucket,
        'pot_size_bucket': pot_size_bucket,
        'board_type_compact': board_type_compact,
        'vx_hand_subgroup': f'{villain_type}__{hand_subgroup}',
        'vx_previous_action_summary': f'{villain_type}__{previous_action_summary}',
        'vx_scenario_id': f'{villain_type}__{scenario_id}',
        'vx_street': f'{villain_type}__{street}',
        'vx_hand_equity_bucket': f'{villain_type}__{hand_equity_bucket}',
        'vx_current_strength_bucket': f'{villain_type}__{current_strength_bucket}',
        'vx_spr_bucket': f'{villain_type}__{spr_bucket}',
        'vx_vulnerability_bucket': f'{villain_type}__{vulnerability_bucket}',
        'vx_board_type_compact': f'{villain_type}__{board_type_compact}',
        'sx_previous_action_summary': f'{scenario_id}__{previous_action_summary}',
        'sx_street': f'{scenario_id}__{street}',
    }
    if model_kind == 'open_bet':
        out.update({'open_action_type': str(flat.get('open_action_type') or 'NA'), 'vx_open_action_type': f"{villain_type}__{str(flat.get('open_action_type') or 'NA')}"})
    else:
        out.update({
            'facing_size_raw': facing_size_raw,
            'facing_size_pct_pot': facing_size_pct_pot,
            'facing_size_pct_stack': facing_size_pct_stack,
            'facing_size_bucket': facing_size_bucket,
            'vx_facing_size_bucket': f'{villain_type}__{facing_size_bucket}',
        })
    return out


def _build_size_feature_dict_v3(flat: dict[str, object], model_kind: str) -> dict[str, object]:
    out = _build_size_feature_dict_context(flat, model_kind)
    villain_type = str(out.get('villain_type') or 'NA')
    scenario_id = str(out.get('scenario_id') or 'NA')
    street = str(out.get('street') or 'NA')
    hand_subgroup = str(out.get('hand_subgroup') or 'NA')
    current_aggressor = str(out.get('current_aggressor') or 'NA')
    previous_summary = str(out.get('previous_action_summary') or 'NA')
    equity_bucket = str(out.get('hand_equity_bucket') or 'NA')
    current_strength_bucket = str(out.get('current_strength_bucket') or 'NA')
    spr_bucket = str(out.get('spr_bucket') or 'NA')
    board_type = str(out.get('board_type_compact') or 'NA')
    facing_size_bucket = str(out.get('facing_size_bucket') or 'NA')
    open_action_type = str(out.get('open_action_type') or 'NA')
    previous_villain_action = str(out.get('previous_street_villain_last_action') or 'NA')
    hero_prev_action = str(out.get('hero_prev_street_last_action_type') or 'NA')
    board_high = str(out.get('board_high_card_bucket') or 'NA')

    out.update({
        'vx_current_aggressor': f'{villain_type}__{current_aggressor}',
        'vx_previous_villain_action': f'{villain_type}__{previous_villain_action}',
        'vx_hero_prev_action': f'{villain_type}__{hero_prev_action}',
        'vx_board_high_card_bucket': f'{villain_type}__{board_high}',
        'vx_pot_size_bucket': f"{villain_type}__{out.get('pot_size_bucket')}",
        'vx_strength_spr': f'{villain_type}__{current_strength_bucket}__{spr_bucket}',
        'vx_equity_spr': f'{villain_type}__{equity_bucket}__{spr_bucket}',
        'vx_subgroup_board': f'{villain_type}__{hand_subgroup}__{board_type}',
        'vx_street_subgroup': f'{villain_type}__{street}__{hand_subgroup}',
        'vx_scenario_street': f'{villain_type}__{scenario_id}__{street}',
        'vx_scenario_subgroup': f'{villain_type}__{scenario_id}__{hand_subgroup}',
        'sx_subgroup': f'{scenario_id}__{hand_subgroup}',
        'sx_board_type': f'{scenario_id}__{board_type}',
        'sx_strength': f'{scenario_id}__{current_strength_bucket}',
        'street_subgroup': f'{street}__{hand_subgroup}',
        'street_board_type': f'{street}__{board_type}',
        'aggressor_previous': f'{current_aggressor}__{previous_summary}',
        'strength_board': f'{current_strength_bucket}__{board_type}',
    })
    if model_kind == 'open_bet':
        out['vx_open_action_strength'] = f'{villain_type}__{open_action_type}__{current_strength_bucket}'
    else:
        out['vx_facing_size_strength'] = f'{villain_type}__{facing_size_bucket}__{current_strength_bucket}'
        out['vx_facing_size_subgroup'] = f'{villain_type}__{facing_size_bucket}__{hand_subgroup}'
    return out


def _build_size_feature_dict_by_space(flat: dict[str, object], model_kind: str, feature_space: str) -> dict[str, object]:
    if feature_space == 'compact_v1':
        return _build_size_feature_dict_compact(flat, model_kind)
    if feature_space == 'context_v2':
        return _build_size_feature_dict_context(flat, model_kind)
    if feature_space == 'villain_context_v3':
        return _build_size_feature_dict_v3(flat, model_kind)
    return _build_size_feature_dict_context(flat, model_kind)


def _build_frame_catboost(feature_source: dict[str, object], artifact: dict):
    _, pd = _load_runtime_modules()
    feature_columns = list(artifact['feature_columns'])
    categorical_columns = set(artifact.get('categorical_feature_columns', []))
    row: dict[str, object] = {}
    for col in feature_columns:
        value = feature_source.get(col)
        if isinstance(value, bool):
            value = int(value)
        if col in categorical_columns:
            row[col] = 'NA' if value is None else str(value)
        else:
            row[col] = 0.0 if value is None else value
    return pd.DataFrame([row], columns=feature_columns)


def _predict_binary_probs_catboost(feature_source: dict[str, object], artifact: dict) -> dict[str, float]:
    np, _ = _load_runtime_modules()
    frame = _build_frame_catboost(feature_source, artifact)
    probs = np.asarray(artifact['model'].predict_proba(frame), dtype=float).reshape(-1)
    classes = list(artifact['classes'])
    return {label: _safe_prob_for_label(classes, probs, label) for label in classes}


def _predict_regression_catboost(feature_source: dict[str, object], artifact: dict) -> float:
    np, _ = _load_runtime_modules()
    frame = _build_frame_catboost(feature_source, artifact)
    pred = np.asarray(artifact['model'].predict(frame), dtype=float).reshape(-1)[0]
    if artifact.get('target_transform') == 'log':
        pred = float(np.exp(pred))
    return float(pred)


def _prepare_frame_v4(flat_predictors: dict[str, object], artifact: dict):
    _, pd = _load_runtime_modules()
    raw_columns = list(artifact['feature_columns_raw'])
    categorical_columns = list(artifact.get('categorical_feature_columns', []))
    data: dict[str, object] = {}
    for col in raw_columns:
        value = flat_predictors.get(col)
        if isinstance(value, bool):
            value = int(value)
        if col in categorical_columns:
            data[col] = 'NA' if value is None else str(value)
        else:
            data[col] = 0.0 if value is None else value
    frame_raw = pd.DataFrame([data], columns=raw_columns)
    frame_enc = pd.get_dummies(frame_raw, columns=categorical_columns, dummy_na=False)
    frame_enc = frame_enc.reindex(columns=artifact['feature_columns_encoded'], fill_value=0.0).astype(float)
    return frame_enc


def _predict_regression_v4(flat_predictors: dict[str, object], artifact: dict) -> float:
    np, _ = _load_runtime_modules()
    frame = _prepare_frame_v4(flat_predictors, artifact)
    pred = np.asarray(artifact['model'].predict(frame), dtype=float).reshape(-1)[0]
    return float(pred)


def _extract_action_probabilities_v1(spot: RuntimeSpot, result: dict[str, object]) -> dict[str, float]:
    if spot.node == 'open_action':
        return {'x': float(result.get('p_x') or 0.0), 'b': float(result.get('p_b') or 0.0)}
    return {'f': float(result.get('p_f') or 0.0), 'c': float(result.get('p_c') or 0.0), 'r': float(result.get('p_r') or 0.0)}


def _predict_v1(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, object]:
    result = {'status': 'ok', 'unavailable_reason': None, 'raw_action_probs': None, 'p_x': None, 'p_b': None, 'p_f': None, 'p_c': None, 'p_r': None}
    if spot.node == 'open_action':
        action_probs = _predict_binary_probs_catboost(flat, _load_artifact(str(OPEN_ACTION_MODEL_FILE)))
        result['p_x'] = float(action_probs.get('x', 0.0))
        result['p_b'] = float(action_probs.get('b', 0.0))
        result['raw_action_probs'] = {'x': result['p_x'], 'b': result['p_b']}
        return result
    if spot.node == 'facing_bet':
        stage1 = _predict_binary_probs_catboost(flat, _load_artifact(str(FACING_BET_FOLD_CONTINUE_MODEL_FILE)))
        p_fold = float(stage1.get('f', 0.0))
        p_continue = float(stage1.get('continue', 0.0))
        stage2 = _predict_binary_probs_catboost(flat, _load_artifact(str(FACING_BET_CALL_RAISE_MODEL_FILE)))
        p_call = p_continue * float(stage2.get('c', 0.0))
        p_raise = p_continue * float(stage2.get('r', 0.0))
    else:
        stage1 = _predict_binary_probs_catboost(flat, _load_artifact(str(FACING_RAISE_FOLD_CONTINUE_MODEL_FILE)))
        p_fold = float(stage1.get('f', 0.0))
        p_continue = float(stage1.get('continue', 0.0))
        stage2 = _predict_binary_probs_catboost(flat, _load_artifact(str(FACING_RAISE_CALL_RERAISE_MODEL_FILE)))
        p_call = p_continue * float(stage2.get('c', 0.0))
        p_raise = p_continue * float(stage2.get('r', 0.0))
    norm = _normalize_probs({'f': p_fold, 'c': p_call, 'r': p_raise})
    result.update({'p_f': norm['f'], 'p_c': norm['c'], 'p_r': norm['r'], 'raw_action_probs': dict(norm)})
    return result


def _predict_v2(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, object]:
    feats = _build_v2_action_feature_dict(flat, node=spot.node)
    result = {'status': 'ok', 'unavailable_reason': None, 'raw_action_probs': None, 'p_x': None, 'p_b': None, 'p_f': None, 'p_c': None, 'p_r': None}
    if spot.node == 'open_action':
        art = _load_artifact(str(OPEN_ACTION_MODEL_V2_FILE))
        probs = _predict_binary_probs_catboost(feats, art)
        norm = _normalize_probs({'x': float(probs.get('x', 0.0)), 'b': float(probs.get('b', 0.0))})
        result.update({'p_x': norm['x'], 'p_b': norm['b'], 'raw_action_probs': dict(norm)})
        return result
    if spot.node == 'facing_bet':
        s1 = _predict_binary_probs_catboost(feats, _load_artifact(str(FACING_BET_FOLD_CONTINUE_MODEL_V2_FILE)))
        s2 = _predict_binary_probs_catboost(feats, _load_artifact(str(FACING_BET_CALL_RAISE_MODEL_V2_FILE)))
    else:
        s1 = _predict_binary_probs_catboost(feats, _load_artifact(str(FACING_RAISE_FOLD_CONTINUE_MODEL_V2_FILE)))
        s2 = _predict_binary_probs_catboost(feats, _load_artifact(str(FACING_RAISE_CALL_RERAISE_MODEL_V2_FILE)))
    p_fold = float(s1.get('f', 0.0))
    p_continue = float(s1.get('continue', 0.0))
    p_call = p_continue * float(s2.get('c', 0.0))
    p_raise = p_continue * float(s2.get('r', 0.0))
    norm = _normalize_probs({'f': p_fold, 'c': p_call, 'r': p_raise})
    result.update({'p_f': norm['f'], 'p_c': norm['c'], 'p_r': norm['r'], 'raw_action_probs': dict(norm)})
    return result


def _predict_v3(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, object]:
    result = {'status': 'ok', 'unavailable_reason': None, 'raw_action_probs': None, 'p_x': None, 'p_b': None, 'p_f': None, 'p_c': None, 'p_r': None}
    if spot.node == 'open_action':
        art = _load_artifact(str(OPEN_ACTION_PROB_MODEL_V3_FILE))
        p_b = _clip_prob(_predict_regression_catboost(flat, art))
        norm = _normalize_probs({'x': 1.0 - p_b, 'b': p_b})
        result.update({'p_x': norm['x'], 'p_b': norm['b'], 'raw_action_probs': dict(norm)})
        return result
    if spot.node == 'facing_bet':
        s1 = _load_artifact(str(FACING_BET_CONTINUE_PROB_MODEL_V3_FILE))
        s2 = _load_artifact(str(FACING_BET_RAISE_GIVEN_CONTINUE_PROB_MODEL_V3_FILE))
    else:
        s1 = _load_artifact(str(FACING_RAISE_CONTINUE_PROB_MODEL_V3_FILE))
        s2 = _load_artifact(str(FACING_RAISE_RERAISE_GIVEN_CONTINUE_PROB_MODEL_V3_FILE))
    p_continue = _clip_prob(_predict_regression_catboost(flat, s1))
    p_raise_given = _clip_prob(_predict_regression_catboost(flat, s2))
    norm = _normalize_probs({'f': 1.0 - p_continue, 'c': max(0.0, p_continue - (p_continue * p_raise_given)), 'r': p_continue * p_raise_given})
    result.update({'p_f': norm['f'], 'p_c': norm['c'], 'p_r': norm['r'], 'raw_action_probs': dict(norm)})
    return result


def _predict_v4(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, object]:
    result = {'status': 'ok', 'unavailable_reason': None, 'raw_action_probs': None, 'p_x': None, 'p_b': None, 'p_f': None, 'p_c': None, 'p_r': None}
    if spot.node == 'open_action':
        art = _load_artifact(str(OPEN_ACTION_PROB_MODEL_V4_FILE))
        p_b = _clip_prob(_predict_regression_v4(flat, art))
        norm = _normalize_probs({'x': 1.0 - p_b, 'b': p_b})
        result.update({'p_x': norm['x'], 'p_b': norm['b'], 'raw_action_probs': dict(norm)})
        return result
    if spot.node == 'facing_bet':
        s1 = _load_artifact(str(FACING_BET_CONTINUE_PROB_MODEL_V4_FILE))
        s2 = _load_artifact(str(FACING_BET_RAISE_GIVEN_CONTINUE_PROB_MODEL_V4_FILE))
    else:
        s1 = _load_artifact(str(FACING_RAISE_CONTINUE_PROB_MODEL_V4_FILE))
        s2 = _load_artifact(str(FACING_RAISE_RERAISE_GIVEN_CONTINUE_PROB_MODEL_V4_FILE))
    p_continue = _clip_prob(_predict_regression_v4(flat, s1))
    p_raise_given = _clip_prob(_predict_regression_v4(flat, s2))
    norm = _normalize_probs({'f': 1.0 - p_continue, 'c': max(0.0, p_continue - (p_continue * p_raise_given)), 'r': p_continue * p_raise_given})
    result.update({'p_f': norm['f'], 'p_c': norm['c'], 'p_r': norm['r'], 'raw_action_probs': dict(norm)})
    return result


def _get_v5_weights(villain_type: str, node: str, street: str) -> tuple[dict[str, float], str]:
    cfg = _load_v5_blend_config()
    street_key = f'{villain_type}__{node}__{street}'
    if street_key in cfg.get('villain_node_street_blend_weights', {}):
        return _normalize_probs({k: float(v) for k, v in cfg['villain_node_street_blend_weights'][street_key].items()}), 'villain_node_street_local'
    vn_key = f'{villain_type}__{node}'
    if vn_key in cfg.get('villain_node_blend_weights', {}):
        return _normalize_probs({k: float(v) for k, v in cfg['villain_node_blend_weights'][vn_key].items()}), 'villain_node_local'
    if node in cfg.get('node_global_blend_weights', {}):
        return _normalize_probs({k: float(v) for k, v in cfg['node_global_blend_weights'][node].items()}), 'node_global_fallback'
    return {'v1': 1.0, 'v2': 0.0, 'v3': 0.0, 'v4': 0.0}, 'hardcoded_fallback'


def _blend_probs(spot: RuntimeSpot, weights: dict[str, float], version_probs: dict[str, dict[str, float]]) -> dict[str, float]:
    legal_actions = list(spot.legal_actions)
    blended = {a: 0.0 for a in legal_actions}
    total_weight = 0.0
    for version in MODEL_ORDER_V5:
        weight = float(weights.get(version, 0.0))
        if weight <= 0.0:
            continue
        probs = version_probs.get(version)
        if probs is None:
            continue
        norm = _normalize_probs({a: float(probs.get(a, 0.0)) for a in legal_actions})
        for action in legal_actions:
            blended[action] += weight * norm[action]
        total_weight += weight
    if total_weight <= 0.0:
        return _normalize_probs({a: 1.0 for a in legal_actions})
    return _normalize_probs({a: float(v) / total_weight for a, v in blended.items()})


def _predict_v5(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, object]:
    weights, scope = _get_v5_weights(spot.villain_type, spot.node, spot.street)
    v1 = _predict_v1(spot, flat)
    v2 = _predict_v2(spot, flat)
    v3 = _predict_v3(spot, flat)
    v4 = _predict_v4(spot, flat)
    version_probs = {
        'v1': dict(v1.get('raw_action_probs') or {}),
        'v2': dict(v2.get('raw_action_probs') or {}),
        'v3': dict(v3.get('raw_action_probs') or {}),
        'v4': dict(v4.get('raw_action_probs') or {}),
    }
    raw = _blend_probs(spot, weights, version_probs)
    return {
        'status': 'ok',
        'unavailable_reason': None,
        'blend_scope': scope,
        'blend_weights': dict(weights),
        'raw_action_probs': dict(raw),
        'expert_raw_action_probs': version_probs,
        'p_x': raw.get('x'),
        'p_b': raw.get('b'),
        'p_f': raw.get('f'),
        'p_c': raw.get('c'),
        'p_r': raw.get('r'),
    }


def _v6_artifact_file_for_node(node: str) -> Path:
    if node == 'open_action':
        return OPEN_ACTION_META_MODEL_V6_FILE
    if node == 'facing_bet':
        return FACING_BET_META_MODEL_V6_FILE
    if node == 'facing_raise':
        return FACING_RAISE_META_MODEL_V6_FILE
    raise ValueError(f'unsupported v6 node: {node}')


def _runtime_expert_probs_v6(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, dict[str, float]]:
    v1 = _predict_v1(spot, flat)
    v2 = _predict_v2(spot, flat)
    v3 = _predict_v3(spot, flat)
    v4 = _predict_v4(spot, flat)
    v5 = _predict_v5(spot, flat)
    return {
        'v1': dict(v1.get('raw_action_probs') or {}),
        'v2': dict(v2.get('raw_action_probs') or {}),
        'v3': dict(v3.get('raw_action_probs') or {}),
        'v4': dict(v4.get('raw_action_probs') or {}),
        'v5': dict(v5.get('raw_action_probs') or {}),
    }


def _predict_v6(spot: RuntimeSpot, flat: dict[str, object]) -> dict[str, object]:
    np, _ = _load_runtime_modules()
    node = str(spot.node)
    actions = ACTIONS_BY_NODE_V6[node]
    artifact = _load_artifact(str(_v6_artifact_file_for_node(node)))
    version_probs = _runtime_expert_probs_v6(spot, flat)
    meta_features = build_action_meta_features_v6(
        node=node,
        raw_context=flat,
        version_probs=version_probs,
    )
    frame = _build_frame_catboost(meta_features, artifact)
    pred = np.asarray(artifact['model'].predict(frame), dtype=float).reshape(-1)
    raw = _normalize_probs({action: float(value) for action, value in zip(actions, pred)})
    result: dict[str, object] = {
        'status': 'ok',
        'unavailable_reason': None,
        'raw_action_probs': dict(raw),
        'expert_raw_action_probs': version_probs,
        'model_version': 'v6',
        'p_x': raw.get('x'),
        'p_b': raw.get('b'),
        'p_f': raw.get('f'),
        'p_c': raw.get('c'),
        'p_r': raw.get('r'),
    }
    if node != 'open_action':
        p_continue = float(raw.get('c', 0.0)) + float(raw.get('r', 0.0))
        result['p_continue'] = p_continue
        if node == 'facing_bet':
            result['p_raise_given_continue'] = 0.0 if p_continue <= 1e-9 else float(raw.get('r', 0.0)) / p_continue
        else:
            result['p_reraise_given_continue'] = 0.0 if p_continue <= 1e-9 else float(raw.get('r', 0.0)) / p_continue
    return result


def _predict_size_v2(flat: dict[str, object], *, node: str) -> dict[str, float | None]:
    result = {
        'pred_open_bet_size_pct_pot_v2': None,
        'pred_raise_multiple_vs_facing_v2': None,
        'pred_reraise_multiple_vs_facing_v2': None,
    }
    if node == 'open_action':
        art = _load_artifact(str(OPEN_BET_SIZE_MODEL_V2_FILE))
        source = _build_size_feature_dict_context(flat, 'open_bet') if art.get('feature_space') != 'compact_v1' else _build_size_feature_dict_compact(flat, 'open_bet')
        result['pred_open_bet_size_pct_pot_v2'] = _clip_open_bet_pct_pot(_predict_regression_catboost(source, art))
        return result
    if node == 'facing_bet':
        art = _load_artifact(str(RAISE_VS_BET_SIZE_MODEL_V2_FILE))
        source = _build_size_feature_dict_context(flat, 'raise_vs_bet') if art.get('feature_space') != 'compact_v1' else _build_size_feature_dict_compact(flat, 'raise_vs_bet')
        result['pred_raise_multiple_vs_facing_v2'] = _clip_raise_multiple(_predict_regression_catboost(source, art))
        return result
    art = _load_artifact(str(RERAISE_VS_RAISE_SIZE_MODEL_V2_FILE))
    source = _build_size_feature_dict_context(flat, 'reraise_vs_raise') if art.get('feature_space') != 'compact_v1' else _build_size_feature_dict_compact(flat, 'reraise_vs_raise')
    result['pred_reraise_multiple_vs_facing_v2'] = _clip_reraise_multiple(_predict_regression_catboost(source, art))
    return result


def _predict_size_v3(flat: dict[str, object], *, spot: RuntimeSpot) -> dict[str, float | None]:
    result = {
        'pred_open_bet_size_pct_pot_v3': None,
        'pred_open_bet_size_raw_v3': None,
        'pred_raise_multiple_vs_facing_v3': None,
        'pred_reraise_multiple_vs_facing_v3': None,
        'pred_raise_to_raw_v3': None,
    }
    if spot.node == 'open_action':
        art = _load_artifact(str(OPEN_BET_SIZE_MODEL_V3_FILE))
        source = _build_size_feature_dict_by_space(flat, 'open_bet', str(art.get('feature_space') or 'villain_context_v3'))
        pred_pct = _clip_open_bet_pct_pot(_predict_regression_catboost(source, art))
        result['pred_open_bet_size_pct_pot_v3'] = pred_pct
        result['pred_open_bet_size_raw_v3'] = pred_pct * float(spot.pot_size)
        return result
    if spot.node == 'facing_bet':
        art = _load_artifact(str(RAISE_VS_BET_SIZE_MODEL_V3_FILE))
        source = _build_size_feature_dict_by_space(flat, 'raise_vs_bet', str(art.get('feature_space') or 'villain_context_v3'))
        pred_mult = _clip_raise_multiple(_predict_regression_catboost(source, art))
        result['pred_raise_multiple_vs_facing_v3'] = pred_mult
        result['pred_raise_to_raw_v3'] = pred_mult * float(spot.facing_action.amount or 0.0)
        return result
    art = _load_artifact(str(RERAISE_VS_RAISE_SIZE_MODEL_V3_FILE))
    source = _build_size_feature_dict_by_space(flat, 'reraise_vs_raise', str(art.get('feature_space') or 'villain_context_v3'))
    pred_mult = _clip_reraise_multiple(_predict_regression_catboost(source, art))
    result['pred_reraise_multiple_vs_facing_v3'] = pred_mult
    result['pred_raise_to_raw_v3'] = pred_mult * float(spot.facing_action.amount or 0.0)
    return result


def _format_probs_for_note(probs: dict[str, float]) -> str:
    pieces = [f'{label}={prob:.2f}' for label, prob in sorted(probs.items())]
    return ', '.join(pieces)


def validate_model_runtime() -> None:
    _load_runtime_modules()
    required = [
        OPEN_ACTION_MODEL_FILE,
        FACING_BET_FOLD_CONTINUE_MODEL_FILE,
        FACING_BET_CALL_RAISE_MODEL_FILE,
        FACING_RAISE_FOLD_CONTINUE_MODEL_FILE,
        FACING_RAISE_CALL_RERAISE_MODEL_FILE,
        OPEN_ACTION_MODEL_V2_FILE,
        FACING_BET_FOLD_CONTINUE_MODEL_V2_FILE,
        FACING_BET_CALL_RAISE_MODEL_V2_FILE,
        FACING_RAISE_FOLD_CONTINUE_MODEL_V2_FILE,
        FACING_RAISE_CALL_RERAISE_MODEL_V2_FILE,
        OPEN_ACTION_PROB_MODEL_V3_FILE,
        FACING_BET_CONTINUE_PROB_MODEL_V3_FILE,
        FACING_BET_RAISE_GIVEN_CONTINUE_PROB_MODEL_V3_FILE,
        FACING_RAISE_CONTINUE_PROB_MODEL_V3_FILE,
        FACING_RAISE_RERAISE_GIVEN_CONTINUE_PROB_MODEL_V3_FILE,
        OPEN_ACTION_PROB_MODEL_V4_FILE,
        FACING_BET_CONTINUE_PROB_MODEL_V4_FILE,
        FACING_BET_RAISE_GIVEN_CONTINUE_PROB_MODEL_V4_FILE,
        FACING_RAISE_CONTINUE_PROB_MODEL_V4_FILE,
        FACING_RAISE_RERAISE_GIVEN_CONTINUE_PROB_MODEL_V4_FILE,
        V5_BLEND_CONFIG_FILE,
        OPEN_ACTION_META_MODEL_V6_FILE,
        FACING_BET_META_MODEL_V6_FILE,
        FACING_RAISE_META_MODEL_V6_FILE,
        OPEN_BET_SIZE_MODEL_V2_FILE,
        RAISE_VS_BET_SIZE_MODEL_V2_FILE,
        RERAISE_VS_RAISE_SIZE_MODEL_V2_FILE,
        OPEN_BET_SIZE_MODEL_V3_FILE,
        RAISE_VS_BET_SIZE_MODEL_V3_FILE,
        RERAISE_VS_RAISE_SIZE_MODEL_V3_FILE,
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError('Missing predictive model artifacts:\n  - ' + '\n  - '.join(missing))
    _load_v5_blend_config()


def _fallback_villain_decision(*, node: str, can_raise: bool, facing_size_raw: float, pot: float, rng: random.Random) -> VillainDecisionResult:
    del rng
    pot = max(float(pot), 1.0)
    frac = max(0.0, float(facing_size_raw) / pot)
    if node == 'open_action':
        probs = {'x': 0.38, 'b': 0.62}
        selected = _select_top_action_from_probs(probs)
        selection_meta = _action_selection_metadata(probs)
        action = ActionType.BET if selected == 'b' else ActionType.CHECK
        bet_size_frac = 0.5 if action == ActionType.BET else None
        bet_size_key = _bet_size_key_from_fraction(bet_size_frac) if bet_size_frac is not None else None
        note = (
            f"fallback={node} selection=top_action "
            f"confidence={selection_meta['selection_confidence_band']} "
            f"[{_format_probs_for_note(probs)}]"
        )
        return VillainDecisionResult(
            action=action,
            node=node,
            note=note,
            probabilities=probs,
            bet_size_key=bet_size_key,
            bet_size_frac=bet_size_frac,
            sampled_menu_key=selected,
            **_selection_result_kwargs(selection_meta),
        )
    if can_raise:
        if frac <= 0.45:
            probs = {'f': 0.18, 'c': 0.58, 'r': 0.24}
        elif frac <= 1.0:
            probs = {'f': 0.28, 'c': 0.56, 'r': 0.16}
        else:
            probs = {'f': 0.42, 'c': 0.48, 'r': 0.10}
    else:
        probs = {'f': 0.34 if frac > 0.9 else 0.24, 'c': 0.66 if frac > 0.9 else 0.76, 'r': 0.0}
    selected = _select_top_action_from_probs(probs)
    selection_meta = _action_selection_metadata(probs)
    action = ActionType.FOLD if selected == 'f' else (ActionType.RAISE if selected == 'r' else ActionType.CALL)
    raise_size_mult = 3.0 if action == ActionType.RAISE else None
    raise_size_key = _raise_size_key_from_multiple(raise_size_mult) if raise_size_mult is not None else None
    note = (
        f"fallback={node} selection=top_action "
        f"confidence={selection_meta['selection_confidence_band']} "
        f"[{_format_probs_for_note(probs)}]"
    )
    return VillainDecisionResult(
        action=action,
        node=node,
        note=note,
        probabilities=probs,
        raise_size_key=raise_size_key,
        raise_size_mult=raise_size_mult,
        sampled_menu_key=selected,
        **_selection_result_kwargs(selection_meta),
    )


def choose_villain_action(
    *,
    villain_hand: tuple[str, str] | list[str],
    board: list[str] | tuple[str, ...],
    villain_profile_id: str,
    street: Street,
    to_call: float,
    pot: float,
    can_raise: bool = True,
    scenario_hero_range_tokens: Iterable[str] | None = None,
    iters: int | None = None,
    seed: int | None = 42,
    node_hint: str | None = None,
    villain_is_current_aggressor: bool | None = None,
    villain_is_pfa: bool | None = None,
    prior_villain_aggressive_actions: int = 0,
    prior_hero_aggressive_actions: int = 0,
    scenario_id: str | None = None,
    villain_is_ip: bool | None = None,
    history_events: Iterable[ActionEvent] | None = None,
    effective_stack_size: float | None = None,
) -> VillainDecisionResult:
    del scenario_hero_range_tokens, villain_is_current_aggressor, villain_is_pfa, prior_villain_aggressive_actions, prior_hero_aggressive_actions
    manifest_error: Exception | None = None
    try:
        validate_model_runtime()
    except Exception as exc:  # pragma: no cover
        manifest_error = exc

    profile = get_villain_profile(villain_profile_id)
    villain_type = getattr(getattr(profile, 'meta', None), 'display_name', None)
    if not villain_type:
        raise ValueError(f'Could not resolve display_name for villain profile: {villain_profile_id}')
    if villain_type not in ALLOWED_CALIBRATION_VILLAIN_NAMES:
        raise ValueError(f"Resolved unsupported model villain name '{villain_type}' for villain profile: {villain_profile_id}")

    street_key = street.value if hasattr(street, 'value') else str(street)
    resolved_scenario_id = scenario_id or 'unknown_scenario'
    villain_is_ip = bool(villain_is_ip) if villain_is_ip is not None else False
    node = _normalize_node(node_hint, float(to_call))
    facing_size_raw = float(to_call) if to_call > 0 else 0.0
    effective_stack = float(effective_stack_size if effective_stack_size is not None else pot)

    rng = _make_rng(seed, villain_profile_id, resolved_scenario_id, street_key, node, ','.join(sorted(villain_hand)), ','.join(sorted(board)), f'to_call={float(to_call):.4f}', f'pot={float(pot):.4f}')
    if manifest_error is not None:
        return _fallback_villain_decision(node=node, can_raise=can_raise, facing_size_raw=facing_size_raw, pot=float(pot), rng=rng)

    spot = _adapt_spot(villain_type=villain_type, scenario_id=resolved_scenario_id, street=street_key, node=node, villain_is_ip=villain_is_ip, pot=float(pot), effective_stack_size=effective_stack, facing_size_raw=facing_size_raw, villain_hand=list(villain_hand), board=list(board), history_events=history_events)
    flat = _derive_flat_predictors(villain_type=villain_type, scenario_id=resolved_scenario_id, street=street_key, node=node, villain_is_ip=villain_is_ip, pot=float(pot), effective_stack_size=effective_stack, facing_size_raw=facing_size_raw, villain_hand=list(villain_hand), board=list(board), history_events=history_events, iters=iters)
    v6 = _predict_v6(spot, flat)
    final_probs = dict(v6.get('raw_action_probs') or {})
    if not can_raise and 'r' in final_probs:
        final_probs['r'] = 0.0
    final_probs = _normalize_probs(final_probs)
    selected = _select_top_action_from_probs(final_probs)
    selection_meta = _action_selection_metadata(final_probs)
    if selected == 'f':
        action = ActionType.FOLD
    elif selected == 'r':
        action = ActionType.RAISE
    elif selected == 'b':
        action = ActionType.BET
    else:
        action = ActionType.CHECK if selected == 'x' else ActionType.CALL

    bet_size_frac = None
    bet_size_key = None
    raise_size_mult = None
    raise_size_key = None
    if node == 'open_action' and action == ActionType.BET:
        size_result = _predict_size_v3(flat, spot=spot)
        bet_size_frac = float(size_result['pred_open_bet_size_pct_pot_v3'] or 0.5)
        bet_size_key = _bet_size_key_from_fraction(bet_size_frac)
    elif node == 'facing_bet' and action == ActionType.RAISE:
        size_result = _predict_size_v3(flat, spot=spot)
        raise_size_mult = float(size_result['pred_raise_multiple_vs_facing_v3'] or 3.0)
        raise_size_key = _raise_size_key_from_multiple(raise_size_mult)
    elif node == 'facing_raise' and action == ActionType.RAISE:
        size_result = _predict_size_v3(flat, spot=spot)
        raise_size_mult = float(size_result['pred_reraise_multiple_vs_facing_v3'] or 3.0)
        raise_size_key = _raise_size_key_from_multiple(raise_size_mult)

    note = (
        f"model=v6 size_model=v3 selection=top_action "
        f"confidence={selection_meta['selection_confidence_band']} "
        f"[{_format_probs_for_note(final_probs)}]"
    )
    return VillainDecisionResult(
        action=action,
        node=node,
        note=note,
        probabilities=final_probs,
        bet_size_key=bet_size_key,
        bet_size_frac=bet_size_frac,
        raise_size_key=raise_size_key,
        raise_size_mult=raise_size_mult,
        sampled_menu_key=selected,
        **_selection_result_kwargs(selection_meta),
    )
