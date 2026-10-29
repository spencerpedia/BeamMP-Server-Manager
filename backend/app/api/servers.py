import asyncio
import shutil

import tomlkit
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ROLE_LEVEL, audit, can_access, current_user, require_admin, server_access
from ..db import get_db
from ..models import Server, ServerGrant, User
from ..services import backups, control, fsutil, jobs, maps, provision, scheduler, server_config, templates
from ..services.process_manager import manager

router = APIRouter(prefix="/api/servers", tags=["servers"])


class ServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    auth_key: str = ""
    port: int | None = None
    version: str = "latest"
    max_players: int = Field(8, ge=1, le=500)
    map: str | None = None
    template_id: str | None = None
    clone_from: int | None = None


class ServerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    port: int | None = None
    version: str | None = None
    autostart: bool | None = None
    auto_restart: bool | None = None
    backup_retention: int | None = Field(None, ge=0, le=1000)


class Command(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


class RawConfig(BaseModel):
    text: str


def server_out(server: Server, user: User | None = None, db: Session | None = None) -> dict:
    sp = manager.get(server.id)
    general = {}
    try:
        general = server_config.read_general(server_config.server_dir(server.id))
    except Exception:  # noqa: BLE001  (a broken config shouldn't hide the server)
        pass
    out = {
        "id": server.id,
        "name": server.name,
        "port": server.port,
        "version": server.version,
        "autostart": server.autostart,
        "auto_restart": server.auto_restart,
        "backup_retention": server.backup_retention,
        "created_at": server.created_at.isoformat(),
        "max_players": general.get("MaxPlayers"),
        "map": maps.level_from_path(general.get("Map", "")),
        "has_auth_key": bool(general.get("AuthKey")),
        "provisioning": server.id in provision.busy,
        **sp.summary(),
    }
    if user is not None and db is not None:
        out["can_control"] = can_access(user, server.id, "operator", db)
    return out


def _port_error(exc: provision.PortError) -> HTTPException:
    return HTTPException(409 if "already used" in str(exc) or "No free ports" in str(exc) else 422, str(exc))


@router.get("")
def list_servers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    servers = db.scalars(select(Server).order_by(Server.id)).all()
    if user.role != "admin":
        allowed = set(db.scalars(select(ServerGrant.server_id).where(ServerGrant.user_id == user.id)))
        servers = [s for s in servers if s.id in allowed]
    return [server_out(s, user, db) for s in servers]


@router.post("", status_code=201)
async def create_server(body: ServerCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Creates a blank server, or one seeded from a template or an existing server (copied in a background job)."""
    source_server = db.get(Server, body.clone_from) if body.clone_from else None
    if body.clone_from and source_server is None:
        raise HTTPException(404, "Server to clone not found")
    template_meta = None
    if body.template_id:
        try:
            _, template_meta = templates.load(body.template_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Template not found") from exc
    settings = {}
    version = body.version
    if template_meta:
        tset = template_meta.get("settings", {})
        settings = {k: tset[k] for k in ("auto_restart", "backup_retention") if k in tset}
        if body.version == "latest" and tset.get("version"):
            version = tset["version"]
    elif source_server:
        settings = {"auto_restart": source_server.auto_restart, "backup_retention": source_server.backup_retention}
        version = source_server.version if body.version == "latest" else body.version
    try:
        server = provision.create_record(db, body.name, body.port, version, body.auth_key, **settings)
    except provision.PortError as exc:
        raise _port_error(exc) from exc
    sdir = server_config.server_dir(server.id)
    if not (template_meta or source_server):
        extra = {"MaxPlayers": body.max_players}
        if body.map:
            extra["Map"] = body.map
        server_config.update_general(sdir, extra)
        audit(db, user, "server_create", f"{server.name} on port {server.port}", server.id)
        return server_out(server, user, db)

    auth_key = body.auth_key.strip()
    label = f"template '{template_meta['name']}'" if template_meta else f"server '{source_server.name}'"

    async def seed(job):
        def progress(frac, done, total):
            job.update(progress=frac, message=f"Copying {done // 2**20}/{total // 2**20} MB from {label}")

        provision.busy.add(server.id)
        try:
            if template_meta:
                await asyncio.to_thread(templates.apply, body.template_id, sdir, progress)
            else:
                src = server_config.server_dir(source_server.id)
                copier = fsutil.Copier(provision.content_size(src), progress)
                await asyncio.to_thread(provision.copy_content, src, sdir, copier)
                server_config.apply_tables(sdir, provision.portable_config(src, include_auth_key=True))
            if auth_key:
                server_config.update_general(sdir, {"AuthKey": auth_key})
            server_config.update_general(sdir, {"Name": server.name})
        finally:
            provision.busy.discard(server.id)
        return {"server_id": server.id}

    provision.busy.add(server.id)
    job = jobs.start("create", f"Creating {server.name} from {label}", user.username, seed, server.id)
    audit(db, user, "server_create", f"{server.name} on port {server.port} from {label}", server.id)
    return {**server_out(server, user, db), "job": job.out()}


@router.get("/{server_id}")
def get_server(
    server: Server = Depends(server_access("viewer")), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return server_out(server, user, db)


@router.patch("/{server_id}")
def update_server(
    body: ServerUpdate,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    changes = body.model_dump(exclude_none=True)
    if "port" in changes and changes["port"] != server.port:
        if manager.get(server.id).running:
            raise HTTPException(409, "Stop the server before changing its port")
        try:
            provision.check_port(db, changes["port"], server.id)
        except provision.PortError as exc:
            raise _port_error(exc) from exc
    for key, value in changes.items():
        setattr(server, key, value)
    db.commit()
    if "name" in changes:
        server_config.update_general(server_config.server_dir(server.id), {"Name": server.name})
    audit(db, user, "server_update", ", ".join(f"{k}={v}" for k, v in changes.items()), server.id)
    return server_out(server, user, db)


@router.delete("/{server_id}")
async def delete_server(
    server_id: int, delete_backups: bool = False, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(404, "Server not found")
    await manager.forget(server_id)
    for sched in server.schedules:
        scheduler.remove_job(sched.id)
    name = server.name
    db.delete(server)
    db.commit()
    await asyncio.to_thread(shutil.rmtree, server_config.server_dir(server_id), True)
    if delete_backups:
        await asyncio.to_thread(shutil.rmtree, backups.backup_dir(server_id), True)
    audit(db, user, "server_delete", name, server_id)
    return {"ok": True}


# ---- lifecycle -----------------------------------------------------------------------------


async def _action(server: Server, user: User, db: Session, action: str) -> dict:
    if server.id in provision.busy:
        raise HTTPException(409, "This server's files are still being copied")
    if action in ("start", "restart") and not server_config.read_general(server_config.server_dir(server.id)).get(
        "AuthKey"
    ):
        raise HTTPException(422, "Set an Auth Key in the server config first (keymaster.beammp.com)")
    try:
        await getattr(control, action)(server.id)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    audit(db, user, f"server_{action}", "", server.id)
    return server_out(server, user, db)


@router.post("/{server_id}/start")
async def start_server(
    server: Server = Depends(server_access("operator")), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return await _action(server, user, db, "start")


@router.post("/{server_id}/stop")
async def stop_server(
    server: Server = Depends(server_access("operator")), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return await _action(server, user, db, "stop")


@router.post("/{server_id}/restart")
async def restart_server(
    server: Server = Depends(server_access("operator")), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return await _action(server, user, db, "restart")


@router.post("/{server_id}/kill")
async def kill_server(
    server: Server = Depends(server_access("operator")), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    sp = manager.get(server.id)
    if sp.proc is not None and sp.proc.returncode is None:
        sp.state = "stopping"
        sp.proc.kill()
    audit(db, user, "server_kill", "", server.id)
    return {"ok": True}


# ---- console -------------------------------------------------------------------------------


@router.get("/{server_id}/console")
def console_history(server: Server = Depends(server_access("viewer"))):
    return {"lines": list(manager.get(server.id).log)}


@router.post("/{server_id}/console")
async def console_command(
    body: Command,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        await manager.get(server.id).send(body.command)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit(db, user, "console", body.command[:200], server.id)
    return {"ok": True}


@router.get("/{server_id}/stats")
def stats_history(server: Server = Depends(server_access("viewer"))):
    return {"points": list(manager.get(server.id).stats)}


# ---- config --------------------------------------------------------------------------------


@router.get("/{server_id}/config")
def get_config(server: Server = Depends(server_access("viewer")), user: User = Depends(current_user)):
    values = server_config.read_general(server_config.server_dir(server.id))
    # Only operators and admins see the auth key.
    if ROLE_LEVEL[user.role] < ROLE_LEVEL["operator"] and values.get("AuthKey"):
        values["AuthKey"] = "********"
    return {"fields": server_config.FIELDS, "values": values, "managed": sorted(server_config.MANAGED_KEYS)}


@router.put("/{server_id}/config")
def put_config(
    values: dict,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        result = server_config.update_general(server_config.server_dir(server.id), values)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if "Name" in values and values["Name"] and values["Name"] != server.name:
        server.name = str(values["Name"])[:128]
        db.commit()
    audit(db, user, "config_update", ", ".join(k for k in values if k != "AuthKey") or "AuthKey", server.id)
    return {"values": result, "restart_required": manager.get(server.id).running}


@router.get("/{server_id}/config/raw")
def get_raw_config(server: Server = Depends(server_access("operator"))):
    return {"text": server_config.read_raw(server_config.server_dir(server.id))}


@router.put("/{server_id}/config/raw")
def put_raw_config(
    body: RawConfig,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        server_config.write_raw(server_config.server_dir(server.id), body.text)
    except (tomlkit.exceptions.ParseError, ValueError) as exc:
        raise HTTPException(422, f"Invalid TOML: {exc}") from exc
    audit(db, user, "config_raw_update", "", server.id)
    return {"ok": True, "restart_required": manager.get(server.id).running}
