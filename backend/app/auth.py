from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import SessionLocal, get_db
from .models import AuditLog, Server, ServerGrant, User

COOKIE_NAME = "bmsm_session"
ROLE_LEVEL = {"viewer": 1, "operator": 2, "admin": 3}

_hasher = PasswordHasher()
_SECRET = None


def _secret() -> str:
    global _SECRET
    if _SECRET is None:
        _SECRET = config.secret_key()
    return _SECRET


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


def issue_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_TTL_HOURS)
    # pwh lets a password change invalidate existing sessions.
    return jwt.encode({"sub": str(user.id), "pwh": user.password_hash[-12:], "exp": exp}, _secret(), algorithm="HS256")


def _user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(claims["sub"]))
    if user is None or user.password_hash[-12:] != claims.get("pwh"):
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_token(request.cookies.get(COOKIE_NAME), db)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


def ws_user(websocket: WebSocket) -> User | None:
    with SessionLocal() as db:
        return _user_from_token(websocket.cookies.get(COOKIE_NAME), db)


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def can_access(user: User, server_id: int, level: str, db: Session) -> bool:
    if user.role == "admin":
        return True
    if ROLE_LEVEL[user.role] < ROLE_LEVEL[level]:
        return False
    grant = db.scalar(select(ServerGrant).where(ServerGrant.user_id == user.id, ServerGrant.server_id == server_id))
    return grant is not None


def server_access(level: str):
    """Dependency factory: resolves {server_id} and checks the user's access level on it."""

    def dep(server_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Server:
        server = db.get(Server, server_id)
        if server is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found")
        if not can_access(user, server_id, level, db):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this server")
        return server

    return dep


def audit(db: Session, user: User | str | None, action: str, detail: str = "", server_id: int | None = None) -> None:
    username = user.username if isinstance(user, User) else (user or "system")
    db.add(AuditLog(username=username, action=action, detail=detail, server_id=server_id))
    db.commit()
