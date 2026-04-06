from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from api.app.config import settings
from api.app.models.betting import ActionEvent, ActionHistory, BettingRoundState
from api.app.models.enums import ActionType, Player, Street, UIGate, UserRole
from api.app.models.state import HandState, SessionState
from api.app.services.assignment_service import create_assignment
from api.app.services.auth_service import create_owner_if_none, create_user, link_external_identity
from api.app.services.audit_service import log_audit_event
from api.app.services.organization_service import add_user_to_organization, create_organization
from api.app.storage.db import get_connection, init_db, json_dumps
from api.app.storage.memory_store import store


def _reset_database() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_tokens")
        conn.execute("DELETE FROM password_reset_tokens")
        conn.execute("DELETE FROM external_identities")
        conn.execute("DELETE FROM organization_memberships")
        conn.execute("DELETE FROM audit_logs")
        conn.execute("DELETE FROM assignments")
        conn.execute("DELETE FROM hand_results")
        conn.execute("DELETE FROM hands")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM organizations")
        conn.execute("DELETE FROM users")


def _now() -> datetime:
    return datetime.now(UTC)


def _hero_tokens() -> list[str]:
    return [
        "AA", "KK", "QQ", "JJ", "TT", "AKs", "AQs", "AJs", "KQs", "AKo", "AQo", "A5s"
    ]


def _session_payload(*, user_id: str, villain_profile_id: str, scenario_id: str) -> SessionState:
    return SessionState(
        session_id=str(uuid4()),
        user_id=user_id,
        villain_profile_id=villain_profile_id,
        train_timer_seconds=30,
        scenario_id=scenario_id,
        pot=22.5,
        hero_stack=178.0,
        villain_stack=183.0,
        hero_range_matrix_saved={"seeded": True, "mode": "raise"},
        hero_tokens_saved=_hero_tokens(),
        villain_range_matrix_saved={"seeded": True, "mode": "call"},
        villain_tokens_saved=["QQ", "JJ", "TT", "AKs", "AQs", "KQs", "QJs", "JTs", "T9s"],
        hero_range_confirmed=True,
        villain_range_confirmed=True,
    )


def _complete_hand(
    *,
    session: SessionState,
    villain_profile_id: str,
    scenario_id: str,
    hero_hand: tuple[str, str],
    villain_hand: tuple[str, str],
    board: list[str],
    history_events: list[ActionEvent],
    villain_range_combos_live: dict[str, list[list[str]]],
    ranging_score: float,
    response_score: float,
    prune_evaluations: list[dict[str, Any]],
    response_evaluations: list[dict[str, Any]],
) -> str:
    hand = HandState(
        hand_id=str(uuid4()),
        session_id=session.session_id,
        user_id=session.user_id,
        scenario_id=scenario_id,
        villain_profile_id=villain_profile_id,
        pot=126.0,
        hero_stack=102.0,
        villain_stack=94.0,
        hero_hand=hero_hand,
        villain_hand=villain_hand,
        board=board,
        street=Street.RIVER,
        betting_round=BettingRoundState(),
        history=ActionHistory(events=history_events),
        hero_tokens_saved=list(session.hero_tokens_saved),
        villain_range_matrix_saved=session.villain_range_matrix_saved,
        villain_range_combos_live=villain_range_combos_live,
        current_actor=Player.HERO,
        current_aggressor=Player.VILLAIN,
        ui_gate=UIGate.HAND_OVER,
        hand_over=True,
        bucket_seed=42,
    )
    store.create_hand(hand.hand_id, asdict(hand))
    overall_score = round((ranging_score + response_score) / 2.0, 2)
    metadata = {
        "score_version": 2,
        "scoring_ready": True,
        "seeded_demo": True,
        "summary": {
            "prune_steps_scored": len(prune_evaluations),
            "response_nodes_scored": len([item for item in response_evaluations if item.get("supported") and item.get("score") is not None]),
            "ranging_score": ranging_score,
            "response_score": response_score,
            "overall_score": overall_score,
        },
        "prune_evaluations": prune_evaluations,
        "response_evaluations": response_evaluations,
    }
    store.update_hand_result_scores(
        hand.hand_id,
        ranging_score=ranging_score,
        response_score=response_score,
        overall_score=overall_score,
        metadata=metadata,
    )
    return hand.hand_id


