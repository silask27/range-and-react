from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("VRT_DATABASE_PATH", str(Path("./data/regression_test.db").resolve()))
os.environ.setdefault("VRT_PASSWORD_RESET_RETURNS_TOKEN", "true")
os.environ.setdefault("VRT_REQUIRE_SIGNUP_INVITE", "true")
os.environ.setdefault("VRT_PUBLIC_STATUS_DETAILED_CHECKS", "false")
os.environ.setdefault("VRT_PUBLIC_STATUS_SHOW_DEMO_DETAILS", "false")

from fastapi.testclient import TestClient

from api.app.main import app
from api.app.storage.db import get_connection, init_db


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


    def test_login_route_returns_success(self) -> None:
        response = self.client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("token", payload)
        self.assertEqual(payload["user"]["email"], "owner@example.com")

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


if __name__ == "__main__":
    unittest.main()
