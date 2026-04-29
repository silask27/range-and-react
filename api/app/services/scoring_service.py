from __future__ import annotations

from collections import defaultdict
from typing import Any

from api.app.data.catalog import SCENARIOS
from api.app.data.villain_profiles import VILLAIN_PROFILES
from api.app.engine.bucket_engine import build_bucket_matrix_view
from api.app.engine.villain_decision import choose_villain_action
from api.app.engine.villain_hand_bucket import bucket_villain_hand
from api.app.models.enums import ActionType, Player, ResponseColumnType
from api.app.models.state import HandState
from api.app.storage.memory_store import store


def _sorted_combo(combo: tuple[str, str] | list[str]) -> list[str]:
    return sorted(list(combo))


def _metadata_for_hand(hand_id: str) -> dict[str, Any]:
    record = store.get_hand_result(hand_id)
    metadata = dict((record or {}).get('metadata') or {})
    metadata.setdefault('score_version', 2)
    metadata.setdefault('prune_evaluations', [])
    metadata.setdefault('response_evaluations', [])
    metadata.setdefault('summary', {})
    return metadata


def _persist_metadata(hand_id: str, metadata: dict[str, Any]) -> None:
    prune_scores = [float(item['overall_score']) for item in metadata.get('prune_evaluations', []) if item.get('overall_score') is not None]
    response_scores = [float(item['score']) for item in metadata.get('response_evaluations', []) if item.get('supported') and item.get('score') is not None]
    ranging_score = round(sum(prune_scores) / len(prune_scores), 2) if prune_scores else None
    response_score = round(sum(response_scores) / len(response_scores), 2) if response_scores else None
    overall_parts = [v for v in [ranging_score, response_score] if v is not None]
    overall_score = round(sum(overall_parts) / len(overall_parts), 2) if overall_parts else None
    metadata['summary'] = {
        'prune_steps_scored': len(prune_scores),
        'response_nodes_scored': len(response_scores),
        'ranging_score': ranging_score,
        'response_score': response_score,
        'overall_score': overall_score,
    }
    store.update_hand_result_scores(
        hand_id,
        ranging_score=ranging_score,
        response_score=response_score,
        overall_score=overall_score,
        metadata=metadata,
    )


def _actual_bucket_info(hand: HandState, *, iters: int | None) -> dict[str, Any]:
    result = bucket_villain_hand(
        villain_hand=hand.villain_hand,
        board=hand.board,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        iters=iters,
        seed=int(hand.bucket_seed),
    )
    return {
        'bucket_label': result.bucket_label,
        'subgroup_label': result.subgroup_label,
        'equity_vs_hero': result.equity_vs_hero,
        'hero_range_source': result.hero_range_source,
    }


def _bucket_view(hand: HandState, *, iters: int | None) -> dict[str, Any]:
    return build_bucket_matrix_view(
        villain_range_combos_live=hand.villain_range_combos_live,
        board=hand.board,
        hero_hand=hand.hero_hand,
        villain_profile_id=hand.villain_profile_id,
        scenario_hero_range_tokens=hand.hero_tokens_saved,
        iters=iters,
        seed=int(hand.bucket_seed),
    )


def _combo_alive(hand: HandState) -> tuple[bool, list[str]]:
    target = _sorted_combo(hand.villain_hand)
    labels = []
    for label, combos in (hand.villain_range_combos_live or {}).items():
        if any(_sorted_combo(combo) == target for combo in combos):
            labels.append(label)
    return bool(labels), labels


def _row_flags(bucket_view: dict[str, Any], *, actual_bucket: str, actual_subgroup: str) -> tuple[bool, bool]:
    bucket_alive = False
    subgroup_alive = False
    for row in bucket_view.get('rows', []):
        if row.get('bucket_name') != actual_bucket:
            continue
        bucket_alive = True
        subgroup_alive = any(
            subgroup.get('subgroup_name') == actual_subgroup and int(subgroup.get('combo_count', 0)) > 0
            for subgroup in row.get('subgroups', [])
        )
        break
    return bucket_alive, subgroup_alive