def _active_hand(*, session: SessionState, villain_profile_id: str, scenario_id: str) -> str:
    hand = HandState(
        hand_id=str(uuid4()),
        session_id=session.session_id,
        user_id=session.user_id,
        scenario_id=scenario_id,
        villain_profile_id=villain_profile_id,
        pot=74.0,
        hero_stack=137.0,
        villain_stack=132.0,
        hero_hand=("Ac", "Kd"),
        villain_hand=("9h", "8h"),
        board=["Jh", "7c", "4h", "2s"],
        street=Street.TURN,
        betting_round=BettingRoundState(current_bet=18.0, hero_contrib=18.0, villain_contrib=0.0, last_raise_size=0.0, folded=False),
        history=ActionHistory(events=[
            ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CHECK, amount=0.0, note="Seeded demo flop check", forced=True),
            ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.BET, amount=7.5, note="Demo c-bet"),
            ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CALL, amount=7.5, note="Demo call"),
            ActionEvent(street=Street.TURN, actor=Player.VILLAIN, action=ActionType.BET, amount=18.0, note="Demo lead"),
        ]),
        hero_tokens_saved=list(session.hero_tokens_saved),
        villain_range_matrix_saved=session.villain_range_matrix_saved,
        villain_range_combos_live={
            "T9s": [["9h", "8h"], ["9s", "8s"]],
            "JhTs": [["Jh", "Th"]],
            "AhQh": [["Ah", "Qh"]],
        },
        current_actor=Player.HERO,
        current_aggressor=Player.VILLAIN,
        ui_gate=UIGate.MUST_FILL_RESPONSE_MATRIX,
        hand_over=False,
        bucket_seed=77,
        response_matrix_columns=["call", "raise"],
        response_matrix_saved={"selections": {}},
    )
    store.create_hand(hand.hand_id, asdict(hand))
    return hand.hand_id


