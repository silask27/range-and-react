from __future__ import annotations

from dataclasses import asdict
import os
import unittest
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("VRT_DATABASE_PATH", str(Path("./data/regression_test.db").resolve()))
os.environ.setdefault("VRT_PASSWORD_RESET_RETURNS_TOKEN", "true")
os.environ.setdefault("VRT_REQUIRE_SIGNUP_INVITE", "true")
os.environ.setdefault("VRT_PUBLIC_STATUS_DETAILED_CHECKS", "false")
os.environ.setdefault("VRT_PUBLIC_STATUS_SHOW_DEMO_DETAILS", "false")

from fastapi.testclient import TestClient

from api.app.main import app
from api.app.engine.bucketizer import _one_pair_subgroup
from api.app.models.betting import ActionEvent, BettingRoundState
from api.app.models.enums import ActionType, Player, Street, UIGate
from api.app.models.state import HandState, SessionState
from api.app.services.action_service import apply_hero_action
from api.app.services.assignment_service import create_assignment, list_assignments_with_progress
from api.app.services.prune_service import _advance_to_next_street as _advance_to_next_street_after_prune
from api.app.services.response_matrix_service import save_response_matrix
from api.app.services.response_matrix_prefill import prepare_response_matrix_for_new_node
from api.app.storage.db import get_connection, init_db
from api.app.storage.memory_store import store


class RegressionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        db_path = Path(os.environ["VRT_DATABASE_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        init_db()
        cls.client = TestClient(app)

        bootstrap = cls.client.post(
            "/auth/bootstrap-owner",
            json={"email": "owner@example.com", "password": "Password123!", "display_name": "Owner"},
        )
        assert bootstrap.status_code == 200, bootstrap.text
        cls.owner_token = bootstrap.json()["token"]
        cls.owner_user_id = bootstrap.json()["user"]["user_id"]

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO organizations (
                    organization_id, name, slug, external_provider, external_org_id, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, '{}', datetime('now'), datetime('now'))
                """,
                ("org-alpha", "Alpha Org", "alpha-org"),
            )
            conn.execute(
                """
                INSERT INTO organizations (
                    organization_id, name, slug, external_provider, external_org_id, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, '{}', datetime('now'), datetime('now'))
                """,
                ("org-beta", "Beta Org", "beta-org"),
            )
            conn.execute(
                """
                INSERT INTO organization_memberships (
                    organization_membership_id, organization_id, user_id, membership_role, created_at
                ) VALUES (?, ?, ?, ?, datetime('now'))
                """,
                ("owner-alpha", "org-alpha", cls.owner_user_id, "owner"),
            )
            conn.execute(
                """
                INSERT INTO organization_memberships (
                    organization_membership_id, organization_id, user_id, membership_role, created_at
                ) VALUES (?, ?, ?, ?, datetime('now'))
                """,
                ("owner-beta", "org-beta", cls.owner_user_id, "owner"),
            )

        coach_invite = cls.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {cls.owner_token}"},
            json={"email": "coach@example.com", "role": "coach", "organization_id": "org-alpha", "membership_role": "coach"},
        )
        assert coach_invite.status_code == 200, coach_invite.text
        coach_code = coach_invite.json()["invite"]["invite_code"]
        coach_signup = cls.client.post(
            "/auth/signup",
            json={"email": "coach@example.com", "password": "Password123!", "display_name": "Coach", "invite_code": coach_code},
        )
        assert coach_signup.status_code == 200, coach_signup.text
        cls.coach_token = coach_signup.json()["token"]

        admin_invite = cls.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {cls.owner_token}"},
            json={"email": "admin@example.com", "role": "admin", "organization_id": "org-alpha", "membership_role": "admin"},
        )
        assert admin_invite.status_code == 200, admin_invite.text
        admin_code = admin_invite.json()["invite"]["invite_code"]
        admin_signup = cls.client.post(
            "/auth/signup",
            json={"email": "admin@example.com", "password": "Password123!", "display_name": "Admin", "invite_code": admin_code},
        )
        assert admin_signup.status_code == 200, admin_signup.text
        cls.admin_token = admin_signup.json()["token"]

        member_invite = cls.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {cls.owner_token}"},
            json={"email": "member@example.com", "role": "member", "organization_id": "org-alpha", "membership_role": "member"},
        )
        assert member_invite.status_code == 200, member_invite.text
        member_code = member_invite.json()["invite"]["invite_code"]
        member_signup = cls.client.post(
            "/auth/signup",
            json={"email": "member@example.com", "password": "Password123!", "display_name": "Member", "invite_code": member_code},
        )
        assert member_signup.status_code == 200, member_signup.text
        cls.member_token = member_signup.json()["token"]
        cls.member_user_id = member_signup.json()["user"]["user_id"]

        other_invite = cls.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {cls.owner_token}"},
            json={"email": "outsider@example.com", "role": "member", "organization_id": "org-beta", "membership_role": "member"},
        )
        assert other_invite.status_code == 200, other_invite.text
        other_code = other_invite.json()["invite"]["invite_code"]
        other_signup = cls.client.post(
            "/auth/signup",
            json={"email": "outsider@example.com", "password": "Password123!", "display_name": "Outsider", "invite_code": other_code},
        )
        assert other_signup.status_code == 200, other_signup.text
        cls.outsider_user_id = other_signup.json()["user"]["user_id"]


    def _create_session_fixture(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        pot: float = 20.0,
        hero_stack: float = 100.0,
        villain_stack: float = 100.0,
    ) -> None:
        session = SessionState(
            session_id=session_id,
            user_id=user_id or self.owner_user_id,
            villain_profile_id="tag",
            train_timer_seconds=30,
            scenario_id="srp_ip_btn_vs_bb",
            pot=pot,
            hero_stack=hero_stack,
            villain_stack=villain_stack,
            hero_range_matrix_saved={"AA": True, "KK": True, "QQ": True, "AKs": True, "AKo": True},
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_matrix_saved={"QQ": True},
            villain_tokens_saved=["QQ"],
            hero_range_confirmed=True,
            villain_range_confirmed=True,
        )
        store.create_session(session.session_id, asdict(session))


    def test_login_route_returns_success(self) -> None:
        response = self.client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("token", payload)
        self.assertEqual(payload["user"]["email"], "owner@example.com")

    def test_default_hero_stacks_stay_in_deep_training_band(self) -> None:
        hero_stacks: list[float] = []
        villain_stacks: list[float] = []

        for seed in range(1, 16):
            session_response = self.client.post(
                "/sessions",
                headers={"Authorization": f"Bearer {self.owner_token}"},
                json={"villain_profile_id": "tag", "train_timer_seconds": 30},
            )
            self.assertEqual(session_response.status_code, 200)
            session_id = session_response.json()["session_id"]
            scenario_response = self.client.post(
                f"/sessions/{session_id}/scenario",
                headers={"Authorization": f"Bearer {self.owner_token}"},
                json={"scenario_id": "srp_ip_btn_vs_bb", "seed": seed},
            )
            self.assertEqual(scenario_response.status_code, 200)
            payload = scenario_response.json()
            hero_stacks.append(float(payload["hero_stack"]))
            villain_stacks.append(float(payload["villain_stack"]))

        self.assertGreater(len(set(hero_stacks)), 1)
        self.assertGreaterEqual(min(hero_stacks), 250.0)
        self.assertLessEqual(max(hero_stacks), 400.0)
        self.assertGreater(len(set(villain_stacks)), 1)

    def test_hero_bet_and_raise_cannot_exceed_effective_stack(self) -> None:
        self._create_session_fixture(session_id="effective-stack-bet-session", villain_stack=25.0)
        bet_hand = HandState(
            hand_id="effective-stack-bet-hand",
            session_id="effective-stack-bet-session",
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=25.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh"],
            street=Street.FLOP,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.HERO_TO_ACT,
        )
        store.create_hand(bet_hand.hand_id, asdict(bet_hand))

        with self.assertRaisesRegex(ValueError, "effective stack"):
            apply_hero_action(hand_id=bet_hand.hand_id, action="bet", amount=26.0, iters=10)

        self._create_session_fixture(session_id="effective-stack-raise-session", pot=45.0, hero_stack=100.0, villain_stack=45.0)
        raise_hand = HandState(
            hand_id="effective-stack-raise-hand",
            session_id="effective-stack-raise-session",
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=45.0,
            hero_stack=95.0,
            villain_stack=25.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh"],
            street=Street.FLOP,
            betting_round=BettingRoundState(
                current_bet=20.0,
                hero_contrib=5.0,
                villain_contrib=20.0,
                last_raise_size=15.0,
            ),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.HERO_TO_ACT,
        )
        store.create_hand(raise_hand.hand_id, asdict(raise_hand))

        with self.assertRaisesRegex(ValueError, "effective all-in"):
            apply_hero_action(hand_id=raise_hand.hand_id, action="raise", amount=31.0, iters=10)

    def test_low_pair_only_covers_bottom_pair_or_below_board_pocket_pairs(self) -> None:
        board = ["Ac", "Td", "7s"]

        self.assertEqual(_one_pair_subgroup(("9c", "9d"), board), "Mid Pair")
        self.assertEqual(_one_pair_subgroup(("8c", "8d"), board), "Mid Pair")
        self.assertEqual(_one_pair_subgroup(("7c", "6d"), board), "Low Pair")
        self.assertEqual(_one_pair_subgroup(("3c", "3d"), board), "Low Pair")

    def test_coach_invite_creates_coach_account(self) -> None:
        response = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {self.coach_token}"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["role"], "coach")

    def test_cannot_invite_existing_email(self) -> None:
        response = self.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {self.owner_token}"},
            json={"email": "member@example.com", "role": "coach", "organization_id": "org-alpha", "membership_role": "coach"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.json()["detail"].lower())

    def test_owner_can_delete_user(self) -> None:
        invite = self.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {self.owner_token}"},
            json={"email": "delete-me@example.com", "role": "member", "organization_id": "org-alpha", "membership_role": "member"},
        )
        self.assertEqual(invite.status_code, 200)
        code = invite.json()["invite"]["invite_code"]
        signup = self.client.post(
            "/auth/signup",
            json={"email": "delete-me@example.com", "password": "Password123!", "display_name": "Delete Me", "invite_code": code},
        )
        self.assertEqual(signup.status_code, 200)
        user_id = signup.json()["user"]["user_id"]
        delete_response = self.client.delete(
            f"/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(delete_response.status_code, 200)
        lookup = self.client.post(
            "/auth/login",
            json={"email": "delete-me@example.com", "password": "Password123!"},
        )
        self.assertEqual(lookup.status_code, 400)

    def test_coach_cannot_permanently_delete_member(self) -> None:
        delete_response = self.client.delete(
            f"/admin/users/{self.member_user_id}",
            headers={"Authorization": f"Bearer {self.coach_token}"},
        )
        self.assertEqual(delete_response.status_code, 403)

    def test_cohort_member_editor_can_remove_members(self) -> None:
        create_response = self.client.post(
            "/admin/cohorts",
            headers={"Authorization": f"Bearer {self.owner_token}"},
            json={
                "organization_id": "org-alpha",
                "name": "Regression Cohort",
                "user_ids": [self.member_user_id],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        cohort_id = create_response.json()["cohort"]["cohort_id"]
        self.assertEqual(create_response.json()["cohort"]["member_count"], 1)

        before = self.client.get(
            f"/admin/cohorts/{cohort_id}/members",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(before.status_code, 200)
        self.assertIn(self.member_user_id, {row["user_id"] for row in before.json()["members"]})

        remove_response = self.client.delete(
            f"/admin/cohorts/{cohort_id}/members/{self.member_user_id}",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(remove_response.json()["cohort"]["member_count"], 0)

        after = self.client.get(
            f"/admin/cohorts/{cohort_id}/members",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(after.status_code, 200)
        self.assertNotIn(self.member_user_id, {row["user_id"] for row in after.json()["members"]})

    def test_unscoped_admin_does_not_see_all_organizations_or_invites(self) -> None:
        invite = self.client.post(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {self.owner_token}"},
            json={"email": "unscoped-admin@example.com", "role": "admin"},
        )
        self.assertEqual(invite.status_code, 200)
        code = invite.json()["invite"]["invite_code"]
        signup = self.client.post(
            "/auth/signup",
            json={"email": "unscoped-admin@example.com", "password": "Password123!", "display_name": "Unscoped Admin", "invite_code": code},
        )
        self.assertEqual(signup.status_code, 200)
        token = signup.json()["token"]

        orgs = self.client.get(
            "/admin/organizations",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(orgs.status_code, 200)
        self.assertEqual(orgs.json()["organizations"], [])

        invites = self.client.get(
            "/admin/signup-invites",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(invites.status_code, 200)
        self.assertEqual(invites.json()["invites"], [])

    def test_completed_assignment_filter_derives_status_before_pagination(self) -> None:
        completed_assignment = create_assignment(
            created_by_user_id=self.owner_user_id,
            target_user_id=self.member_user_id,
            organization_id="org-alpha",
            title="Completed before newer active assignments",
            description=None,
            scenario_id=None,
            villain_profile_id=None,
            repetition_target=1,
            minimum_overall_score=None,
            due_at=None,
        )
        session = SessionState(
            session_id=str(uuid4()),
            user_id=self.member_user_id,
            villain_profile_id="tag",
            train_timer_seconds=30,
            scenario_id="srp_ip_btn_vs_bb",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_range_matrix_saved={"AA": True, "AKs": True},
            hero_tokens_saved=["AA", "AKs"],
            villain_range_matrix_saved={"QQ": True},
            villain_tokens_saved=["QQ"],
            hero_range_confirmed=True,
            villain_range_confirmed=True,
        )
        store.create_session(session.session_id, asdict(session))
        hand = HandState(
            hand_id=str(uuid4()),
            session_id=session.session_id,
            user_id=self.member_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=40.0,
            hero_stack=90.0,
            villain_stack=90.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh", "8c", "9s"],
            street=Street.RIVER,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "AKs"],
            villain_range_matrix_saved={"QQ": True},
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.HAND_OVER,
            hand_over=True,
        )
        store.create_hand(hand.hand_id, asdict(hand))
        store.update_hand_result_scores(
            hand.hand_id,
            ranging_score=90.0,
            response_score=90.0,
            overall_score=90.0,
            metadata={"score_version": 2, "scoring_ready": True},
        )
        for idx in range(3):
            create_assignment(
                created_by_user_id=self.owner_user_id,
                target_user_id=self.member_user_id,
                organization_id="org-alpha",
                title=f"Newer active assignment {idx}",
                description=None,
                scenario_id="3bet_ip_co_vs_hj",
                villain_profile_id=None,
                repetition_target=5,
                minimum_overall_score=None,
                due_at=None,
            )

        completed = list_assignments_with_progress(
            target_user_id=self.member_user_id,
            status="completed",
            limit=1,
            offset=0,
        )
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["assignment_id"], completed_assignment["assignment_id"])

    def test_public_signup_blocks_role_escalation(self) -> None:
        response = self.client.post(
            "/auth/signup",
            json={
                "email": "illegal@example.com",
                "password": "Password123!",
                "display_name": "Illegal",
                "role": "owner",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_public_status_hides_detailed_checks(self) -> None:
        response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("detail_visibility"), "summary")
        self.assertNotIn("checks", payload)

    def test_coach_user_visibility_is_scoped(self) -> None:
        response = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {self.coach_token}"},
        )
        self.assertEqual(response.status_code, 200)
        emails = {item["email"] for item in response.json()["users"]}
        self.assertIn("coach@example.com", emails)
        self.assertIn("member@example.com", emails)
        self.assertNotIn("outsider@example.com", emails)

    def test_org_admin_user_visibility_is_scoped(self) -> None:
        response = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        emails = {item["email"] for item in response.json()["users"]}
        self.assertIn("admin@example.com", emails)
        self.assertIn("member@example.com", emails)
        self.assertNotIn("outsider@example.com", emails)

    def test_cross_org_direct_hand_ids_are_blocked_for_coach_and_admin(self) -> None:
        session = SessionState(
            session_id="outsider-session",
            user_id=self.outsider_user_id,
            villain_profile_id="tag",
            train_timer_seconds=30,
            scenario_id="srp_ip_btn_vs_bb",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_range_matrix_saved={"AA": True, "AKs": True},
            hero_tokens_saved=["AA", "AKs"],
            villain_range_matrix_saved={"QQ": True},
            villain_tokens_saved=["QQ"],
            hero_range_confirmed=True,
            villain_range_confirmed=True,
        )
        store.create_session(session.session_id, asdict(session))

        hand = HandState(
            hand_id="outsider-complete-hand",
            session_id=session.session_id,
            user_id=self.outsider_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=40.0,
            hero_stack=90.0,
            villain_stack=90.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh", "8c", "9s"],
            street=Street.RIVER,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "AKs"],
            villain_range_matrix_saved={"QQ": True},
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.HAND_OVER,
            hand_over=True,
        )
        store.create_hand(hand.hand_id, asdict(hand))

        for token in (self.coach_token, self.admin_token):
            hand_response = self.client.get(
                f"/hands/{hand.hand_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(hand_response.status_code, 403)

            debrief_response = self.client.get(
                f"/results/hand/{hand.hand_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(debrief_response.status_code, 403)

            replay_response = self.client.get(
                f"/results/hand/{hand.hand_id}/replay",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(replay_response.status_code, 403)

        owner_response = self.client.get(
            f"/results/hand/{hand.hand_id}",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(owner_response.status_code, 200)

    def test_coach_cannot_assign_outside_org(self) -> None:
        response = self.client.post(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {self.coach_token}"},
            json={
                "target_user_id": self.outsider_user_id,
                "title": "Out-of-scope assignment",
                "description": "Should be blocked",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_runtime_checks_endpoint_available(self) -> None:
        response = self.client.get(
            "/admin/runtime-checks",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("checks", payload)
        self.assertGreaterEqual(len(payload["checks"]), 1)

    def test_timeout_saved_response_matrix_allows_hero_action(self) -> None:
        session = SessionState(
            session_id="timeout-matrix-session",
            user_id=self.owner_user_id,
            villain_profile_id="tag",
            train_timer_seconds=30,
            scenario_id="srp_ip_btn_vs_bb",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_range_matrix_saved={},
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_matrix_saved={},
            villain_tokens_saved=["QQ"],
            hero_range_confirmed=True,
            villain_range_confirmed=True,
        )
        store.create_session(session.session_id, asdict(session))

        hand = HandState(
            hand_id="timeout-matrix-hand",
            session_id=session.session_id,
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh"],
            street=Street.FLOP,
            betting_round=BettingRoundState(
                current_bet=10.0,
                hero_contrib=0.0,
                villain_contrib=10.0,
                last_raise_size=10.0,
            ),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.MUST_FILL_RESPONSE_MATRIX,
            response_matrix_columns=["call", "raise"],
            response_matrix_saved={
                "street": "flop",
                "columns": ["call", "raise"],
                "row_order": ["SDV", "Value"],
                "selections": {
                    "SDV": {"call": "", "raise": ""},
                    "Value": {"call": "P", "raise": ""},
                },
                "complete": False,
                "allow_partial": True,
                "save_reason": "timer_expired",
            },
        )
        store.create_hand(hand.hand_id, asdict(hand))

        updated = apply_hero_action(
            hand_id=hand.hand_id,
            action="fold",
            iters=10,
        )

        self.assertTrue(updated.hand_over)
        self.assertEqual(updated.ui_gate, UIGate.HAND_OVER)

    def test_street_advance_keeps_previous_response_matrix_for_prune_display(self) -> None:
        saved_matrix = {
            "street": "flop",
            "columns": ["check", "bet_small", "bet_big"],
            "row_order": ["SDV", "Draw", "Value"],
            "selections": {
                "SDV": {"check": "P", "bet_small": "C", "bet_big": "F"},
                "Draw": {"check": "P", "bet_small": "C", "bet_big": "C"},
                "Value": {"check": "A", "bet_small": "C", "bet_big": "C"},
            },
            "complete": True,
            "allow_partial": False,
            "save_reason": "manual",
        }
        hand = HandState(
            hand_id="preserve-matrix-advance-hand",
            session_id="preserve-matrix-advance-session",
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh"],
            street=Street.FLOP,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.MUST_PRUNE_RANGE,
            response_matrix_columns=["check", "bet_small", "bet_big"],
            response_matrix_saved=saved_matrix,
        )

        _advance_to_next_street_after_prune(hand)

        self.assertEqual(hand.street, Street.TURN)
        self.assertEqual(hand.response_matrix_saved, saved_matrix)

    def test_new_response_matrix_node_clears_previous_street_answers(self) -> None:
        hand = HandState(
            hand_id="clear-previous-matrix-hand",
            session_id="clear-previous-matrix-session",
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_hand=("As", "Kh"),
            villain_hand=("Qd", "Qs"),
            board=["8c", "7c", "6s", "2d", "Ah"],
            street=Street.RIVER,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"KJs": [["Kc", "Jc"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.MUST_FILL_RESPONSE_MATRIX,
            response_matrix_columns=["check", "bet_small", "bet_big"],
            response_matrix_saved={
                "street": "turn",
                "columns": ["check", "bet_small", "bet_big"],
                "row_order": ["Draw", "Value"],
                "selections": {
                    "Draw": {"check": "P", "bet_small": "C", "bet_big": "C"},
                    "Value": {"check": "A", "bet_small": "C", "bet_big": "C"},
                },
                "complete": True,
                "allow_partial": False,
                "save_reason": "manual",
            },
        )

        prepare_response_matrix_for_new_node(hand, iters=10)

        self.assertEqual(hand.response_matrix_saved, {})

    def test_river_terminal_response_matrix_accepts_showdown_results(self) -> None:
        self._create_session_fixture(session_id="river-call-showdown-matrix-session", pot=80.0, hero_stack=80.0, villain_stack=100.0)
        call_hand = HandState(
            hand_id="river-call-showdown-matrix-hand",
            session_id="river-call-showdown-matrix-session",
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=80.0,
            hero_stack=80.0,
            villain_stack=80.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh", "8c", "9s"],
            street=Street.RIVER,
            betting_round=BettingRoundState(current_bet=20.0, hero_contrib=0.0, villain_contrib=20.0, last_raise_size=20.0),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.MUST_FILL_RESPONSE_MATRIX,
            response_matrix_columns=["call"],
        )
        store.create_hand(call_hand.hand_id, asdict(call_hand))

        saved_call = save_response_matrix(
            call_hand.hand_id,
            selections={"SDV": {"call": "W"}},
            row_order=["SDV"],
            iters=10,
        )
        self.assertEqual(saved_call.response_matrix_saved["selections"]["SDV"]["call"], "W")

        self._create_session_fixture(session_id="river-checkback-showdown-matrix-session", pot=80.0, hero_stack=80.0, villain_stack=80.0)
        checkback_hand = HandState(
            hand_id="river-checkback-showdown-matrix-hand",
            session_id="river-checkback-showdown-matrix-session",
            user_id=self.owner_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=80.0,
            hero_stack=80.0,
            villain_stack=80.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh", "8c", "9s"],
            street=Street.RIVER,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "KK", "QQ", "AKs", "AKo"],
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.MUST_FILL_RESPONSE_MATRIX,
            response_matrix_columns=["check"],
        )
        checkback_hand.history.append(
            ActionEvent(street=Street.RIVER, actor=Player.VILLAIN, action=ActionType.CHECK)
        )
        store.create_hand(checkback_hand.hand_id, asdict(checkback_hand))

        saved_checkback = save_response_matrix(
            checkback_hand.hand_id,
            selections={"SDV": {"check": "L"}},
            row_order=["SDV"],
            iters=10,
        )
        self.assertEqual(saved_checkback.response_matrix_saved["selections"]["SDV"]["check"], "L")

    def test_member_can_send_flagged_hand_to_coach_replay_queue(self) -> None:
        session = SessionState(
            session_id="review-session",
            user_id=self.member_user_id,
            villain_profile_id="tag",
            train_timer_seconds=30,
            scenario_id="srp_ip_btn_vs_bb",
            pot=20.0,
            hero_stack=100.0,
            villain_stack=100.0,
            hero_range_matrix_saved={"AA": True, "AKs": True},
            hero_tokens_saved=["AA", "AKs"],
            villain_range_matrix_saved={"QQ": True},
            villain_tokens_saved=["QQ"],
            hero_range_confirmed=True,
            villain_range_confirmed=True,
        )
        store.create_session(session.session_id, asdict(session))

        hand = HandState(
            hand_id="review-hand",
            session_id=session.session_id,
            user_id=self.member_user_id,
            scenario_id="srp_ip_btn_vs_bb",
            villain_profile_id="tag",
            pot=40.0,
            hero_stack=90.0,
            villain_stack=90.0,
            hero_hand=("Ah", "Kd"),
            villain_hand=("Qs", "Qd"),
            board=["2h", "4d", "Qh", "8c", "9s"],
            street=Street.RIVER,
            betting_round=BettingRoundState(),
            hero_tokens_saved=["AA", "AKs"],
            villain_range_matrix_saved={"QQ": True},
            villain_range_combos_live={"QQ": [["Qs", "Qd"]]},
            current_actor=Player.HERO,
            ui_gate=UIGate.HAND_OVER,
            hand_over=True,
        )
        store.create_hand(hand.hand_id, asdict(hand))

        flag_response = self.client.post(
            f"/results/hand/{hand.hand_id}/flag",
            headers={"Authorization": f"Bearer {self.member_token}"},
            json={"flagged": True},
        )
        self.assertEqual(flag_response.status_code, 200)
        self.assertTrue(flag_response.json()["review"]["flagged"])

        coach_note_response = self.client.patch(
            f"/results/hand/{hand.hand_id}/review",
            headers={"Authorization": f"Bearer {self.coach_token}"},
            json={"coach_note": "Review turn sizing with the member."},
        )
        self.assertEqual(coach_note_response.status_code, 200)
        self.assertEqual(coach_note_response.json()["review"]["coach_note"], "Review turn sizing with the member.")

        coach_queue_before = self.client.get(
            "/results/review-queue",
            headers={"Authorization": f"Bearer {self.coach_token}"},
        )
        self.assertEqual(coach_queue_before.status_code, 200)
        self.assertNotIn(hand.hand_id, {row["hand_id"] for row in coach_queue_before.json()["review_queue"]})

        send_response = self.client.post(
            "/results/review/send",
            headers={"Authorization": f"Bearer {self.member_token}"},
            json={},
        )
        self.assertEqual(send_response.status_code, 200)
        self.assertEqual(send_response.json()["sent_count"], 1)

        coach_queue_after = self.client.get(
            "/results/review-queue",
            headers={"Authorization": f"Bearer {self.coach_token}"},
        )
        self.assertEqual(coach_queue_after.status_code, 200)
        self.assertIn(hand.hand_id, {row["hand_id"] for row in coach_queue_after.json()["review_queue"]})

        replay_response = self.client.get(
            f"/results/hand/{hand.hand_id}/replay",
            headers={"Authorization": f"Bearer {self.coach_token}"},
        )
        self.assertEqual(replay_response.status_code, 200)
        replay = replay_response.json()
        self.assertEqual(replay["hand_id"], hand.hand_id)
        self.assertGreaterEqual(len(replay["steps"]), 3)


if __name__ == "__main__":
    unittest.main()
