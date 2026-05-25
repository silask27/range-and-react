from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException, status

from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.storage.db import get_connection


_PLATFORM_ADMIN_ROLES = {UserRole.OWNER}


def is_platform_admin(user: UserAccount) -> bool:
    return user.role in _PLATFORM_ADMIN_ROLES


def _clean_ids(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or '').strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def list_user_organization_ids(user_id: str) -> list[str]:
    clean = str(user_id or '').strip()
    if not clean:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT organization_id FROM organization_memberships WHERE user_id = ? ORDER BY created_at ASC',
            (clean,),
        ).fetchall()
    return [str(row['organization_id']) for row in rows if row['organization_id']]



def list_users_in_organizations(organization_ids: Iterable[str]) -> list[str]:
    org_ids = _clean_ids(organization_ids)
    if not org_ids:
        return []
    placeholders = ', '.join('?' for _ in org_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f'SELECT DISTINCT user_id FROM organization_memberships WHERE organization_id IN ({placeholders}) ORDER BY user_id ASC',
            tuple(org_ids),
        ).fetchall()
    return [str(row['user_id']) for row in rows if row['user_id']]



def get_visible_organization_ids(user: UserAccount) -> list[str] | None:
    if is_platform_admin(user):
        return None
    return list_user_organization_ids(user.user_id)



def get_visible_user_ids(user: UserAccount) -> list[str] | None:
    if is_platform_admin(user):
        return None
    org_ids = list_user_organization_ids(user.user_id)
    user_ids = set(list_users_in_organizations(org_ids))
    user_ids.add(user.user_id)
    return sorted(user_ids)



def ensure_organization_access(user: UserAccount, organization_id: str) -> str:
    clean = str(organization_id or '').strip()
    if not clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='organization_id is required')
    visible = get_visible_organization_ids(user)
    if visible is not None and clean not in set(visible):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You do not have access to that organization')
    return clean



def ensure_user_access(user: UserAccount, target_user_id: str) -> str:
    clean = str(target_user_id or '').strip()
    if not clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='user_id is required')
    visible = get_visible_user_ids(user)
    if visible is not None and clean not in set(visible):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You do not have access to that user')
    return clean



def resolve_default_organization_id_for_user(user: UserAccount) -> str | None:
    org_ids = list_user_organization_ids(user.user_id)
    if len(org_ids) == 1:
        return org_ids[0]
    return None



def shared_organization_ids(user_a_id: str, user_b_id: str) -> list[str]:
    left = set(list_user_organization_ids(user_a_id))
    right = set(list_user_organization_ids(user_b_id))
    return sorted(left & right)