def _latest_villain_event(hand: HandState):
    return next(
        (
            event
            for event in reversed(hand.history.events)
            if event.actor == Player.VILLAIN or getattr(event.actor, "value", None) == "villain"
        ),
        None,
    )


def _previous_hero_event_before_latest_villain(hand: HandState):
    latest = _latest_villain_event(hand)
    if latest is None:
        return None
    seen_latest = False
    for event in reversed(hand.history.events):
        if event is latest:
            seen_latest = True
            continue
        if not seen_latest:
            continue
        if event.actor == Player.HERO or getattr(event.actor, "value", None) == "hero":
            return event
    return None


def _action_model_key(action: ActionType | None) -> str | None:
    if action == ActionType.CHECK:
        return "x"
    if action == ActionType.BET:
        return "b"
    if action == ActionType.FOLD:
        return "f"
    if action == ActionType.CALL:
        return "c"
    if action == ActionType.RAISE:
        return "r"
    return None


def _response_probs_from_model_probs(column: str, model_probs: dict[str, float]) -> dict[str, float]:
    if column == ResponseColumnType.CHECK.value:
        return {"X": float(model_probs.get("x", 0.0)), "B": float(model_probs.get("b", 0.0))}
    if column in {ResponseColumnType.BET_SMALL.value, ResponseColumnType.BET_BIG.value, ResponseColumnType.RAISE.value}:
        return {"F": float(model_probs.get("f", 0.0)), "C": float(model_probs.get("c", 0.0)), "R": float(model_probs.get("r", 0.0))}
    return {}


def _stable_combo_seed(hand: HandState, combo: list[str] | tuple[str, str], offset: int = 0) -> int:
    combo_text = "".join(sorted(str(card) for card in combo))
    return int(hand.bucket_seed) + offset + sum(ord(ch) for ch in combo_text)


def _decision_context_for_response_score(hand: HandState, *, hero_action_type: ActionType, hero_amount: float | None, pot_before_action: float | None) -> dict[str, Any]:
    amount = float(hero_amount or 0.0)
    base_pot = float(pot_before_action if pot_before_action is not None else hand.pot)
    if hero_action_type in {ActionType.BET, ActionType.RAISE}:
        return {"pot": max(1.0, base_pot + amount), "to_call": max(0.0, amount), "node_hint": "facing_raise" if hero_action_type == ActionType.RAISE else "facing_bet"}
    return {"pot": max(1.0, base_pot), "to_call": 0.0, "node_hint": "open_action"}


def _decision_context_for_observed_villain_event(hand: HandState) -> tuple[dict[str, Any], ActionType | None]:
    latest = _latest_villain_event(hand)
    if latest is None:
        return {"pot": max(1.0, float(hand.pot)), "to_call": 0.0, "node_hint": "open_action"}, None
    action = latest.action
    amount = float(latest.amount or 0.0)
    prev_hero = _previous_hero_event_before_latest_villain(hand)
    if action in {ActionType.CHECK, ActionType.BET}:
        return {"pot": max(1.0, float(hand.pot) - (amount if action == ActionType.BET else 0.0)), "to_call": 0.0, "node_hint": "open_action"}, action
    node_hint = "facing_raise" if prev_hero is not None and prev_hero.action == ActionType.RAISE else "facing_bet"
    to_call = amount if action == ActionType.CALL else float(getattr(prev_hero, "amount", 0.0) or amount or 0.0)
    return {"pot": max(1.0, float(hand.pot) - amount), "to_call": max(0.0, to_call), "node_hint": node_hint}, action


