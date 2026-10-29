"""Finds BeamMP server plugins on GitHub and installs them, whatever layout the repo uses.

Supported layouts (checked in order, after stripping a single wrapping folder):
  1. Resources/Server/<Plugin>/ and Resources/Client/*.zip   (e.g. CobaltEssentials release zip)
  2. Server/<Plugin>/ and Client/*.zip                         (e.g. BeamMP-Essentials)
  3. .lua files at the root → one plugin named after the repo (e.g. Nickel)
  4. Several top-level folders: folders with .lua at their root become plugins, and folders that look
     like a BeamNG client mod (lua/ge, ui/, scripts/, vehicles/, levels/ …) are zipped into client mods
     (e.g. BeamJoy)
"""

import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from . import bridge, downloads, mods

API = "https://api.github.com"
CACHE_TTL = 600
_REPO_RE = re.compile(r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
SKIP_DIRS = {".github", ".vscode", ".vs", "docs", "doc", "assets", "images", "img", "screenshots", "development", "dev", "examples", "example", "tests", "test"}
CLIENT_MARKERS = {"lua/ge", "lua/vehicle", "lua/common", "ui", "scripts", "vehicles", "levels", "art", "settings"}

# Well-known plugins shown before searching. Descriptions are ours; stats come from GitHub.
FEATURED = [
    ("my-name-is-samael/BeamJoy", "All-in-one: races, derby, deliveries, economy, admin tools"),
    ("prestonelam2003/CobaltEssentials", "Permissions, commands and moderation framework"),
    ("StanleyDudek/CobaltEssentialsInterface", "In-game UI for Cobalt Essentials"),
    ("boubouleuh/Nickel-BeamMP-Plugin", "Moderation and admin plugin with extensions"),
    ("BeamMP/BeamMP-Essentials", "Official essentials: AFK kick and utilities"),
    ("Danyxeon/whitelistman", "Simple whitelist"),
]

_cache: dict[str, tuple[float, object]] = {}


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {token}"
    return h


async def _api(path: str, params: dict | None = None):
    key = path + repr(sorted((params or {}).items()))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]
    async with downloads.client(headers=_headers()) as c:
        resp = await c.get(API + path, params=params)
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise RuntimeError("GitHub rate limit reached. Wait a minute, or set GITHUB_TOKEN on the container.")
    resp.raise_for_status()
    data = resp.json()
    _cache[key] = (time.monotonic(), data)
    return data


def _repo_out(r: dict, blurb: str = "") -> dict:
    return {
        "full_name": r["full_name"],
        "description": blurb or (r.get("description") or ""),
        "stars": r.get("stargazers_count", 0),
        "updated": r.get("pushed_at"),
        "url": r.get("html_url"),
        "owner_avatar": (r.get("owner") or {}).get("avatar_url"),
        "language": r.get("language"),
        "archived": r.get("archived", False),
    }


def parse_repo(value: str) -> str:
    m = _REPO_RE.match(value.strip())
    if not m:
        raise ValueError("Use owner/repo or a github.com link")
    return f"{m.group(1)}/{m.group(2)}"


async def featured() -> list[dict]:
    out = []
    for full_name, blurb in FEATURED:
        try:
            out.append(_repo_out(await _api(f"/repos/{full_name}"), blurb))
        except (httpx.HTTPError, RuntimeError):
            out.append({"full_name": full_name, "description": blurb, "stars": None, "url": f"https://github.com/{full_name}"})
    return out


async def search(q: str, page: int = 1) -> dict:
    terms = q.strip()
    query = f"{terms} beammp in:name,description,topics" if terms else "beammp in:name,description,topics language:lua"
    data = await _api("/search/repositories", {"q": query, "sort": "stars", "per_page": 20, "page": page})
    return {"items": [_repo_out(r) for r in data.get("items", [])], "total": min(data.get("total_count", 0), 1000), "page": page}


async def _source(full_name: str) -> tuple[str, str]:
    """(download url, label): the latest release's .zip asset if any, otherwise the default branch."""
    try:
        rel = await _api(f"/repos/{full_name}/releases/latest")
        assets = [a for a in rel.get("assets", []) if a["name"].lower().endswith(".zip")]
        if assets:
            # Prefer an asset named like the repo or "server"; avoid data packs.
            repo = full_name.split("/")[1].lower()
            assets.sort(key=lambda a: (repo not in a["name"].lower() and "server" not in a["name"].lower(), "data" in a["name"].lower()))
            return assets[0]["browser_download_url"], f"release {rel['tag_name']}"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
    info = await _api(f"/repos/{full_name}")
    return f"{API}/repos/{full_name}/zipball/{info['default_branch']}", f"branch {info['default_branch']}"


