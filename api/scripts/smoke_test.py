from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("VRT_DATABASE_PATH", str(Path("./data/smoke_test.db").resolve()))
os.environ.setdefault("VRT_PASSWORD_RESET_RETURNS_TOKEN", "true")
os.environ.setdefault("VRT_REQUIRE_SIGNUP_INVITE", "true")

from api.app.main import app
from api.app.storage.db import get_connection, init_db


def _assert_ok(response, label: str) -> None:
    if response.status_code >= 400:
        raise SystemExit(f"{label} failed: {response.status_code} {response.text}")


def main() -> None:
    db_path = Path(os.environ["VRT_DATABASE_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    init_db()
    client = TestClient(app)

    live = client.get("/livez")
    _assert_ok(live, "livez")

    health = client.get("/healthz")
    _assert_ok(health, "health")

    ready = client.get("/readyz")
    _assert_ok(ready, "readyz")
    if "checks" not in ready.json():
        raise SystemExit("readyz failed: missing detailed checks payload")

    public_config = client.get("/platform/public-config")
    _assert_ok(public_config, "public config")

    owner_exists = client.get("/auth/owner-exists")
    _assert_ok(owner_exists, "owner exists")

    bootstrap = client.post(
        "/auth/bootstrap-owner",
        json={"email": "owner@example.com", "password": "Password123!", "display_name": "Owner"},
    )
    _assert_ok(bootstrap, "bootstrap owner")
    owner_token = bootstrap.json()["token"]

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO organizations (
                organization_id, name, slug, external_provider, external_org_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, '{}', datetime('now'), datetime('now'))
            """,
            ("org-smoke", "Smoke Org", "smoke-org"),
        )
        conn.execute(
            """
            INSERT INTO organization_memberships (
                organization_membership_id, organization_id, user_id, membership_role, created_at
            ) VALUES (?, ?, ?, ?, datetime('now'))
            """,
            ("org-mem-smoke", "org-smoke", bootstrap.json()["user"]["user_id"], "owner"),
        )

    invite_create = client.post(
        "/admin/signup-invites",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "member@example.com", "role": "member", "organization_id": "org-smoke", "membership_role": "member"},
    )
    _assert_ok(invite_create, "create invite")
    invite = invite_create.json()["invite"]

    invite_preview = client.get(f"/auth/signup-invites/{invite['invite_code']}")
    _assert_ok(invite_preview, "invite preview")

    signup = client.post(
        "/auth/signup",
        json={
            "email": "member@example.com",
            "password": "Password123!",
            "display_name": "Member",
            "invite_code": invite["invite_code"],
        },
    )
    _assert_ok(signup, "invite signup")

    reset_request = client.post("/auth/request-password-reset", json={"email": "member@example.com"})
    _assert_ok(reset_request, "request password reset")
    reset_token = reset_request.json().get("reset_token")
    if not reset_token:
        raise SystemExit("request password reset failed: missing reset_token in smoke mode")

    reset_complete = client.post(
        "/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "NewPassword123!"},
    )
    _assert_ok(reset_complete, "reset password")

    login = client.post("/auth/login", json={"email": "member@example.com", "password": "NewPassword123!"})
    _assert_ok(login, "login after reset")

    print("Smoke test passed.")


if __name__ == "__main__":
    main()