def _model_probabilities_for_combo(hand: HandState, *, combo: list[str] | tuple[str, str], context: dict[str, Any], iters: int | None, seed_offset: int) -> dict[str, float] | None:
    scenario = SCENARIOS.get(hand.scenario_id)
    try:
        decision = choose_villain_action(
            villain_hand=tuple(combo),
            board=hand.board,
            villain_profile_id=hand.villain_profile_id,
            street=hand.street,
            to_call=float(context.get("to_call") or 0.0),
            pot=float(context.get("pot") or hand.pot or 1.0),
            can_raise=True,
            scenario_hero_range_tokens=hand.hero_tokens_saved,
            iters=iters,
            seed=_stable_combo_seed(hand, combo, offset=seed_offset),
            node_hint=str(context.get("node_hint") or "open_action"),
            scenario_id=hand.scenario_id,
            villain_is_ip=(not bool(getattr(scenario, "hero_is_ip", False))) if scenario else False,
            history_events=hand.history.events,
            effective_stack_size=float(hand.villain_stack or 0.0),
        )
    except Exception:
        return None
    return dict(decision.probabilities or {})


def _bucket_level_response_scores(hand: HandState, *, column: str, selections: dict[str, dict[str, str]], hero_action_type: ActionType, hero_amount: float | None, pot_before_action: float | None, iters: int | None) -> tuple[float | None, list[dict[str, Any]]]:
    context = _decision_context_for_response_score(hand, hero_action_type=hero_action_type, hero_amount=hero_amount, pot_before_action=pot_before_action)
    bucket_view = _bucket_view(hand, iters=iters)
    bucket_rows: list[dict[str, Any]] = []
    weighted_total = 0.0
    total_weight = 0.0
    for row in bucket_view.get("rows", []):
        bucket_name = str(row.get("bucket_name"))
        combo_count = int(row.get("combo_count", 0) or 0)
        if combo_count <= 0:
            continue
        accum: dict[str, float] = defaultdict(float)
        seen = 0
        for hand_entry in row.get("hands", []):
            for combo in hand_entry.get("combo_cards", []):
                probs = _model_probabilities_for_combo(hand, combo=combo, context=context, iters=iters, seed_offset=3100)
                if probs is None:
                    continue
                response_probs = _response_probs_from_model_probs(column, probs)
                if not response_probs:
                    continue
                for key, value in response_probs.items():
                    accum[key] += float(value)
                seen += 1
        if seen <= 0:
            continue
        averaged = {key: value / seen for key, value in accum.items()}
        max_prob = max(averaged.values()) if averaged else 0.0
        predicted = (selections.get(bucket_name) or {}).get(column)
        selected_prob = float(averaged.get(predicted, 0.0)) if predicted else 0.0
        bucket_score = (selected_prob / max_prob * 100.0) if max_prob > 0 else None
        if bucket_score is not None:
            weighted_total += bucket_score * combo_count
            total_weight += combo_count
        bucket_rows.append({
            "bucket": bucket_name,
            "predicted": predicted,
            "probabilities": {k: round(v, 4) for k, v in averaged.items()},
            "selected_probability": round(selected_prob, 4),
            "best_probability": round(max_prob, 4),
            "score": round(bucket_score, 2) if bucket_score is not None else None,
            "combo_count": combo_count,
        })
    if total_weight <= 0:
        return None, bucket_rows
    return round(weighted_total / total_weight, 2), bucket_rows


