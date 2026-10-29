"""Users, BeamMP versions and the audit log (admin only, except reads noted below)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..auth import ROLE_LEVEL, audit, current_user, hash_password, require_admin
from ..db import get_db
from ..models import AuditLog, Server, ServerGrant, User
from ..services import releases
from ..services.process_manager import manager

router = APIRouter(prefix="/api", tags=["admin"])


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: str = "viewer"
    server_ids: list[int] = []


class UserUpdate(BaseModel):
    password: str | None = Field(None, min_length=8, max_length=256)
    role: str | None = None
    server_ids: list[int] | None = None


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "server_ids": [g.server_id for g in u.grants],
        "created_at": u.created_at.isoformat(),
    }


def _check_role(role: str) -> None:
    if role not in ROLE_LEVEL:
        raise HTTPException(422, f"Role must be one of {', '.join(ROLE_LEVEL)}")


def _set_grants(db: Session, user: User, server_ids: list[int]) -> None:
    valid = set(db.scalars(select(Server.id).where(Server.id.in_(server_ids))))
    user.grants = [g for g in user.grants if g.server_id in valid]
    have = {g.server_id for g in user.grants}
    for sid in valid - have:
        user.grants.append(ServerGrant(server_id=sid))


# ---- users ---------------------------------------------------------------------------------


@router.get("/users")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_role(body.role)
    if db.scalar(select(User).where(User.username == body.username.strip())):
        raise HTTPException(409, "Username already taken")
    user = User(username=body.username.strip(), password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    _set_grants(db, user, body.server_ids)
    db.commit()
    audit(db, admin, "user_create", f"{user.username} ({user.role})")
    return user_out(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if body.role is not None:
        _check_role(body.role)
        if user.role == "admin" and body.role != "admin" and _admin_count(db) <= 1:
            raise HTTPException(409, "Can't demote the last admin")
        user.role = body.role
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.server_ids is not None:
        _set_grants(db, user, body.server_ids)
    db.commit()
    audit(db, admin, "user_update", user.username)
    return user_out(user)


def _admin_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(409, "You can't delete yourself")
    db.delete(user)
    db.commit()
    audit(db, admin, "user_delete", user.username)
    return {"ok": True}


# ---- BeamMP versions -----------------------------------------------------------------------


@router.get("/versions")
async def versions(refresh: bool = False, _: User = Depends(current_user), db: Session = Depends(get_db)):
    installed = releases.installed_versions()
    try:
        available = await releases.list_releases(force=refresh)
        error = None
    except httpx.HTTPError as exc:
        available, error = [], str(exc)
    in_use = {sp.version for sp in manager.servers.values() if sp.running}
    pinned = set(db.scalars(select(Server.version)))
    return {
        "asset": config.BEAMMP_ASSET,
        "latest": available[0]["tag"] if available else (installed[0] if installed else None),
        "installed": [{"tag": t, "in_use": t in in_use, "pinned": t in pinned} for t in installed],
        "available": available,
        "error": error,
    }


@router.post("/versions/{tag}")
async def install_version(tag: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        path = await releases.ensure_binary(tag)
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        raise HTTPException(502, f"Download failed: {exc}") from exc
    audit(db, admin, "version_install", path.parent.name)
    return {"tag": path.parent.name}


@router.delete("/versions/{tag}")
def delete_version(tag: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if any(sp.version == tag and sp.running for sp in manager.servers.values()):
        raise HTTPException(409, "That version is running on a server")
    if db.scalar(select(Server).where(Server.version == tag)):
        raise HTTPException(409, "A server is pinned to that version")
    try:
        releases.remove_version(tag)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, admin, "version_delete", tag)
    return {"ok": True}


# ---- audit log & system --------------------------------------------------------------------


@router.get("/audit")
def audit_log(
    limit: int = 200,
    server_id: int | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
    if server_id is not None:
        q = q.where(AuditLog.server_id == server_id)
    return [
        {
            "id": a.id,
            "ts": a.ts.isoformat(),
            "username": a.username,
            "server_id": a.server_id,
            "action": a.action,
            "detail": a.detail,
        }
        for a in db.scalars(q)
    ]


@router.get("/system")
def system_info(_: User = Depends(current_user)):
    lo, hi = config.GAME_PORT_RANGE
    return {"port_range": [lo, hi], "asset": config.BEAMMP_ASSET}
