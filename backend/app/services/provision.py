"""Creating server records and copying server content (used by create, clone, templates and import)."""

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models import Server
from . import bridge, fsutil, server_config


busy: set[int] = set()  # server ids whose files are still being copied in; they can't be started yet


class PortError(ValueError):
    pass


def check_port(db: Session, port: int, exclude_id: int | None = None) -> None:
    lo, hi = config.GAME_PORT_RANGE
    if not lo <= port <= hi:
        raise PortError(f"Port must be within the published range {lo}-{hi}")
    clash = db.scalar(select(Server).where(Server.port == port, Server.id != (exclude_id or -1)))
    if clash:
        raise PortError(f"Port {port} is already used by '{clash.name}'")


def next_free_port(db: Session, preferred: int | None = None) -> int:
    used = set(db.scalars(select(Server.port)))
    lo, hi = config.GAME_PORT_RANGE
    if preferred and lo <= preferred <= hi and preferred not in used:
        return preferred
    for port in range(lo, hi + 1):
        if port not in used:
            return port
    raise PortError(f"No free ports left in {lo}-{hi}. Widen GAME_PORT_RANGE and publish more ports.")


def create_record(db: Session, name: str, port: int | None, version: str = "latest", auth_key: str = "", **settings) -> Server:
    port = port or next_free_port(db)
    check_port(db, port)
    server = Server(name=name.strip()[:128], port=port, version=version or "latest", **settings)
    db.add(server)
    db.commit()
    sdir = server_config.server_dir(server.id)
    shutil.rmtree(sdir, ignore_errors=True)  # leftovers from a deleted server with a reused id
    server_config.create_default(sdir, server.name, port, auth_key.strip())
    return server


# Which folders make up a server's content, and how they're named in other layouts.
CONTENT_DIRS = ("Client", "Client.disabled", "Server", "Server.disabled")


def _skip_content(path: Path) -> bool:
    return path.name in (bridge.PLUGIN_NAME, "mods.json") or path.name.endswith((".part", ".upload"))


def content_size(server_dir: Path) -> int:
    return fsutil.tree_size(server_dir / "Resources" / d for d in CONTENT_DIRS)


def copy_content(src_dir: Path, dst_dir: Path, copier: fsutil.Copier) -> None:
    """Copies Resources/{Client,Server}[.disabled] from one manager-layout directory to another."""
    for d in CONTENT_DIRS:
        src = src_dir / "Resources" / d
        if src.is_dir():
            copier.tree(src, dst_dir / "Resources" / d, skip=_skip_content)


def portable_config(server_dir: Path, include_auth_key: bool) -> dict:
    tables = server_config.read_tables(server_dir)
    general = tables.get("General", {})
    for key in ("Port", "ResourceFolder", "Name", "IP"):
        general.pop(key, None)
    if not include_auth_key:
        general.pop("AuthKey", None)
    return tables
