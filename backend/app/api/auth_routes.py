from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..auth import COOKIE_NAME, audit, current_user, hash_password, issue_token, verify_password
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


def user_out(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


def _set_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        issue_token(user),
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        max_age=config.TOKEN_TTL_HOURS * 3600,
    )


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    return {"needs_setup": db.scalar(select(func.count(User.id))) == 0}


@router.post("/setup")
def setup(body: Credentials, response: Response, db: Session = Depends(get_db)):
    """Creates the first admin account. Only works while no users exist."""
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "Setup already done")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    user = User(username=body.username.strip(), password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.commit()
    audit(db, user, "setup", "created first admin")
    _set_cookie(response, user)
    return user_out(user)


@router.post("/login")
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    _set_cookie(response, user)
    audit(db, user, "login")
    return user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/password")
def change_password(
    body: PasswordChange, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "Current password is wrong")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    audit(db, user, "password_change")
    _set_cookie(response, user)
    return {"ok": True}