def _safe_extract(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            parts = PurePosixPath(member.filename).parts
            if not parts or ".." in parts or parts[0].startswith("/"):
                continue
            target = dest.joinpath(*parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def _ci(path: Path, name: str) -> Path | None:
    """Case-insensitive child lookup."""
    if not path.is_dir():
        return None
    return next((p for p in path.iterdir() if p.name.lower() == name.lower()), None)


def _has_lua(d: Path) -> bool:
    return any(p.suffix == ".lua" for p in d.iterdir() if p.is_file())


def _looks_like_client_mod(d: Path) -> bool:
    return any((d / marker).is_dir() for marker in CLIENT_MARKERS)


def analyze(root: Path, repo_name: str) -> dict:
    """Returns {"plugins": [(name, path)], "client_dirs": [(name, path)], "client_zips": [path]}."""
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        root = entries[0]

    plan = {"plugins": [], "client_dirs": [], "client_zips": []}
    base = _ci(root, "Resources") or root
    server, client = _ci(base, "Server"), _ci(base, "Client")
    if (server and server.is_dir()) or (client and client.is_dir()):
        if server and server.is_dir():
            subdirs = [d for d in sorted(server.iterdir()) if d.is_dir() and not d.name.startswith(".")]
            if _has_lua(server) and not subdirs:
                plan["plugins"].append((repo_name, server))  # Server/ itself is the plugin folder
            else:
                plan["plugins"] += [(d.name, d) for d in subdirs]
        if client and client.is_dir():
            plan["client_zips"] += sorted(p for p in client.glob("*.zip"))
            plan["client_dirs"] += [(d.name, d) for d in sorted(client.iterdir()) if d.is_dir() and _looks_like_client_mod(d)]
        return plan

    if _has_lua(root):
        plan["plugins"].append((repo_name, root))
        return plan

    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name.lower() in SKIP_DIRS or d.name.startswith("."):
            continue
        if _looks_like_client_mod(d):
            plan["client_dirs"].append((d.name, d))
        elif _has_lua(d):
            plan["plugins"].append((d.name, d))
    plan["client_zips"] += sorted(root.glob("*.zip")) if not plan["plugins"] else []
    return plan


def _zip_dir(src: Path, dest_zip: Path) -> None:
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(src).as_posix())


def apply_plan(server_dir: Path, plan: dict) -> dict:
    res = server_dir / "Resources"
    installed = {"plugins": [], "mods": []}
    for name, path in plan["plugins"]:
        name = mods.safe_name(name)
        if name == bridge.PLUGIN_NAME:
            continue
        for existing in (res / "Server" / name, res / "Server.disabled" / name):
            if existing.exists():
                shutil.rmtree(existing)
        shutil.copytree(path, res / "Server" / name, ignore=shutil.ignore_patterns(".git", ".github"))
        installed["plugins"].append(name)
    client = res / "Client"
    client.mkdir(parents=True, exist_ok=True)
    for zip_path in plan["client_zips"]:
        name = mods.safe_name(zip_path.name)
        (res / "Client.disabled" / name).unlink(missing_ok=True)
        shutil.copy2(zip_path, client / name)
        installed["mods"].append(name)
    for name, path in plan["client_dirs"]:
        zname = mods.safe_name(f"{name}.zip")
        (res / "Client.disabled" / zname).unlink(missing_ok=True)
        _zip_dir(path, client / zname)
        installed["mods"].append(zname)
    return installed


async def install(server_dir: Path, full_name: str, job) -> dict:
    job.update(message=f"Finding the latest {full_name} download…")
    url, label = await _source(full_name)
    repo_name = full_name.split("/")[1]
    with tempfile.TemporaryDirectory(prefix="bmsm-plugin-", dir=server_dir.parent) as tmpdir:
        tmp = Path(tmpdir)

        def progress(frac, done, total):
            job.update(progress=frac * 0.8, message=f"Downloading {full_name} ({label})")

        job.update(message=f"Downloading {full_name} ({label})")
        archive, _ = await downloads.stream_to(url, tmp, progress, headers=_headers())
        if not zipfile.is_zipfile(archive):
            raise RuntimeError("The download wasn't a zip file")
        job.update(progress=0.85, message="Unpacking…")
        extracted = tmp / "x"
        _safe_extract(archive, extracted)
        plan = analyze(extracted, repo_name)
        if not plan["plugins"] and not plan["client_dirs"] and not plan["client_zips"]:
            raise RuntimeError("Couldn't find any server plugin or client mod files in this repository")
        job.update(progress=0.9, message="Installing…")
        result = apply_plan(server_dir, plan)
    result.update({"repo": full_name, "source": label})
    return result
