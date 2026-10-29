"""Server lifecycle actions shared by the API and the scheduler."""

import asyncio

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Ban, Server
from . import backups, bridge, server_config
from .process_manager import LaunchSpec, manager


def ban_entries(db, server_id: int) -> list[dict]:
    rows = db.scalars(select(Ban).where(Ban.server_id == server_id))
    return [{"name": b.name, "beammp": b.beammp_id, "ip": b.ip, "reason": b.reason} for b in rows]


def launch_spec(server_id: int) -> LaunchSpec | None:
    with SessionLocal() as db:
        server = db.get(Server, server_id)
        if server is None:
            return None
        return LaunchSpec(
            server_id=server.id,
            port=server.port,
            version=server.version,
            auto_restart=server.auto_restart,
            bans=ban_entries(db, server.id),
        )


def sync_bans(server_id: int) -> None:
    """Rewrites the ban file and, if running, kicks any banned players who are online."""
    with SessionLocal() as db:
        entries = ban_entries(db, server_id)
    bridge.write_bans(server_config.server_dir(server_id), entries)
    sp = manager.get(server_id)
    if sp.running:
        asyncio.create_task(sp.send("bmsm enforcebans"))


async def start(server_id: int) -> None:
    spec = launch_spec(server_id)
    if spec is None:
        raise LookupError("Server not found")
    await manager.get(server_id).start(spec)


async def stop(server_id: int) -> None:
    await manager.get(server_id).stop()


async def restart(server_id: int) -> None:
    spec = launch_spec(server_id)
    if spec is None:
        raise LookupError("Server not found")
    await manager.get(server_id).restart(spec)


async def warn_players(server_id: int, minutes: int, what: str) -> None:
    """Counts down in chat before a disruptive action. Returns immediately if nobody is online."""
    sp = manager.get(server_id)
    if minutes <= 0 or not sp.running or not sp.players:
        return
    seconds = minutes * 60
    marks = sorted({m * 60 for m in (minutes, 10, 5, 1) if m <= minutes} | {30, 10}, reverse=True)
    elapsed_target = 0
    for mark in marks:
        await asyncio.sleep(max(0, (seconds - mark) - elapsed_target))
        elapsed_target = seconds - mark
        if not sp.running:
            return
        if not sp.players:
            continue
        label = f"{mark // 60} minute{'s' if mark >= 120 else ''}" if mark >= 60 else f"{mark} seconds"
        await sp.send(f"say Server {what} in {label}")
    await asyncio.sleep(max(0, seconds - elapsed_target))


async def backup(server_id: int, label: str = "manual") -> dict:
    result = await asyncio.to_thread(backups.create_backup, server_id, label)
    with SessionLocal() as db:
        server = db.get(Server, server_id)
        keep = server.backup_retention if server else 0
    await asyncio.to_thread(backups.prune, server_id, keep)
    return result
