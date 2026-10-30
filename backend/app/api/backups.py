import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import audit, current_user, server_access
from ..db import get_db
from ..models import Server, User
from ..services import backups, control
from ..services.process_manager import manager

router = APIRouter(prefix="/api/servers/{server_id}/backups", tags=["backups"])
_busy: set[int] = set()


class BackupCreate(BaseModel):
    label: str = Field("manual", max_length=32)


def _path_or_404(server_id: int, name: str):
    try:
        return backups.backup_path(server_id, name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "Backup not found") from exc


@router.get("")
def list_backups(server: Server = Depends(server_access("viewer"))):
    return {"backups": backups.list_backups(server.id), "busy": server.id in _busy}


@router.post("", status_code=201)
async def create_backup(
    body: BackupCreate,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if server.id in _busy:
        raise HTTPException(409, "A backup or restore is already running for this server")
    _busy.add(server.id)
    try:
        result = await control.backup(server.id, body.label)
    finally:
        _busy.discard(server.id)
    manager.get(server.id).publish({"type": "notify", "event": "backup", "name": result["name"], "user": user.username})
    audit(db, user, "backup_create", result["name"], server.id)
    return result


@router.get("/{name}")
def download_backup(name: str, server: Server = Depends(server_access("operator"))):
    path = _path_or_404(server.id, name)
    return FileResponse(path, filename=name, media_type="application/gzip")


@router.post("/{name}/restore")
async def restore_backup(
    name: str,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _path_or_404(server.id, name)
    if manager.get(server.id).running:
        raise HTTPException(409, "Stop the server before restoring a backup")
    if server.id in _busy:
        raise HTTPException(409, "A backup or restore is already running for this server")
    _busy.add(server.id)
    try:
        await asyncio.to_thread(backups.restore_backup, server.id, name)
    finally:
        _busy.discard(server.id)
    manager.get(server.id).system_log(f"Restored backup {name}")
    manager.get(server.id).publish({"type": "notify", "event": "restore", "name": name, "user": user.username})
    audit(db, user, "backup_restore", name, server.id)
    return {"ok": True}


@router.delete("/{name}")
def delete_backup(
    name: str,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _path_or_404(server.id, name)
    backups.delete_backup(server.id, name)
    audit(db, user, "backup_delete", name, server.id)
    return {"ok": True}
