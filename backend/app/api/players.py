from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, current_user, server_access
from ..db import get_db
from ..models import Ban, Server, User
from ..services import control
from ..services.process_manager import manager

router = APIRouter(prefix="/api/servers/{server_id}", tags=["players"])


class Kick(BaseModel):
    reason: str = Field("", max_length=200)


class BanCreate(BaseModel):
    name: str = Field("", max_length=64)
    beammp_id: str = Field("", max_length=32)
    ip: str = Field("", max_length=64)
    reason: str = Field("", max_length=200)


def ban_out(b: Ban) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "beammp_id": b.beammp_id,
        "ip": b.ip,
        "reason": b.reason,
        "created_by": b.created_by,
        "created_at": b.created_at.isoformat(),
    }


@router.get("/players")
def players(server: Server = Depends(server_access("viewer"))):
    return manager.get(server.id).players


@router.post("/players/{player_id}/kick")
async def kick(
    player_id: int,
    body: Kick,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    sp = manager.get(server.id)
    player = next((p for p in sp.players if p.get("id") == player_id), None)
    if player is None:
        raise HTTPException(404, "Player is not online")
    try:
        await sp.send(f"bmsm kick {player_id} {body.reason}".strip())
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    sp.system_log(f"{user.username} kicked {player.get('name')}" + (f": {body.reason}" if body.reason else ""))
    audit(db, user, "kick", f"{player.get('name')} {body.reason}".strip(), server.id)
    return {"ok": True}


@router.get("/chat")
def chat(server: Server = Depends(server_access("viewer"))):
    return list(manager.get(server.id).chat)


@router.get("/bans")
def list_bans(server: Server = Depends(server_access("viewer")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Ban).where(Ban.server_id == server.id).order_by(Ban.created_at.desc()))
    return [ban_out(b) for b in rows]


@router.post("/bans", status_code=201)
def add_ban(
    body: BanCreate,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not (body.name.strip() or body.beammp_id.strip() or body.ip.strip()):
        raise HTTPException(422, "Give a name, BeamMP ID or IP to ban")
    ban = Ban(
        server_id=server.id,
        name=body.name.strip(),
        beammp_id=body.beammp_id.strip(),
        ip=body.ip.strip(),
        reason=body.reason.strip(),
        created_by=user.username,
    )
    db.add(ban)
    db.commit()
    control.sync_bans(server.id)
    audit(db, user, "ban", body.name or body.beammp_id or body.ip, server.id)
    return ban_out(ban)


@router.delete("/bans/{ban_id}")
def remove_ban(
    ban_id: int,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ban = db.get(Ban, ban_id)
    if ban is None or ban.server_id != server.id:
        raise HTTPException(404, "Ban not found")
    label = ban.name or ban.beammp_id or ban.ip
    db.delete(ban)
    db.commit()
    control.sync_bans(server.id)
    audit(db, user, "unban", label, server.id)
    return {"ok": True}
