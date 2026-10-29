"""tar.gz backups of a server's directory, stored under BACKUP_DIR/<server_id>/."""

import re
import shutil
import tarfile
import time
from datetime import datetime
from pathlib import Path

from .. import config
from . import server_config

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.tar\.gz$")


def backup_dir(server_id: int) -> Path:
    return config.BACKUP_DIR / str(server_id)


def backup_path(server_id: int, name: str) -> Path:
    if not _NAME_RE.match(name):
        raise ValueError("Invalid backup name")
    path = backup_dir(server_id) / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def list_backups(server_id: int) -> list[dict]:
    folder = backup_dir(server_id)
    if not folder.exists():
        return []
    items = []
    for p in folder.glob("*.tar.gz"):
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "created": int(st.st_mtime)})
    return sorted(items, key=lambda b: b["created"], reverse=True)


def create_backup(server_id: int, label: str = "manual") -> dict:
    """Blocking; call from a worker thread."""
    src = server_config.server_dir(server_id)
    folder = backup_dir(server_id)
    folder.mkdir(parents=True, exist_ok=True)
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", label)[:32] or "backup"
    name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{label}.tar.gz"
    tmp = folder / (name + ".part")
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(src, arcname=".")
    final = folder / name
    tmp.replace(final)
    return {"name": name, "size": final.stat().st_size, "created": int(time.time())}


def prune(server_id: int, keep: int) -> list[str]:
    if keep <= 0:
        return []
    removed = []
    for b in list_backups(server_id)[keep:]:
        (backup_dir(server_id) / b["name"]).unlink(missing_ok=True)
        removed.append(b["name"])
    return removed


def restore_backup(server_id: int, name: str) -> None:
    """Blocking. The server must be stopped. The current directory is kept until extraction succeeds."""
    archive = backup_path(server_id, name)
    target = server_config.server_dir(server_id)
    staging = target.with_name(f"{target.name}.restore")
    old = target.with_name(f"{target.name}.old")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(staging, filter="data")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    staging.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def delete_backup(server_id: int, name: str) -> None:
    backup_path(server_id, name).unlink()
