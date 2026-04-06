# File: api/app/engine/villain_decision.py
# Summary: Predictive villain action engine backed by the trained models from
# villain-calibration-lab.
#
# Design goals:
# - preserve the main app's service-layer contract as much as possible
# - replace the old hand-bucket/policy action engine completely
# - make future model refreshes simple: replace the model artifacts in
#   api/app/model_artifacts/villain_models/
# - fail loudly if the feature version expected by inference does not match the
#   feature versions recorded in the artifacts

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import pickle
import random
from typing import Iterable, Sequence

from api.app.data.villain_profiles import get_villain_profile
from api.app.engine import bucketizer as bz
from api.app.engine.board_texture import evaluate_board_texture
from api.app.engine.cards import normalize_cards
from api.app.models.betting import ActionEvent
from api.app.models.enums import ActionType, Street

FEATURE_VERSION = "v2"

MODEL_DIR = Path(__file__).resolve().parents[1] / "model_artifacts" / "villain_models"
TRAINING_SUMMARY_PATH = MODEL_DIR / "training_summary.json"

OPEN_ACTION_MODEL_FILE = MODEL_DIR / "open_action_model.pkl"
FACING_BET_FOLD_CONTINUE_MODEL_FILE = MODEL_DIR / "facing_bet_fold_continue_model.pkl"
FACING_BET_CALL_RAISE_MODEL_FILE = MODEL_DIR / "facing_bet_call_raise_model.pkl"
FACING_RAISE_FOLD_CONTINUE_MODEL_FILE = MODEL_DIR / "facing_raise_fold_continue_model.pkl"
FACING_RAISE_CALL_RERAISE_MODEL_FILE = MODEL_DIR / "facing_raise_call_reraise_model.pkl"

OPEN_BET_SIZE_MODEL_FILE = MODEL_DIR / "open_bet_size_model.pkl"
RAISE_VS_BET_SIZE_MODEL_FILE = MODEL_DIR / "raise_vs_bet_size_model.pkl"


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
class DerivedPredictors:
    feature_version: str
    villain_type: str
    scenario_id: str
    street: str
    node: str
    open_action_type: str | None
    villain_is_ip: bool
    pot_size: float
    effective_stack_size: float
    spr: float
    facing_size_raw: float
    facing_size_pct_pot: float
    hand_equity: float
    hand_subgroup: str
    previous_action_summary: str
    board_state: BoardStateFlags
    vulnerability_score: float


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


@lru_cache(maxsize=1)
def _fixed_hero_combos() -> tuple[tuple[str, str], ...]:
    return tuple(bz.expand_range_to_combos(list(bz.HERO_RANGE_TOKENS)))


@lru_cache(maxsize=1)
def _load_runtime_modules():
    try:
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Predictive villain models require numpy and pandas in the main app "
            "environment. Install them before running villain-range-trainer-working."
        ) from exc
    return np, pd


@lru_cache(maxsize=1)
def _load_training_summary() -> dict | None:
    if not TRAINING_SUMMARY_PATH.exists():
        return None
    return json.loads(TRAINING_SUMMARY_PATH.read_text())


@lru_cache(maxsize=None)
def _load_artifact(path_str: str) -> dict:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Missing predictive villain model artifact: {path}")

    try:
        with path.open("rb") as f:
            artifact = pickle.load(f)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Failed to load predictive villain model artifacts. The main app "
            "environment is likely missing CatBoost or a compatible dependency."
        ) from exc

    feature_versions = set((artifact.get("feature_versions") or {}).keys())
    if feature_versions and feature_versions != {FEATURE_VERSION}:
        raise RuntimeError(
            f"Artifact {path.name} is incompatible with runtime feature version "
            f"{FEATURE_VERSION}. Artifact versions: {sorted(feature_versions)}"
        )

    return artifact


@lru_cache(maxsize=1)
def _validate_model_manifest() -> None:
    summary = _load_training_summary()
    if summary is not None:
        versions = set((summary.get("feature_version_counts") or {}).keys())
        if versions and versions != {FEATURE_VERSION}:
            raise RuntimeError(
                "Predictive villain model manifest does not match runtime feature "
                f"version {FEATURE_VERSION}. Manifest versions: {sorted(versions)}"
            )

    for path in [
        OPEN_ACTION_MODEL_FILE,
        FACING_BET_FOLD_CONTINUE_MODEL_FILE,
        FACING_BET_CALL_RAISE_MODEL_FILE,
        FACING_RAISE_FOLD_CONTINUE_MODEL_FILE,
        FACING_RAISE_CALL_RERAISE_MODEL_FILE,
        OPEN_BET_SIZE_MODEL_FILE,
        RAISE_VS_BET_SIZE_MODEL_FILE,
    ]:
        _load_artifact(str(path))




def validate_model_runtime() -> None:
    _validate_model_manifest()
    _load_runtime_modules()


def _build_one_row_frame(flat_predictors: dict[str, object], artifact: dict):
    _, pd = _load_runtime_modules()
    feature_columns = list(artifact["feature_columns"])
    categorical_columns = set(artifact.get("categorical_feature_columns", []))

    row: dict[str, object] = {}
    for col in feature_columns:
        value = flat_predictors.get(col)
        if isinstance(value, bool):
            value = int(value)
        if col in categorical_columns:
            row[col] = "NA" if value is None else str(value)
        else:
            row[col] = value

    return pd.DataFrame([row], columns=feature_columns)


def _safe_prob_for_label(classes: list[str], probs, label: str) -> float:
    if label not in classes:
        return 0.0
    idx = classes.index(label)
    return float(probs[idx])


def _predict_binary_probs(flat_predictors: dict[str, object], artifact: dict) -> dict[str, float]:
    np, _ = _load_runtime_modules()
    frame = _build_one_row_frame(flat_predictors, artifact)
    model = artifact["model"]
    probs = np.asarray(model.predict_proba(frame), dtype=float).reshape(-1)
    classes = list(artifact["classes"])
    return {label: _safe_prob_for_label(classes, probs, label) for label in classes}


def _predict_regression_value(flat_predictors: dict[str, object], artifact: dict) -> float:
    np, _ = _load_runtime_modules()
    frame = _build_one_row_frame(flat_predictors, artifact)
    model = artifact["model"]
    pred = np.asarray(model.predict(frame), dtype=float).reshape(-1)[0]
    return float(pred)


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


def _clip_open_bet_pct_pot(value: float) -> float:
    return max(0.25, min(float(value), 2.00))


def _clip_raise_multiple(value: float) -> float:
    return max(2.00, min(float(value), 7.00))


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


def _is_made_hand_subgroup(subgroup: str) -> bool:
    return subgroup in {
        "Overpair",
        "Top Pair",
        "Mid Pair",
        "Low Pair",
        "Two Pair",
        "Trips",
        "Set",
        "Straight",
        "Flush",
        "Full House",
        "Quads",
        "Straight Flush",
    }


def _compute_vulnerability_score(
    *,
    street: str,
    villain_is_ip: bool,
    hand_equity: float,
    hand_subgroup: str,
    board_state: BoardStateFlags,
) -> float:
    if street == "river":
        return 0.0
    if not _is_made_hand_subgroup(hand_subgroup):
        return 0.0
    texture_pressure = (0.65 * float(board_state.connected)) + (0.35 * float(board_state.two_tone))
    if texture_pressure <= 0.0:
        return 0.0
    position_multiplier = 1.00 if villain_is_ip else 1.10
    return float(round(max(0.0, hand_equity * texture_pressure * position_multiplier), 6))


def _street_order_value(street: str) -> int:
    return {"flop": 1, "turn": 2, "river": 3}[street]


def _previous_action_summary(street: str, history_events: Iterable[ActionEvent] | None) -> str:
    if street == "flop" or not history_events:
        return "NA"

    current_street_value = _street_order_value(street)
    previous_street = None
    for name, value in {"flop": 1, "turn": 2, "river": 3}.items():
        if value == current_street_value - 1:
            previous_street = name
            break
    if previous_street is None:
        return "NA"

    previous_events: list[ActionEvent] = []
    for event in history_events:
        if getattr(event, "forced", False):
            continue
        event_street = event.street.value if hasattr(event.street, "value") else str(event.street)
        if event_street == previous_street:
            previous_events.append(event)

    if not previous_events:
        return "NA"

    return ">".join(
        f"{event.actor.value if hasattr(event.actor, 'value') else str(event.actor)}_"
        f"{event.action.value if hasattr(event.action, 'value') else str(event.action)}"
        for event in previous_events
    )