def seed_demo_data(*, reset: bool = False) -> dict[str, Any]:
    init_db()
    if reset:
        _reset_database()
        init_db()

    owner = create_owner_if_none(email=settings.demo_owner_email, password=settings.demo_seed_password, display_name="Demo Owner")
    coach = create_user(email=settings.demo_coach_email, password=settings.demo_seed_password, display_name="Demo Coach", role=UserRole.COACH)
    member = create_user(email=settings.demo_member_email, password=settings.demo_seed_password, display_name="Demo Member", role=UserRole.MEMBER)
    member_two = create_user(email="member2@demo.local", password=settings.demo_seed_password, display_name="Member Struggling", role=UserRole.MEMBER)

    org = create_organization(name=settings.demo_org_name, slug="demo-poker-academy", external_provider="kajabi", external_org_id="demo-kajabi-org")
    add_user_to_organization(organization_id=org["organization_id"], user_id=owner.user_id, membership_role="owner")
    add_user_to_organization(organization_id=org["organization_id"], user_id=coach.user_id, membership_role="coach")
    add_user_to_organization(organization_id=org["organization_id"], user_id=member.user_id, membership_role="member")
    add_user_to_organization(organization_id=org["organization_id"], user_id=member_two.user_id, membership_role="member")

    link_external_identity(user_id=coach.user_id, provider="kajabi", external_user_id="coach-001", external_email=coach.email, metadata={"plan": "coach"})
    link_external_identity(user_id=member.user_id, provider="kajabi", external_user_id="member-001", external_email=member.email, metadata={"plan": "basecamp"})
    link_external_identity(user_id=member_two.user_id, provider="kajabi", external_user_id="member-002", external_email=member_two.email, metadata={"plan": "basecamp"})

    member_session_1 = _session_payload(user_id=member.user_id, villain_profile_id="tag", scenario_id="3bet_ip_co_vs_hj")
    member_session_2 = _session_payload(user_id=member.user_id, villain_profile_id="calling_station", scenario_id="srp_ip_btn_vs_bb")
    member_session_3 = _session_payload(user_id=member.user_id, villain_profile_id="maniac", scenario_id="3bet_oop_sb_vs_co")
    member2_session_1 = _session_payload(user_id=member_two.user_id, villain_profile_id="weak_tight", scenario_id="srp_oop_utg_vs_btn")
    member2_session_2 = _session_payload(user_id=member_two.user_id, villain_profile_id="maniac", scenario_id="3bet_ip_co_vs_hj")

    for session in [member_session_1, member_session_2, member_session_3, member2_session_1, member2_session_2]:
        store.create_session(session.session_id, asdict(session))

    member_hand_ids = [
        _complete_hand(
            session=member_session_1,
            villain_profile_id="tag",
            scenario_id="3bet_ip_co_vs_hj",
            hero_hand=("As", "Kd"),
            villain_hand=("Qh", "Qs"),
            board=["Qc", "7d", "2s", "Th", "3c"],
            history_events=[
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CHECK, amount=0.0, note="Villain checked range", forced=True),
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.BET, amount=8.0, note="Hero bet small"),
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CALL, amount=8.0, note="Villain called with value"),
                ActionEvent(street=Street.TURN, actor=Player.VILLAIN, action=ActionType.BET, amount=18.0, note="Villain led turn"),
                ActionEvent(street=Street.TURN, actor=Player.HERO, action=ActionType.CALL, amount=18.0, note="Hero called"),
                ActionEvent(street=Street.RIVER, actor=Player.VILLAIN, action=ActionType.BET, amount=42.0, note="Villain value bet river"),
                ActionEvent(street=Street.RIVER, actor=Player.HERO, action=ActionType.FOLD, amount=0.0, note="Hero folded river"),
            ],
            villain_range_combos_live={"QQ": [["Qh", "Qs"]], "AQs": [["Ah", "Qd"]], "KQs": [["Kh", "Qd"]]},
            ranging_score=88.0,
            response_score=100.0,
            prune_evaluations=[{
                "street": "turn", "villain_action": "bet", "actual_bucket": "Value", "actual_subgroup": "Set", "start_live_combos": 22, "end_live_combos": 5,
                "combo_alive": True, "bucket_alive": True, "subgroup_alive": True, "remaining_labels_for_true_combo": ["QQ"], "efficiency_score": 60.0, "overall_score": 88.0,
            }],
            response_evaluations=[{
                "street": "flop", "actual_bucket": "Value", "actual_subgroup": "Set", "hero_action": "bet", "hero_amount": 8.0,
                "column": "bet_small", "predicted": "C", "actual": "C", "villain_action": "call", "supported": True, "score": 100.0, "correct": True, "reason": None,
            }],
        ),
        _complete_hand(
            session=member_session_2,
            villain_profile_id="calling_station",
            scenario_id="srp_ip_btn_vs_bb",
            hero_hand=("Ah", "Kd"),
            villain_hand=("Jh", "9h"),
            board=["Kh", "Th", "3c", "2d", "8h"],
            history_events=[
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CHECK, amount=0.0, note="Villain checked flop", forced=True),
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.BET, amount=6.5, note="Hero bet small"),
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CALL, amount=6.5, note="Villain overcalled draw"),
                ActionEvent(street=Street.TURN, actor=Player.VILLAIN, action=ActionType.CHECK, amount=0.0, note="Villain checked turn"),
                ActionEvent(street=Street.TURN, actor=Player.HERO, action=ActionType.BET, amount=14.0, note="Hero bet turn"),
                ActionEvent(street=Street.TURN, actor=Player.VILLAIN, action=ActionType.CALL, amount=14.0, note="Villain called again"),
                ActionEvent(street=Street.RIVER, actor=Player.VILLAIN, action=ActionType.CHECK, amount=0.0, note="Villain checked flush river"),
                ActionEvent(street=Street.RIVER, actor=Player.HERO, action=ActionType.CHECK, amount=0.0, note="Hero checked back"),
            ],
            villain_range_combos_live={"J9s": [["Jh", "9h"]], "QJh": [["Qh", "Jh"]], "A5h": [["Ah", "5h"]]},
            ranging_score=74.0,
            response_score=0.0,
            prune_evaluations=[{
                "street": "turn", "villain_action": "call", "actual_bucket": "Draw", "actual_subgroup": "Flush Draw", "start_live_combos": 28, "end_live_combos": 11,
                "combo_alive": True, "bucket_alive": True, "subgroup_alive": True, "remaining_labels_for_true_combo": ["J9s"], "efficiency_score": 18.0, "overall_score": 74.0,
            }],
            response_evaluations=[{
                "street": "flop", "actual_bucket": "Draw", "actual_subgroup": "Flush Draw", "hero_action": "bet", "hero_amount": 6.5,
                "column": "bet_small", "predicted": "F", "actual": "C", "villain_action": "call", "supported": True, "score": 0.0, "correct": False, "reason": None,
            }],
        ),
        _complete_hand(
            session=member_session_3,
            villain_profile_id="maniac",
            scenario_id="3bet_oop_sb_vs_co",
            hero_hand=("Ac", "Qs"),
            villain_hand=("9c", "8c"),
            board=["7c", "6d", "2h", "Tc", "Kd"],
            history_events=[
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.CHECK, amount=0.0, note="Hero checked"),
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.BET, amount=11.0, note="Villain stabbed flop"),
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.CALL, amount=11.0, note="Hero called"),
                ActionEvent(street=Street.TURN, actor=Player.HERO, action=ActionType.CHECK, amount=0.0, note="Hero checked turn"),
                ActionEvent(street=Street.TURN, actor=Player.VILLAIN, action=ActionType.BET, amount=24.0, note="Villain barreled"),
                ActionEvent(street=Street.TURN, actor=Player.HERO, action=ActionType.FOLD, amount=0.0, note="Hero folded turn"),
            ],
            villain_range_combos_live={"98s": [["9c", "8c"]], "A5s": [["Ah", "5h"]], "J9s": [["Jc", "9c"]]},
            ranging_score=92.0,
            response_score=100.0,
            prune_evaluations=[{
                "street": "turn", "villain_action": "bet", "actual_bucket": "Draw", "actual_subgroup": "Combo Draw", "start_live_combos": 19, "end_live_combos": 4,
                "combo_alive": True, "bucket_alive": True, "subgroup_alive": True, "remaining_labels_for_true_combo": ["98s"], "efficiency_score": 74.0, "overall_score": 92.0,
            }],
            response_evaluations=[{
                "street": "flop", "actual_bucket": "Draw", "actual_subgroup": "Combo Draw", "hero_action": "check", "hero_amount": 0.0,
                "column": "check", "predicted": "B", "actual": "B", "villain_action": "bet", "supported": True, "score": 100.0, "correct": True, "reason": None,
            }],
        ),
    ]

    member_two_hand_ids = [
        _complete_hand(
            session=member2_session_1,
            villain_profile_id="weak_tight",
            scenario_id="srp_oop_utg_vs_btn",
            hero_hand=("Ad", "Kh"),
            villain_hand=("Ts", "Td"),
            board=["Tc", "8s", "2d", "4h", "Jc"],
            history_events=[
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.CHECK, amount=0.0, note="Hero checked flop"),
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.BET, amount=7.0, note="Villain bet"),
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.CALL, amount=7.0, note="Hero called"),
                ActionEvent(street=Street.TURN, actor=Player.HERO, action=ActionType.CHECK, amount=0.0, note="Hero checked turn"),
                ActionEvent(street=Street.TURN, actor=Player.VILLAIN, action=ActionType.BET, amount=15.0, note="Villain bet turn"),
                ActionEvent(street=Street.TURN, actor=Player.HERO, action=ActionType.FOLD, amount=0.0, note="Hero folded"),
            ],
            villain_range_combos_live={"TT": [["Ts", "Td"]], "JJ": [["Js", "Jd"]], "AQ": [["As", "Qd"]]},
            ranging_score=55.0,
            response_score=0.0,
            prune_evaluations=[{
                "street": "turn", "villain_action": "bet", "actual_bucket": "Value", "actual_subgroup": "Set", "start_live_combos": 17, "end_live_combos": 13,
                "combo_alive": True, "bucket_alive": True, "subgroup_alive": True, "remaining_labels_for_true_combo": ["TT"], "efficiency_score": 5.0, "overall_score": 55.0,
            }],
            response_evaluations=[{
                "street": "flop", "actual_bucket": "Value", "actual_subgroup": "Set", "hero_action": "check", "hero_amount": 0.0,
                "column": "check", "predicted": "X", "actual": "B", "villain_action": "bet", "supported": True, "score": 0.0, "correct": False, "reason": None,
            }],
        ),
        _complete_hand(
            session=member2_session_2,
            villain_profile_id="maniac",
            scenario_id="3bet_ip_co_vs_hj",
            hero_hand=("As", "Jd"),
            villain_hand=("Kc", "Qd"),
            board=["Jh", "Td", "3s", "9c", "2h"],
            history_events=[
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.CHECK, amount=0.0, note="Villain checked"),
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.BET, amount=8.5, note="Hero bet flop"),
                ActionEvent(street=Street.FLOP, actor=Player.VILLAIN, action=ActionType.RAISE, amount=25.0, note="Villain check-raised draw"),
                ActionEvent(street=Street.FLOP, actor=Player.HERO, action=ActionType.FOLD, amount=0.0, note="Hero folded flop"),
            ],
            villain_range_combos_live={"KQo": [["Kc", "Qd"]], "Q9s": [["Qc", "9c"]], "A5s": [["Ah", "5h"]]},
            ranging_score=68.0,
            response_score=100.0,
            prune_evaluations=[{
                "street": "flop", "villain_action": "raise", "actual_bucket": "Draw", "actual_subgroup": "Straight Draw", "start_live_combos": 24, "end_live_combos": 9,
                "combo_alive": True, "bucket_alive": True, "subgroup_alive": True, "remaining_labels_for_true_combo": ["KQo"], "efficiency_score": 40.0, "overall_score": 68.0,
            }],
            response_evaluations=[{
                "street": "flop", "actual_bucket": "Draw", "actual_subgroup": "Straight Draw", "hero_action": "bet", "hero_amount": 8.5,
                "column": "bet_small", "predicted": "R", "actual": "R", "villain_action": "raise", "supported": True, "score": 100.0, "correct": True, "reason": None,
            }],
        ),
    ]

    active_hand_id = _active_hand(session=member_session_2, villain_profile_id="calling_station", scenario_id="srp_ip_btn_vs_bb")

    due_soon = (_now() + timedelta(days=7)).isoformat()
    overdue = (_now() - timedelta(days=2)).isoformat()
    create_assignment(
        created_by_user_id=coach.user_id,
        target_user_id=member.user_id,
        title="Sharpen 3Bet IP reps",
        description="Complete 12 more reps in 3Bet IP spots and keep your ranging discipline above 80.",
        scenario_id="3bet_ip_co_vs_hj",
        villain_profile_id=None,
        repetition_target=12,
        minimum_overall_score=80.0,
        due_at=due_soon,
    )
    create_assignment(
        created_by_user_id=coach.user_id,
        target_user_id=member.user_id,
        title="Mike-style overcall prep",
        description="Drill calling-station nodes and tighten your response predictions.",
        scenario_id="srp_ip_btn_vs_bb",
        villain_profile_id="calling_station",
        repetition_target=8,
        minimum_overall_score=75.0,
        due_at=due_soon,
    )
    create_assignment(
        created_by_user_id=coach.user_id,
        target_user_id=member_two.user_id,
        title="Catch up on OOP discipline",
        description="Your last results suggest you need a tighter pruning process out of position.",
        scenario_id="srp_oop_utg_vs_btn",
        villain_profile_id="weak_tight",
        repetition_target=10,
        minimum_overall_score=70.0,
        due_at=overdue,
    )

    log_audit_event(action_type="demo_seed_run", actor=owner, metadata={"reset": reset, "organization_id": org["organization_id"]})

    with get_connection() as conn:
        conn.execute(
            "UPDATE hand_results SET started_at = ?, updated_at = ? WHERE hand_id = ?",
            ((_now() - timedelta(days=4)).isoformat(), (_now() - timedelta(days=4)).isoformat(), member_hand_ids[0]),
        )
        conn.execute(
            "UPDATE hand_results SET started_at = ?, updated_at = ? WHERE hand_id = ?",
            ((_now() - timedelta(days=3)).isoformat(), (_now() - timedelta(days=3)).isoformat(), member_hand_ids[1]),
        )
        conn.execute(
            "UPDATE hand_results SET started_at = ?, updated_at = ? WHERE hand_id = ?",
            ((_now() - timedelta(days=1)).isoformat(), (_now() - timedelta(days=1)).isoformat(), member_hand_ids[2]),
        )

    return {
        "owner": owner.email,
        "coach": coach.email,
        "member": member.email,
        "member_two": member_two.email,
        "password": settings.demo_seed_password,
        "organization": org["name"],
        "seeded_completed_hands": len(member_hand_ids) + len(member_two_hand_ids),
        "seeded_active_hand": active_hand_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a demo-ready environment for Villain Range Trainer.")
    parser.add_argument("--reset", action="store_true", help="Wipe existing data before seeding demo data.")
    args = parser.parse_args()

    payload = seed_demo_data(reset=args.reset)
    print(json_dumps(payload))


if __name__ == "__main__":
    main()
