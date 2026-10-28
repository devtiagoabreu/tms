"""Dependências de autenticação."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from tms.app.deps.db import get_db
from tms.core.auth import verify_session_token
from tms.models.auth import User, UserRole

SESSION_COOKIE_NAME = "tms_session"


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    uid = verify_session_token(token)
    if not uid:
        return None
    user = db.get(User, uid)
    if not user or not user.is_active:
        return None
    request.state.user = user
    return user


async def require_user(
    request: Request,
    user: Annotated[Optional[User], Depends(get_current_user)],
) -> User:
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    request.state.user = user
    return user


def require_roles(*roles: UserRole):
    async def _checker(user: Annotated[User, Depends(require_user)]) -> User:
        if user.role not in roles:
            return RedirectResponse(url="/", status_code=303)
        return user

    return _checker


CurrentUser = Annotated[User, Depends(require_user)]
DbSession = Annotated[Session, Depends(get_db)]
