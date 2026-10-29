"""Server templates: a saved config + mods + plugins that new servers can start from.

Stored as /data/templates/<id>/template.json plus a Resources/ tree in the same layout as a server.
"""

import json
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .. import config
from . import fsutil, provision, server_config

TEMPLATES_DIR = config.DATA_DIR / "templates"
META = "template.json"
_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _dir(template_id: str) -> Path:
    if not _ID_RE.match(template_id):
        raise FileNotFoundError(template_id)
    path = TEMPLATES_DIR / template_id
    if not (path / META).is_file():
        raise FileNotFoundError(template_id)
    return path


def _counts(root: Path) -> dict:
    res = root / "Resources"
    return {
        "mods": sum(len(list((res / d).glob("*.zip"))) for d in ("Client", "Client.disabled") if (res / d).is_dir()),
        "plugins": sum(sum(1 for p in (res / d).iterdir() if p.is_dir()) for d in ("Server", "Server.disabled") if (res / d).is_dir()),
        "size": provision.content_size(root),
    }


def _out(path: Path) -> dict:
    meta = json.loads((path / META).read_text())
    general = meta.get("config", {}).get("General", {})
    return {
        "id": path.name,
        "name": meta.get("name", path.name),
        "description": meta.get("description", ""),
        "created": meta.get("created"),
        "source": meta.get("source", ""),
        "includes_auth_key": bool(general.get("AuthKey")),
        "map": general.get("Map", ""),
        "max_players": general.get("MaxPlayers"),
        "settings": meta.get("settings", {}),
        **meta.get("counts", {}),
    }


def list_templates() -> list[dict]:
    if not TEMPLATES_DIR.is_dir():
        return []
    items = []
    for p in TEMPLATES_DIR.iterdir():
        if (p / META).is_file():
            try:
                items.append(_out(p))
            except (OSError, ValueError):
                continue
    return sorted(items, key=lambda t: t["created"] or 0, reverse=True)


def get(template_id: str) -> dict:
    return _out(_dir(template_id))


def load(template_id: str) -> tuple[Path, dict]:
    path = _dir(template_id)
    return path, json.loads((path / META).read_text())


def create_from_server(server, name: str, description: str, include_auth_key: bool, on_progress=None) -> dict:
    """Blocking. Snapshots a server's config, mods and plugins as a new template."""
    src = server_config.server_dir(server.id)
    tid = uuid.uuid4().hex[:12]
    staging = TEMPLATES_DIR / f".{tid}.tmp"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        provision.copy_content(src, staging, fsutil.Copier(provision.content_size(src), on_progress))
        meta = {
            "format": 1,
            "name": name.strip()[:128] or server.name,
            "description": description.strip()[:1000],
            "created": int(time.time()),
            "source": server.name,
            "config": provision.portable_config(src, include_auth_key),
            "settings": {"version": server.version, "auto_restart": server.auto_restart, "backup_retention": server.backup_retention},
            "counts": _counts(staging),
        }
        (staging / META).write_text(json.dumps(meta, indent=2))
        staging.rename(TEMPLATES_DIR / tid)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return get(tid)


def apply(template_id: str, server_dir: Path, on_progress=None) -> dict:
    """Blocking. Copies a template's content and config into a freshly created server directory."""
    path, meta = load(template_id)
    provision.copy_content(path, server_dir, fsutil.Copier(provision.content_size(path), on_progress))
    server_config.apply_tables(server_dir, meta.get("config", {}))
    return meta


def update(template_id: str, name: str | None, description: str | None) -> dict:
    path, meta = load(template_id)
    if name:
        meta["name"] = name.strip()[:128]
    if description is not None:
        meta["description"] = description.strip()[:1000]
    (path / META).write_text(json.dumps(meta, indent=2))
    return get(template_id)


def delete(template_id: str) -> None:
    shutil.rmtree(_dir(template_id))


def export_zip(template_id: str) -> Path:
    """Blocking. Writes a shareable zip (mods are already compressed, so entries are stored)."""
    path = _dir(template_id)
    out = Path(tempfile.mkstemp(prefix="bmsm-template-", suffix=".zip", dir=config.DATA_DIR)[1])
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zf:
        for f in sorted(path.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(path).as_posix())
    return out


def import_zip(zip_path: Path) -> dict:
    """Blocking. Installs a template from an exported zip."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        prefix = ""
        if META not in names:
            hits = [n for n in names if n.endswith("/" + META) and n.count("/") == 1]
            if not hits:
                raise ValueError("Not a template export (template.json missing)")
            prefix = hits[0][: -len(META)]
        meta = json.loads(zf.read(prefix + META))
        if not isinstance(meta, dict) or "config" not in meta:
            raise ValueError("template.json is not valid")
        tid = uuid.uuid4().hex[:12]
        staging = TEMPLATES_DIR / f".{tid}.tmp"
        staging.mkdir(parents=True)
        try:
            for member in zf.infolist():
                if member.is_dir() or not member.filename.startswith(prefix):
                    continue
                rel = PurePosixPath(member.filename[len(prefix):])
                if ".." in rel.parts or rel.is_absolute() or not (rel.as_posix() == META or rel.parts[0] == "Resources"):
                    continue
                target = staging.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, 4 << 20)
            meta["counts"] = _counts(staging)
            meta["created"] = int(time.time())
            (staging / META).write_text(json.dumps(meta, indent=2))
            staging.rename(TEMPLATES_DIR / tid)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return get(tid)
