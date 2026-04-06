# File: api/app/routes/scenarios.py
# Summary: API routes for listing scenarios and retrieving a single scenario by id.

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.app.data.catalog import SCENARIOS, list_scenarios
from api.app.models.scenario import Scenario

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _serialize_scenario(scenario: Scenario) -> dict:
    return {
        "id": scenario.id,
        "display_name": scenario.display_name,
        "description": scenario.description,
        "hero_position": scenario.hero_position.value,
        "villain_position": scenario.villain_position.value,
        "hero_is_ip": scenario.hero_is_ip,
        "preflop_aggressor": scenario.preflop_aggressor.value,
        "default_pot": scenario.default_pot,
        "hero_range_tokens": list(scenario.hero_range_tokens),
        "villain_range_tokens": list(scenario.villain_range_tokens),
        "hero_scenario_name": scenario.hero_scenario_name,
        "villain_scenario_name": scenario.villain_scenario_name,
        "hero_action_bubble": scenario.hero_action_bubble,
        "villain_action_bubble": scenario.villain_action_bubble,
        "players_not_folded_hero_action": list(scenario.players_not_folded_hero_action),
        "players_not_folded_villain_action": list(scenario.players_not_folded_villain_action),
        "non_aggressor_previous_action": scenario.non_aggressor_previous_action,
        "oop_player": scenario.oop_player.value,
        "ip_player": scenario.ip_player.value,
        "first_to_act_postflop": scenario.first_to_act_postflop.value,
    }


@router.get("")
def get_scenarios() -> list[dict]:
    return [_serialize_scenario(scenario) for scenario in list_scenarios()]


@router.get("/{scenario_id}")
def get_scenario_by_id(scenario_id: str) -> dict:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario_id: {scenario_id}")
    return _serialize_scenario(scenario)