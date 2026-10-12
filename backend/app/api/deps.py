"""Dependency xác thực: đọc Bearer token → session + user còn hiệu lực."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DatabaseSession

from app.core.security import AuthError, decode_access_token
from app.db.session import get_db
from app.models.session import UserSession
from app.models.user import User
from app.services import auth_service

# auto_error=False để tự raise AuthError (thống nhất message tiếng Việt)
_bearer_scheme = HTTPBearer(auto_error=False)

# Alias dùng chung cho các endpoint
DbSession = Annotated[DatabaseSession, Depends(get_db)]


def get_current_session_and_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: DbSession,
) -> tuple[UserSession, User]:
    if credentials is None:
        raise AuthError("Chưa đăng nhập")
    payload = decode_access_token(credentials.credentials)
    return auth_service.load_session_and_user(db, payload)


CurrentUser = Annotated[tuple[UserSession, User], Depends(get_current_session_and_user)]
