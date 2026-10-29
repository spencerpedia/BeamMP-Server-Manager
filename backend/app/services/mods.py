"""Client mods (Resources/Client/*.zip) and server Lua plugins (Resources/Server/<name>/)."""

import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from . import bridge

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ \-()\[\]]+")
_LEVEL_RE = re.compile(r"^levels/([^/]+)/", re.IGNORECASE)
MAX_UPLOAD = 4 * 1024**3


def safe_name(filename: str) -> str:
    name = _SAFE_NAME_RE.sub("_", Path(filename).name).strip(" .")
    if not name:
        raise ValueError("Invalid file name")
    return name


def _dirs(server_dir: Path, kind: str) -> tuple[Path, Path]:
    base = server_dir / "Resources"
    return base / kind, base / f"{kind}.disabled"


def maps_in_zip(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as zf:
            names = {m.group(1) for n in zf.namelist() if (m := _LEVEL_RE.match(n))}
    except (zipfile.BadZipFile, OSError):
        return []
    return sorted(names)


async def _save_upload(upload: UploadFile, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    written = 0
    try:
        with tmp.open("wb") as fh:
            while chunk := await upload.read(1 << 20):
                written += len(chunk)
                if written > MAX_UPLOAD:
                    raise ValueError("File too large")
                fh.write(chunk)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


# ---- client mods ---------------------------------------------------------------------------


def list_mods(server_dir: Path) -> list[dict]:
    enabled_dir, disabled_dir = _dirs(server_dir, "Client")
    mods = []
    for folder, enabled in ((enabled_dir, True), (disabled_dir, False)):
        if not folder.exists():
            continue
        for p in sorted(folder.glob("*.zip"), key=lambda x: x.name.lower()):
            mods.append({"name": p.name, "size": p.stat().st_size, "enabled": enabled, "maps": maps_in_zip(p)})
    return mods


async def upload_mod(server_dir: Path, upload: UploadFile) -> dict:
    name = safe_name(upload.filename or "")
    if not name.lower().endswith(".zip"):
        raise ValueError("Mods must be .zip files")
    enabled_dir, disabled_dir = _dirs(server_dir, "Client")
    enabled_dir.mkdir(parents=True, exist_ok=True)
    (disabled_dir / name).unlink(missing_ok=True)
    dest = enabled_dir / name
    await _save_upload(upload, dest)
    if not zipfile.is_zipfile(dest):
        dest.unlink()
        raise ValueError("Not a valid zip file")
    return {"name": name, "size": dest.stat().st_size, "enabled": True, "maps": maps_in_zip(dest)}


def _find_mod(server_dir: Path, name: str) -> Path:
    name = safe_name(name)
    for folder in _dirs(server_dir, "Client"):
        if (folder / name).is_file():
            return folder / name
    raise FileNotFoundError(name)


def set_mod_enabled(server_dir: Path, name: str, enabled: bool) -> None:
    src = _find_mod(server_dir, name)
    enabled_dir, disabled_dir = _dirs(server_dir, "Client")
    target = (enabled_dir if enabled else disabled_dir) / src.name
    if src != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        src.replace(target)


def delete_mod(server_dir: Path, name: str) -> None:
    _find_mod(server_dir, name).unlink()


# ---- server plugins ------------------------------------------------------------------------


def list_plugins(server_dir: Path) -> list[dict]:
    enabled_dir, disabled_dir = _dirs(server_dir, "Server")
    plugins = []
    for folder, enabled in ((enabled_dir, True), (disabled_dir, False)):
        if not folder.exists():
            continue
        for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_dir() or p.name == bridge.PLUGIN_NAME:
                continue
            files = [f for f in p.rglob("*") if f.is_file()]
            plugins.append(
                {
                    "name": p.name,
                    "enabled": enabled,
                    "files": len(files),
                    "size": sum(f.stat().st_size for f in files),
                }
            )
    return plugins


def _extract_zip(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        parts = [PurePosixPath(m.filename).parts for m in members]
        if any(".." in p or (p and p[0].startswith("/")) for p in parts):
            raise ValueError("Zip contains unsafe paths")
        # If everything sits in one top-level folder, strip it so the plugin isn't nested twice.
        strip = len({p[0] for p in parts}) == 1 and all(len(p) > 1 for p in parts)
        for member, p in zip(members, parts):
            rel = PurePosixPath(*p[1:]) if strip else PurePosixPath(*p)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


async def upload_plugin(server_dir: Path, upload: UploadFile) -> str:
    filename = safe_name(upload.filename or "")
    lower = filename.lower()
    if not (lower.endswith(".zip") or lower.endswith(".lua")):
        raise ValueError("Plugins must be a .zip of a plugin folder or a single .lua file")
    plugin_name = filename.rsplit(".", 1)[0]
    if plugin_name == bridge.PLUGIN_NAME:
        raise ValueError("That plugin name is reserved")
    enabled_dir, disabled_dir = _dirs(server_dir, "Server")
    dest = enabled_dir / plugin_name
    for existing in (dest, disabled_dir / plugin_name):
        if existing.exists():
            shutil.rmtree(existing)
    staging = enabled_dir / f".{plugin_name}.upload"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        if lower.endswith(".lua"):
            await _save_upload(upload, staging / "main.lua")
        else:
            zip_tmp = staging.with_suffix(".zip")
            await _save_upload(upload, zip_tmp)
            try:
                _extract_zip(zip_tmp, staging)
            finally:
                zip_tmp.unlink(missing_ok=True)
        staging.rename(dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return plugin_name


def _find_plugin(server_dir: Path, name: str) -> Path:
    name = safe_name(name)
    if name == bridge.PLUGIN_NAME:
        raise PermissionError("The manager bridge plugin can't be changed")
    for folder in _dirs(server_dir, "Server"):
        if (folder / name).is_dir():
            return folder / name
    raise FileNotFoundError(name)


def set_plugin_enabled(server_dir: Path, name: str, enabled: bool) -> None:
    src = _find_plugin(server_dir, name)
    enabled_dir, disabled_dir = _dirs(server_dir, "Server")
    target = (enabled_dir if enabled else disabled_dir) / src.name
    if src != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        src.rename(target)


def delete_plugin(server_dir: Path, name: str) -> None:
    shutil.rmtree(_find_plugin(server_dir, name))