def _posterior_prune_score(hand: HandState, *, iters: int | None) -> dict[str, Any] | None:
    context, observed_action = _decision_context_for_observed_villain_event(hand)
    action_key = _action_model_key(observed_action)
    if action_key is None:
        return None
    prior_combos: list[tuple[str, tuple[str, str]]] = []
    for label, combos in (hand.prune_range_snapshot or {}).items():
        for combo in combos:
            prior_combos.append((label, tuple(sorted(combo))))
    if not prior_combos:
        return None
    kept = {tuple(sorted(combo)) for combos in (hand.villain_range_combos_live or {}).values() for combo in combos}
    raw_weights: list[tuple[str, tuple[str, str], float]] = []
    for label, combo in prior_combos:
        probs = _model_probabilities_for_combo(hand, combo=combo, context=context, iters=iters, seed_offset=9100)
        probability = float((probs or {}).get(action_key, 0.0))
        raw_weights.append((label, combo, max(0.0, probability)))
    total_raw = sum(weight for _, _, weight in raw_weights)
    if total_raw <= 0:
        return None
    posterior = [(label, combo, weight / total_raw) for label, combo, weight in raw_weights]
    posterior_mass_kept = sum(weight for _, combo, weight in posterior if combo in kept)
    uniform = 1.0 / len(posterior)
    low_posterior = [(label, combo, weight) for label, combo, weight in posterior if weight < uniform]
    if low_posterior:
        removed_low = sum(1 for _, combo, _ in low_posterior if combo not in kept)
        junk_removed = removed_low / len(low_posterior)
    else:
        junk_removed = 1.0
    overall = (0.75 * posterior_mass_kept + 0.25 * junk_removed) * 100.0
    return {
        "observed_action_key": action_key,
        "posterior_mass_kept": round(posterior_mass_kept * 100.0, 2),
        "low_posterior_junk_removed": round(junk_removed * 100.0, 2),
        "overall_score": round(overall, 2),
        "prior_combo_count": len(prior_combos),
        "kept_combo_count": len(kept),
    }

def record_prune_evaluation(hand: HandState, *, iters: int | None) -> None:
    if not hand.prune_range_snapshot:
        return
    start_total = sum(len(combos) for combos in hand.prune_range_snapshot.values())
    end_total = sum(len(combos) for combos in (hand.villain_range_combos_live or {}).values())
    actual = _actual_bucket_info(hand, iters=iters)
    combo_alive, live_labels = _combo_alive(hand)
    bucket_alive, subgroup_alive = _row_flags(
        _bucket_view(hand, iters=iters),
        actual_bucket=actual['bucket_label'],
        actual_subgroup=actual['subgroup_label'],
    )

    posterior_result = _posterior_prune_score(hand, iters=iters)
    if posterior_result is not None:
        overall = float(posterior_result['overall_score'])
        efficiency = None
    else:
        efficiency = 0.0
        if combo_alive and start_total > 1:
            efficiency = max(0.0, min(1.0, (start_total - end_total) / (start_total - 1)))
        if combo_alive:
            overall = 70.0 + (30.0 * efficiency)
        elif subgroup_alive:
            overall = 35.0
        elif bucket_alive:
            overall = 20.0
        else:
            overall = 0.0

    latest_villain_event = _latest_villain_event(hand)
    metadata = _metadata_for_hand(hand.hand_id)
    metadata['prune_evaluations'].append({
        'street': hand.street.value,
        'villain_action': latest_villain_event.action.value if latest_villain_event else None,
        'actual_bucket': actual['bucket_label'],
        'actual_subgroup': actual['subgroup_label'],
        'start_live_combos': start_total,
        'end_live_combos': end_total,
        'combo_alive': combo_alive,
        'bucket_alive': bucket_alive,
        'subgroup_alive': subgroup_alive,
        'remaining_labels_for_true_combo': live_labels,
        'posterior_scoring': posterior_result,
        'efficiency_score': round(efficiency * 100.0, 2) if efficiency is not None else None,
        'overall_score': round(overall, 2),
    })
    _persist_metadata(hand.hand_id, metadata)

def _hero_column_for_action(*, action_type: ActionType, amount: float | None, pot_before_action: float | None) -> str | None:
    if action_type == ActionType.CHECK:
        return ResponseColumnType.CHECK.value
    if action_type == ActionType.RAISE:
        return ResponseColumnType.RAISE.value
    if action_type == ActionType.CALL:
        return ResponseColumnType.CALL.value
    if action_type == ActionType.BET:
        if amount is None or not pot_before_action or pot_before_action <= 0:
            return ResponseColumnType.BET_SMALL.value
        frac = float(amount) / float(pot_before_action)
        return ResponseColumnType.BET_SMALL.value if frac <= 0.66 else ResponseColumnType.BET_BIG.value
    return None