def _stable_equity_seed(
    *,
    villain_type: str,
    scenario_id: str,
    street: str,
    board: Sequence[str],
    villain_hand: Sequence[str],
) -> int:
    raw = "|".join(
        [
            villain_type,
            scenario_id,
            street,
            "".join(board),
            "".join(villain_hand),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _compute_hand_equity_and_subgroup(
    *,
    villain_type: str,
    scenario_id: str,
    street: str,
    villain_hand: Sequence[str],
    board: Sequence[str],
) -> tuple[float, str]:
    normalized_board = normalize_cards(list(board))
    normalized_hole = normalize_cards(list(villain_hand))
    hole = tuple(sorted((normalized_hole[0], normalized_hole[1])))

    subgroup = bz.subgroup_of(hole, normalized_board)
    hero_combos = list(_fixed_hero_combos())

    if len(normalized_board) == 5:
        equity = bz.equity_vs_hero_range_river_exact(hole, normalized_board, hero_combos)
    else:
        iters = bz.resolve_iters(normalized_board, None)
        rng = random.Random(
            _stable_equity_seed(
                villain_type=villain_type,
                scenario_id=scenario_id,
                street=street,
                board=normalized_board,
                villain_hand=normalized_hole,
            )
        )
        equity = bz.equity_vs_hero_range_mc(
            villain_hole=hole,
            board=normalized_board,
            hero_combos=hero_combos,
            iters=iters,
            rng=rng,
        )

    return float(equity), subgroup


def _normalize_node(node_hint: str | None, to_call: float) -> str:
    if node_hint == "unopened":
        return "open_action"
    if node_hint == "facing_raise":
        return "facing_raise"
    if to_call > 0:
        return "facing_bet"
    return "open_action"


def _derive_predictors(
    *,
    villain_type: str,
    scenario_id: str,
    street: str,
    villain_is_ip: bool,
    node: str,
    pot: float,
    effective_stack_size: float,
    facing_size_raw: float,
    villain_hand: Sequence[str],
    board: Sequence[str],
    history_events: Iterable[ActionEvent] | None,
) -> DerivedPredictors:
    open_action_type = None
    if node == "open_action":
        open_action_type = "checked_to" if villain_is_ip else "first_to_act"

    hand_equity, hand_subgroup = _compute_hand_equity_and_subgroup(
        villain_type=villain_type,
        scenario_id=scenario_id,
        street=street,
        villain_hand=villain_hand,
        board=board,
    )
    board_state = _derive_board_state_flags(board)
    spr = float(effective_stack_size / pot) if pot > 0 else 0.0
    facing_size_pct_pot = float(facing_size_raw / pot) if pot > 0 else 0.0
    vulnerability_score = _compute_vulnerability_score(
        street=street,
        villain_is_ip=villain_is_ip,
        hand_equity=hand_equity,
        hand_subgroup=hand_subgroup,
        board_state=board_state,
    )

    return DerivedPredictors(
        feature_version=FEATURE_VERSION,
        villain_type=villain_type,
        scenario_id=scenario_id,
        street=street,
        node=node,
        open_action_type=open_action_type,
        villain_is_ip=villain_is_ip,
        pot_size=float(pot),
        effective_stack_size=float(effective_stack_size),
        spr=float(spr),
        facing_size_raw=float(facing_size_raw),
        facing_size_pct_pot=float(facing_size_pct_pot),
        hand_equity=float(hand_equity),
        hand_subgroup=hand_subgroup,
        previous_action_summary=_previous_action_summary(street, history_events),
        board_state=board_state,
        vulnerability_score=float(vulnerability_score),
    )


def _flatten_predictors_for_model(predictors: DerivedPredictors) -> dict[str, object]:
    return {
        "feature_version": predictors.feature_version,
        "villain_type": predictors.villain_type,
        "scenario_id": predictors.scenario_id,
        "street": predictors.street,
        "node": predictors.node,
        "open_action_type": predictors.open_action_type,
        "villain_is_ip": predictors.villain_is_ip,
        "pot_size": predictors.pot_size,
        "effective_stack_size": predictors.effective_stack_size,
        "spr": predictors.spr,
        "facing_size_raw": predictors.facing_size_raw,
        "facing_size_pct_pot": predictors.facing_size_pct_pot,
        "hand_equity": predictors.hand_equity,
        "hand_subgroup": predictors.hand_subgroup,
        "previous_action_summary": predictors.previous_action_summary,
        "board_paired": predictors.board_state.paired,
        "board_rainbow": predictors.board_state.rainbow,
        "board_monotone": predictors.board_state.monotone,
        "board_two_tone": predictors.board_state.two_tone,
        "board_flush_completed": predictors.board_state.flush_completed,
        "board_straight_completed": predictors.board_state.straight_completed,
        "board_connected": predictors.board_state.connected,
        "vulnerability_score": predictors.vulnerability_score,
    }


def _format_probs_for_note(probs: dict[str, float]) -> str:
    pieces = [f"{label}={prob:.2f}" for label, prob in sorted(probs.items())]
    return ", ".join(pieces)




def _fallback_villain_decision(
    *,
    node: str,
    can_raise: bool,
    facing_size_raw: float,
    pot: float,
    rng: random.Random,
) -> VillainDecisionResult:
    pot = max(float(pot), 1.0)
    frac = max(0.0, float(facing_size_raw) / pot)
    if node == "open_action":
        probs = {"x": 0.38, "b": 0.62}
        sampled = _sample_action_from_probs(probs, rng)
        action = ActionType.BET if sampled == "b" else ActionType.CHECK
        bet_size_frac = 0.5 if action == ActionType.BET else None
        bet_size_key = _bet_size_key_from_fraction(bet_size_frac) if bet_size_frac is not None else None
        return VillainDecisionResult(action=action, node=node, note=f"fallback={node} [{_format_probs_for_note(probs)}]", probabilities=probs, bet_size_key=bet_size_key, bet_size_frac=bet_size_frac, sampled_menu_key=sampled)

    if can_raise:
        if frac <= 0.45:
            probs = {"f": 0.18, "c": 0.58, "r": 0.24}
        elif frac <= 1.0:
            probs = {"f": 0.28, "c": 0.56, "r": 0.16}
        else:
            probs = {"f": 0.42, "c": 0.48, "r": 0.10}
    else:
        probs = {"f": 0.34 if frac > 0.9 else 0.24, "c": 0.66 if frac > 0.9 else 0.76, "r": 0.0}

    sampled = _sample_action_from_probs(probs, rng)
    if sampled == "f":
        action = ActionType.FOLD
    elif sampled == "r":
        action = ActionType.RAISE
    else:
        action = ActionType.CALL

    raise_size_mult = None
    raise_size_key = None
    if action == ActionType.RAISE:
        raise_size_mult = 3.0
        raise_size_key = _raise_size_key_from_multiple(raise_size_mult)

    return VillainDecisionResult(action=action, node=node, note=f"fallback={node} [{_format_probs_for_note(probs)}]", probabilities=probs, raise_size_key=raise_size_key, raise_size_mult=raise_size_mult, sampled_menu_key=sampled)

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
    del scenario_hero_range_tokens
    del iters
    del villain_is_current_aggressor
    del villain_is_pfa
    del prior_villain_aggressive_actions
    del prior_hero_aggressive_actions

    manifest_error: Exception | None = None
    try:
        _validate_model_manifest()
    except Exception as exc:  # pragma: no cover - runtime fallback path
        manifest_error = exc

    profile = get_villain_profile(villain_profile_id)

    villain_type = getattr(getattr(profile, "meta", None), "display_name", None)
    if not villain_type:
        raise ValueError(
            f"Could not resolve display_name for villain profile: {villain_profile_id}"
        )

    allowed_villain_types = {"Dave", "Mike", "Blake", "Tom", "Steve", "Erik", "Alex"}
    if villain_type not in allowed_villain_types:
        raise ValueError(
            f"Resolved unsupported model villain name '{villain_type}' "
            f"for villain profile: {villain_profile_id}"
        )

    street_key = street.value if hasattr(street, "value") else str(street)
    resolved_scenario_id = scenario_id or "unknown_scenario"
    if villain_is_ip is None:
        villain_is_ip = False

    node = _normalize_node(node_hint, float(to_call))
    facing_size_raw = float(to_call) if to_call > 0 else 0.0
    effective_stack = float(effective_stack_size if effective_stack_size is not None else pot)

    predictors = _derive_predictors(
        villain_type=villain_type,
        scenario_id=resolved_scenario_id,
        street=street_key,
        villain_is_ip=bool(villain_is_ip),
        node=node,
        pot=float(pot),
        effective_stack_size=effective_stack,
        facing_size_raw=facing_size_raw,
        villain_hand=list(villain_hand),
        board=list(board),
        history_events=history_events,
    )
    flat_predictors = _flatten_predictors_for_model(predictors)

    rng = _make_rng(
        seed,
        villain_profile_id,
        resolved_scenario_id,
        street_key,
        node,
        ",".join(sorted(villain_hand)),
        ",".join(sorted(board)),
        f"to_call={float(to_call):.4f}",
        f"pot={float(pot):.4f}",
    )

    if manifest_error is not None:
        return _fallback_villain_decision(
            node=node,
            can_raise=can_raise,
            facing_size_raw=facing_size_raw,
            pot=float(pot),
            rng=rng,
        )

    if node == "open_action":
        action_probs = _predict_binary_probs(flat_predictors, _load_artifact(str(OPEN_ACTION_MODEL_FILE)))
        sampled = _sample_action_from_probs(action_probs, rng)
        action = ActionType.BET if sampled == "b" else ActionType.CHECK
        bet_size_frac = None
        bet_size_key = None
        if action == ActionType.BET:
            raw_fraction = _predict_regression_value(
                flat_predictors,
                _load_artifact(str(OPEN_BET_SIZE_MODEL_FILE)),
            )
            bet_size_frac = _clip_open_bet_pct_pot(raw_fraction)
            bet_size_key = _bet_size_key_from_fraction(bet_size_frac)
        return VillainDecisionResult(
            action=action,
            node=node,
            note=f"model={node} [{_format_probs_for_note(action_probs)}]",
            probabilities=action_probs,
            bet_size_key=bet_size_key,
            bet_size_frac=bet_size_frac,
            sampled_menu_key=sampled,
        )

    if node == "facing_bet":
        stage1 = _predict_binary_probs(flat_predictors, _load_artifact(str(FACING_BET_FOLD_CONTINUE_MODEL_FILE)))
        p_fold = float(stage1.get("f", 0.0))
        p_continue = float(stage1.get("continue", 0.0))
        if can_raise:
            stage2 = _predict_binary_probs(flat_predictors, _load_artifact(str(FACING_BET_CALL_RAISE_MODEL_FILE)))
            p_call = p_continue * float(stage2.get("c", 0.0))
            p_raise = p_continue * float(stage2.get("r", 0.0))
        else:
            p_call = p_continue
            p_raise = 0.0
        final_probs = {"f": p_fold, "c": p_call, "r": p_raise}
    else:
        stage1 = _predict_binary_probs(flat_predictors, _load_artifact(str(FACING_RAISE_FOLD_CONTINUE_MODEL_FILE)))
        p_fold = float(stage1.get("f", 0.0))
        p_continue = float(stage1.get("continue", 0.0))
        if can_raise:
            stage2 = _predict_binary_probs(flat_predictors, _load_artifact(str(FACING_RAISE_CALL_RERAISE_MODEL_FILE)))
            p_call = p_continue * float(stage2.get("c", 0.0))
            p_raise = p_continue * float(stage2.get("r", 0.0))
        else:
            p_call = p_continue
            p_raise = 0.0
        final_probs = {"f": p_fold, "c": p_call, "r": p_raise}

    sampled = _sample_action_from_probs(final_probs, rng)
    if sampled == "f":
        action = ActionType.FOLD
    elif sampled == "r":
        action = ActionType.RAISE
    else:
        action = ActionType.CALL

    raise_size_mult = None
    raise_size_key = None
    if action == ActionType.RAISE:
        raw_mult = _predict_regression_value(
            flat_predictors,
            _load_artifact(str(RAISE_VS_BET_SIZE_MODEL_FILE)),
        )
        raise_size_mult = _clip_raise_multiple(raw_mult)
        raise_size_key = _raise_size_key_from_multiple(raise_size_mult)

    return VillainDecisionResult(
        action=action,
        node=node,
        note=f"model={node} [{_format_probs_for_note(final_probs)}]",
        probabilities=final_probs,
        raise_size_key=raise_size_key,
        raise_size_mult=raise_size_mult,
        sampled_menu_key=sampled,
    )
