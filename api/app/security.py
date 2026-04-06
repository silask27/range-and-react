from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from api.app.models.auth import UserAccount
from api.app.models.enums import UserRole
from api.app.services.auth_service import get_user_by_token


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid authorization header')
    return token.strip()


def get_current_user(authorization: str | None = Header(default=None)) -> UserAccount:
    token = _extract_bearer_token(authorization)
    return get_user_by_token(token)


def require_role(*roles: UserRole):
    def _dependency(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
        if current_user.role not in set(roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient permissions')
        return current_user

    return _dependency
