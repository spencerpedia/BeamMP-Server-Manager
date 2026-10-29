"""Downloads and tracks BeamMP-Server binaries from GitHub releases."""

import asyncio
import logging
import re
import time
from pathlib import Path

import httpx

from .. import config

log = logging.getLogger(__name__)

BINARY_NAME = "BeamMP-Server"
_TAG_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_CACHE_TTL = 600

_cache: dict[str, tuple[float, object]] = {}
_download_locks: dict[str, asyncio.Lock] = {}


def _version_key(tag: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"[.\-]", tag.lstrip("v")))


def binary_path(tag: str) -> Path:
    if not _TAG_RE.match(tag):
        raise ValueError(f"Bad version tag: {tag!r}")
    return config.BINARIES_DIR / tag / BINARY_NAME


def installed_versions() -> list[str]:
    if not config.BINARIES_DIR.exists():
        return []
    tags = [p.name for p in config.BINARIES_DIR.iterdir() if (p / BINARY_NAME).is_file()]
    return sorted(tags, key=_version_key, reverse=True)


async def list_releases(force: bool = False) -> list[dict]:
    """Stable releases that ship our asset, newest first."""
    cached = _cache.get("releases")
    if cached and not force and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]  # type: ignore[return-value]
    url = f"https://api.github.com/repos/{config.BEAMMP_REPO}/releases?per_page=30"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
    releases = []
    for rel in resp.json():
        if rel.get("draft") or rel.get("prerelease"):
            continue
        asset = next((a for a in rel.get("assets", []) if a["name"] == config.BEAMMP_ASSET), None)
        if asset:
            releases.append(
                {
                    "tag": rel["tag_name"],
                    "published_at": rel.get("published_at"),
                    "url": asset["browser_download_url"],
                    "size": asset.get("size", 0),
                    "notes_url": rel.get("html_url"),
                }
            )
    _cache["releases"] = (time.monotonic(), releases)
    return releases


async def latest_tag() -> str | None:
    try:
        releases = await list_releases()
    except httpx.HTTPError as exc:
        log.warning("Could not reach GitHub for releases: %s", exc)
        installed = installed_versions()
        return installed[0] if installed else None
    return releases[0]["tag"] if releases else None


async def resolve(version: str) -> str:
    if version == "latest":
        tag = await latest_tag()
        if tag is None:
            raise RuntimeError("No BeamMP-Server release available (GitHub unreachable and nothing installed)")
        return tag
    return version


async def ensure_binary(version: str) -> Path:
    """Returns the path to the binary for `version` ("latest" or a tag), downloading it if needed."""
    tag = await resolve(version)
    path = binary_path(tag)
    if path.is_file():
        return path
    lock = _download_locks.setdefault(tag, asyncio.Lock())
    async with lock:
        if path.is_file():
            return path
        releases = await list_releases()
        rel = next((r for r in releases if r["tag"] == tag), None)
        if rel is None:
            raise RuntimeError(f"Release {tag} has no {config.BEAMMP_ASSET} asset")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        log.info("Downloading BeamMP-Server %s", tag)
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("GET", rel["url"]) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(1 << 16):
                        fh.write(chunk)
        tmp.chmod(0o755)
        tmp.rename(path)
    return path


def remove_version(tag: str) -> None:
    path = binary_path(tag)
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass
