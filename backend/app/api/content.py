"""Mods, maps and Lua plugins for a server."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import audit, current_user, server_access
from ..db import get_db
from ..models import Server, User
from ..services import maps, mods, repo_beamng, server_config
from ..services.process_manager import manager

router = APIRouter(prefix="/api/servers/{server_id}", tags=["content"])


class Toggle(BaseModel):
    enabled: bool


class MapChoice(BaseModel):
    path: str


def _sdir(server: Server):
    return server_config.server_dir(server.id)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(404, f"Not found: {exc}")


@router.get("/mods")
def list_mods(server: Server = Depends(server_access("viewer"))):
    meta = repo_beamng.read_meta(_sdir(server))
    return [{**m, "source": meta.get(m["name"])} for m in mods.list_mods(_sdir(server))]


@router.post("/mods", status_code=201)
async def upload_mods(
    files: list[UploadFile],
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    saved = []
    for f in files:
        try:
            saved.append(await mods.upload_mod(_sdir(server), f))
        except ValueError as exc:
            raise HTTPException(422, f"{f.filename}: {exc}") from exc
    audit(db, user, "mod_upload", ", ".join(m["name"] for m in saved), server.id)
    return {"saved": saved, "restart_required": manager.get(server.id).running}


@router.patch("/mods/{name}")
def toggle_mod(
    name: str,
    body: Toggle,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        mods.set_mod_enabled(_sdir(server), name, body.enabled)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    audit(db, user, "mod_enable" if body.enabled else "mod_disable", name, server.id)
    return {"ok": True, "restart_required": manager.get(server.id).running}


@router.delete("/mods/{name}")
def delete_mod(
    name: str,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        mods.delete_mod(_sdir(server), name)
        repo_beamng.forget_mod(_sdir(server), name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    audit(db, user, "mod_delete", name, server.id)
    return {"ok": True}


@router.get("/maps")
def list_maps(server: Server = Depends(server_access("viewer"))):
    current = server_config.read_general(_sdir(server)).get("Map", "")
    return {"current": current, "maps": maps.list_maps(_sdir(server))}


@router.put("/maps")
def set_map(
    body: MapChoice,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    server_config.update_general(_sdir(server), {"Map": body.path})
    audit(db, user, "map_set", body.path, server.id)
    return {"ok": True, "restart_required": manager.get(server.id).running}


@router.get("/plugins")
def list_plugins(server: Server = Depends(server_access("viewer"))):
    return mods.list_plugins(_sdir(server))


@router.post("/plugins", status_code=201)
async def upload_plugin(
    file: UploadFile,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        name = await mods.upload_plugin(_sdir(server), file)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, user, "plugin_upload", name, server.id)
    return {"name": name}


@router.patch("/plugins/{name}")
def toggle_plugin(
    name: str,
    body: Toggle,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        mods.set_plugin_enabled(_sdir(server), name, body.enabled)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    audit(db, user, "plugin_enable" if body.enabled else "plugin_disable", name, server.id)
    return {"ok": True, "restart_required": manager.get(server.id).running}


@router.delete("/plugins/{name}")
def delete_plugin(
    name: str,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        mods.delete_plugin(_sdir(server), name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    audit(db, user, "plugin_delete", name, server.id)
    return {"ok": True}