def _actual_response_code(column: str, villain_action: ActionType) -> str | None:
    if column == ResponseColumnType.CHECK.value:
        return 'X' if villain_action == ActionType.CHECK else 'B' if villain_action == ActionType.BET else None
    if column in {ResponseColumnType.BET_SMALL.value, ResponseColumnType.BET_BIG.value, ResponseColumnType.RAISE.value}:
        return {ActionType.FOLD: 'F', ActionType.CALL: 'C', ActionType.RAISE: 'R'}.get(villain_action)
    return None


def record_response_matrix_evaluation(
    hand: HandState,
    *,
    hero_action_type: ActionType,
    hero_amount: float | None,
    pot_before_action: float | None,
    villain_action_type: ActionType | None,
    iters: int | None,
) -> None:
    saved = hand.response_matrix_saved or {}
    selections = saved.get('selections') if isinstance(saved, dict) else None
    if not isinstance(selections, dict) or not selections:
        return
    actual = _actual_bucket_info(hand, iters=iters)
    column = _hero_column_for_action(action_type=hero_action_type, amount=hero_amount, pot_before_action=pot_before_action)
    supported = True
    reason = None
    actual_code = None
    score = None
    correct = None
    bucket_scores: list[dict[str, Any]] = []
    if column == ResponseColumnType.CALL.value:
        supported = False
        reason = 'Call-column nodes are not directly scored yet because they predict later posture rather than an immediate villain action.'
    elif column is None or villain_action_type is None:
        supported = False
        reason = 'No scoreable immediate villain response was available for this node.'
    else:
        actual_code = _actual_response_code(column, villain_action_type)
        if actual_code is None:
            supported = False
            reason = 'The villain action did not map cleanly to this response column.'
        else:
            score, bucket_scores = _bucket_level_response_scores(
                hand,
                column=column,
                selections=selections,
                hero_action_type=hero_action_type,
                hero_amount=hero_amount,
                pot_before_action=pot_before_action,
                iters=iters,
            )
            if score is None:
                supported = False
                reason = 'Could not compute bucket-level model probabilities for this node.'
            else:
                predicted_actual_bucket = (selections.get(actual['bucket_label']) or {}).get(column)
                correct = predicted_actual_bucket == actual_code
    metadata = _metadata_for_hand(hand.hand_id)
    metadata['response_evaluations'].append({
        'street': hand.street.value,
        'actual_bucket': actual['bucket_label'],
        'actual_subgroup': actual['subgroup_label'],
        'hero_action': hero_action_type.value,
        'hero_amount': hero_amount,
        'column': column,
        'predicted': (selections.get(actual['bucket_label']) or {}).get(column) if column else None,
        'actual': actual_code,
        'villain_action': villain_action_type.value if villain_action_type else None,
        'supported': supported,
        'score': score,
        'correct': correct,
        'bucket_level_scores': bucket_scores,
        'score_method': 'bucket_probability_decision_quality',
        'reason': reason,
    })
    _persist_metadata(hand.hand_id, metadata)

