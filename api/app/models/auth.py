from __future__ import annotations

from dataclasses import dataclass

from api.app.models.enums import UserRole


@dataclass
class UserAccount:
    user_id: str
    email: str
    display_name: str | None
    role: UserRole
    is_active: bool = True


@dataclass
class AuthSession:
    token: str
    user: UserAccount