def build_hand_debrief(hand: HandState) -> dict[str, Any]:
    metadata = _metadata_for_hand(hand.hand_id)
    summary = metadata.get('summary') or {}
    prune_evals = metadata.get('prune_evaluations', [])
    response_evals = metadata.get('response_evaluations', [])
    recommendations: list[str] = []
    posterior_scores = [
        float(item["posterior_scoring"]["posterior_mass_kept"])
        for item in prune_evals
        if isinstance(item.get("posterior_scoring"), dict)
        and item["posterior_scoring"].get("posterior_mass_kept") is not None
    ]
    low_junk_scores = [
        float(item["posterior_scoring"]["low_posterior_junk_removed"])
        for item in prune_evals
        if isinstance(item.get("posterior_scoring"), dict)
        and item["posterior_scoring"].get("low_posterior_junk_removed") is not None
    ]
    response_scores = [
        float(item["score"])
        for item in response_evals
        if item.get("supported") and item.get("score") is not None
    ]

    if posterior_scores:
        avg_posterior_kept = sum(posterior_scores) / len(posterior_scores)
        if avg_posterior_kept < 70:
            recommendations.append(
                "Your ranging score was driven by how much model-likely post-action range you kept. Review the prune steps where too much posterior range was removed."
            )
        elif any(not item.get("combo_alive") for item in prune_evals):
            recommendations.append(
                "You removed villain's exact combo in at least one prune step, but the ranging score now rewards how closely your remaining range matched the model's likely post-action range."
            )
    elif any(not item.get("combo_alive") for item in prune_evals):
        recommendations.append(
            "You excluded villain's real combo on at least one prune step. Focus on keeping plausible hands alive before narrowing aggressively."
        )

    if response_scores and (sum(response_scores) / len(response_scores)) < 70:
        recommendations.append(
            "Action Prediction is scored by bucket-level model probabilities. Review buckets where your selected reaction was far from the model's highest-probability response."
        )
    if any(not item.get("supported") for item in response_evals):
        recommendations.append(
            "Some response nodes were not scored because they do not map to an immediate villain reaction yet."
        )
    if not recommendations:
        recommendations.append(
            "Nice work. Your remaining range matched the model-likely post-action range and your bucket reactions were close to the model's highest-probability responses."
        )
    actual = _actual_bucket_info(hand, iters=None)
    return {
        'hand_id': hand.hand_id,
        'session_id': hand.session_id,
        'scenario_id': hand.scenario_id,
        'villain_profile_id': hand.villain_profile_id,
        'street': hand.street.value,
        'hero_hand': list(hand.hero_hand),
        'villain_hand': list(hand.villain_hand),
        'board': list(hand.board),
        'pot': hand.pot,
        'hero_stack': hand.hero_stack,
        'villain_stack': hand.villain_stack,
        'hand_over': hand.hand_over,
        'actual_final_bucket': actual,
        'summary': summary,
        'prune_evaluations': prune_evals,
        'response_evaluations': response_evals,
        'recommendations': recommendations,
        'history': [
            {'street': e.street.value, 'actor': e.actor.value, 'action': e.action.value, 'amount': e.amount, 'note': e.note, 'forced': e.forced}
            for e in hand.history.events
        ],
    }


def _avg(values: list[float | int | None]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _timer_label(seconds: int | None) -> str:
    if seconds in (None, 0):
        return 'Off'
    return f'{int(seconds)}s'


def _result_context(result: dict[str, Any]) -> dict[str, Any]:
    scenario = SCENARIOS.get(result.get('scenario_id'))
    villain = VILLAIN_PROFILES.get(result.get('villain_profile_id'))
    session = store.get_session(result.get('session_id')) if result.get('session_id') else None
    timer_seconds = None
    if session:
        timer_seconds = session.get('train_timer_seconds')
    metadata = dict(result.get('metadata') or {})
    prune_evals = metadata.get('prune_evaluations') or []
    response_evals = metadata.get('response_evaluations') or []

    street_scores_map: dict[str, dict[str, list[float]]] = defaultdict(lambda: {'ranging': [], 'response': []})
    streets_played: set[str] = set()
    for item in prune_evals:
        street = str(item.get('street') or '').lower()
        if not street:
            continue
        streets_played.add(street)
        if item.get('overall_score') is not None:
            street_scores_map[street]['ranging'].append(float(item['overall_score']))
    for item in response_evals:
        street = str(item.get('street') or '').lower()
        if not street:
            continue
        streets_played.add(street)
        if item.get('supported') and item.get('score') is not None:
            street_scores_map[street]['response'].append(float(item['score']))
    if result.get('street'):
        streets_played.add(str(result['street']).lower())

    street_scores = [
        {
            'street': street,
            'ranging_score': _avg(values['ranging']),
            'response_score': _avg(values['response']),
        }
        for street, values in street_scores_map.items()
    ]
    street_scores.sort(key=lambda item: ['flop', 'turn', 'river'].index(item['street']) if item['street'] in {'flop', 'turn', 'river'} else 99)

    return {
        'hand_id': result.get('hand_id'),
        'session_id': result.get('session_id'),
        'scenario_id': result.get('scenario_id'),
        'scenario_display_name': scenario.display_name if scenario else result.get('scenario_id'),
        'villain_profile_id': result.get('villain_profile_id'),
        'villain_display_name': villain.meta.display_name if villain else result.get('villain_profile_id'),
        'street': result.get('street'),
        'position': 'IP' if scenario and scenario.hero_is_ip else 'OOP' if scenario else 'Unknown',
        'timer_seconds': timer_seconds,
        'timer_label': _timer_label(timer_seconds),
        'ranging_score': result.get('ranging_score'),
        'response_score': result.get('response_score'),
        'overall_score': result.get('overall_score'),
        'completed_at': result.get('completed_at'),
        'streets_played': sorted(streets_played, key=lambda s: ['flop', 'turn', 'river'].index(s) if s in {'flop', 'turn', 'river'} else 99),
        'street_scores': street_scores,
    }


def build_results_overview(*, user_id: str) -> dict[str, Any]:
    records = [item for item in store.list_hand_results(user_id=user_id, limit=2000) if item.get('hand_over')]
    completed = [_result_context(item) for item in records]

    scenario_options = sorted({(item['scenario_id'], item['scenario_display_name']) for item in completed if item.get('scenario_id')}, key=lambda pair: pair[1])
    villain_options = sorted({(item['villain_profile_id'], item['villain_display_name']) for item in completed if item.get('villain_profile_id')}, key=lambda pair: pair[1])
    position_options = sorted({item['position'] for item in completed if item.get('position')}, key=lambda value: ['IP', 'OOP', 'Unknown'].index(value) if value in {'IP', 'OOP', 'Unknown'} else 99)
    timer_options = sorted({(item['timer_label'], item['timer_seconds']) for item in completed}, key=lambda pair: (-1 if pair[1] in (None, 0) else int(pair[1]), pair[0]))

    street_group: dict[str, dict[str, list[float]]] = defaultdict(lambda: {'ranging': [], 'response': [], 'events': 0})
    for item in completed:
        for street_row in item['street_scores']:
            street = street_row['street']
            street_group[street]['events'] += 1
            if street_row.get('ranging_score') is not None:
                street_group[street]['ranging'].append(float(street_row['ranging_score']))
            if street_row.get('response_score') is not None:
                street_group[street]['response'].append(float(street_row['response_score']))

    by_street = []
    for street, values in street_group.items():
        by_street.append({
            'key': street,
            'display_name': street.title(),
            'hands': values['events'],
            'ranging_score': _avg(values['ranging']),
            'response_score': _avg(values['response']),
        })
    by_street.sort(key=lambda row: ['flop', 'turn', 'river'].index(row['key']) if row['key'] in {'flop', 'turn', 'river'} else 99)

    return {
        'summary': {
            'completed_hands': len(completed),
            'ranging_score': _avg([item.get('ranging_score') for item in completed]),
            'response_score': _avg([item.get('response_score') for item in completed]),
            'overall_score': _avg([item.get('overall_score') for item in completed]),
        },
        'filter_options': {
            'scenarios': [{'id': sid, 'display_name': label} for sid, label in scenario_options],
            'villains': [{'id': vid, 'display_name': label} for vid, label in villain_options],
            'positions': [{'id': pos, 'display_name': pos} for pos in position_options],
            'timers': [{'id': label, 'display_name': label} for label, _ in timer_options],
            'streets': [{'id': row['key'], 'display_name': row['display_name']} for row in by_street],
        },
        'by_street': by_street,
        'completed_results': sorted(completed, key=lambda item: item.get('completed_at') or '', reverse=True),
        'recent_results': sorted(completed, key=lambda item: item.get('completed_at') or '', reverse=True)[:20],
    }
