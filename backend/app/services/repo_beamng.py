"""Browses the BeamNG.com mod repository (www.beamng.com/resources).

There is no public API, so this reads the server-rendered XenForo listing pages. Keyword search sits
behind a bot challenge and is deliberately not used; browsing is by category and sort order, and any
mod can be installed by pasting its URL. Pages are cached to keep request volume low.
"""

import html
import json
import re
import time
import zipfile
from pathlib import Path

from . import downloads, mods

BASE = "https://www.beamng.com/"
CACHE_TTL = 600

CATEGORIES = {
    "": "All mods",
    "vehicles.2": "Vehicles",
    "terrains-levels-maps.9": "Maps",
    "land.3": "Land",
    "mods-of-mods.7": "Mods of mods",
    "props.5": "Props",
    "scenarios.8": "Scenarios",
    "skins.12": "Skins",
    "sounds.13": "Sounds",
    "user-interface-apps.10": "UI apps",
    "license-plates.15": "License plates",
    "automation.16": "Automation",
    "track-builder.17": "Track builder",
}
ORDERS = {
    "download_count": "Most downloaded",
    "rating_weighted": "Top rated",
    "last_update": "Recently updated",
    "resource_date": "Newest",
}

_cache: dict[str, tuple[float, object]] = {}
_ITEM_RE = re.compile(r'<li class="resourceListItem[^"]*" id="resource-(\d+)">(.*?)</li>\s*(?=<li class="resourceListItem|</ol>)', re.S)
_URL_RE = re.compile(r"beamng\.com/resources/(?:[a-z0-9-]+\.)?(\d+)", re.I)
META_FILE = Path(".bmsm") / "mods_meta.json"


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _abs(url: str) -> str:
    return url if url.startswith("http") else BASE + url.lstrip("/")


def _num(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s) or 0)


async def _get(path: str) -> str:
    cached = _cache.get(path)
    if cached and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]  # type: ignore[return-value]
    async with downloads.client() as c:
        resp = await c.get(_abs(path))
        resp.raise_for_status()
    text = resp.text
    if "<title>CrowdSec" in text or "challenge" in text[:2000].lower() and "resourceListItem" not in text:
        raise RuntimeError("BeamNG.com asked for a browser check; try again later")
    _cache[path] = (time.monotonic(), text)
    if len(_cache) > 300:
        oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:100]
        for key, _ in oldest:
            _cache.pop(key, None)
    return text


def _parse_list(page: str) -> list[dict]:
    items = []
    for rid, body in _ITEM_RE.findall(page):
        title_m = re.search(r'<h3 class="title">.*?<a\s+href="(resources/[^"]+)">(.*?)</a>\s*<span class="version">(.*?)</span>', body, re.S)
        if not title_m:
            continue
        prefix = re.search(r'<span class="prefix[^"]*">(.*?)</span>', body)
        icon = re.search(r'class="resourceIcon"><img src="([^"]+)"', body)
        author = re.search(r'<div class="resourceDetails muted">\s*<a[^>]*>(.*?)</a>', body, re.S)
        category = re.search(r'resources/categories/[^"]+">(.*?)</a>', body)
        updated = re.search(r'data-time="(\d+)"', body) or re.search(r'title="([^"]+)"', body)
        rating = re.search(r'<span class="Number" itemprop="average">([\d.]+)</span>', body)
        ratings = re.search(r'<span class="Hint">([\d,]+) rating', body)
        dl = re.search(r'resourceDownloads"><dt>Downloads:</dt>\s*<dd>([\d,]+)</dd>', body)
        tagline = re.search(r'<div class="tagLine">(.*?)</div>', body, re.S)
        items.append(
            {
                "id": int(rid),
                "url": _abs(title_m.group(1)),
                "title": _text(title_m.group(2)),
                "version": _text(title_m.group(3)),
                "prefix": _text(prefix.group(1)) if prefix else "",
                "icon": _abs(icon.group(1)) if icon else None,
                "author": _text(author.group(1)) if author else "",
                "category": _text(category.group(1)) if category else "",
                "updated": int(updated.group(1)) if updated and updated.group(1).isdigit() else None,
                "rating": float(rating.group(1)) if rating else None,
                "ratings": _num(ratings.group(1)) if ratings else 0,
                "downloads": _num(dl.group(1)) if dl else 0,
                "tagline": _text(tagline.group(1)) if tagline else "",
            }
        )
    return items


async def browse(category: str = "", order: str = "download_count", page: int = 1) -> dict:
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    if order not in ORDERS:
        raise ValueError("Unknown sort order")
    base = f"resources/categories/{category}/" if category else "resources/"
    text = await _get(f"{base}?order={order}&page={max(1, page)}")
    last = max([_num(p) for p in re.findall(r'class="PageNav"[^>]*?data-last="(\d+)"', text, re.S)] or [page])
    return {"items": _parse_list(text), "page": page, "pages": last}


def parse_resource_id(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    m = _URL_RE.search(value)
    if not m:
        raise ValueError("Paste a beamng.com/resources/… link or a resource ID")
    return int(m.group(1))


async def details(resource_id: int) -> dict:
    text = await _get(f"resources/{resource_id}/")
    title = re.search(r"<h1>(.*?)\s*<span class=\"muted\">(.*?)</span></h1>", text, re.S)
    if not title:
        raise LookupError("Mod not found on BeamNG.com")
    dl = re.search(r'<a href="(resources/[^"]+/download\?version=\d+)" class="inner"\s*>\s*Download Now\s*(?:<small class="minorText">(.*?)</small>)?', text, re.S)
    external = re.search(r'<a href="([^"]+)" class="inner"[^>]*>\s*Go to Download', text)
    icon = re.search(r'<img src="(data/resource_icons/[^"]+)"[^>]*class="resourceIcon"', text)
    tagline = re.search(r'<p class="tagLine muted">(.*?)</p>', text, re.S)
    author = re.search(r'<dl class="author"><dt>Author:</dt>\s*<dd><a[^>]*>(.*?)</a>', text, re.S)
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', text)
    return {
        "id": resource_id,
        "title": _text(title.group(1)),
        "version": _text(title.group(2)),
        "tagline": _text(tagline.group(1)) if tagline else "",
        "author": _text(author.group(1)) if author else "",
        "icon": _abs(icon.group(1)) if icon else None,
        "url": canonical.group(1) if canonical else _abs(f"resources/{resource_id}/"),
        "download_url": _abs(html.unescape(dl.group(1))) if dl else None,
        "size": _text(dl.group(2)) if dl and dl.group(2) else "",
        "external": bool(external and not dl),
    }


# ---- install + bookkeeping -----------------------------------------------------------------


def read_meta(server_dir: Path) -> dict:
    path = server_dir / META_FILE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write_meta(server_dir: Path, meta: dict) -> None:
    path = server_dir / META_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=1))


def forget_mod(server_dir: Path, filename: str) -> None:
    meta = read_meta(server_dir)
    if meta.pop(filename, None) is not None:
        _write_meta(server_dir, meta)


async def install(server_dir: Path, resource_id: int, job) -> dict:
    job.update(message="Looking up mod…")
    info = await details(resource_id)
    if not info["download_url"]:
        raise RuntimeError("This mod is hosted off-site; download it manually and upload the zip")
    job.update(message=f"Downloading {info['title']} {info['size']}".strip())
    client_dir = server_dir / "Resources" / "Client"

    def progress(frac, done, total):
        job.update(progress=frac * 0.98, message=f"Downloading {info['title']} ({done // 2**20}/{total // 2**20} MB)")

    tmp, suggested = await downloads.stream_to(info["download_url"], client_dir, progress)
    try:
        if not zipfile.is_zipfile(tmp):
            raise RuntimeError("Downloaded file is not a zip (the mod may need a manual download)")
        name = mods.safe_name(suggested or f"mod_{resource_id}.zip")
        if not name.lower().endswith(".zip"):
            name += ".zip"
        # Replace any earlier copy of this mod (an update may have a new filename).
        meta = read_meta(server_dir)
        for old_name, entry in list(meta.items()):
            if entry.get("id") == resource_id and old_name != name:
                for folder in ("Client", "Client.disabled"):
                    (server_dir / "Resources" / folder / old_name).unlink(missing_ok=True)
                meta.pop(old_name)
        (server_dir / "Resources" / "Client.disabled" / name).unlink(missing_ok=True)
        dest = client_dir / name
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    meta[name] = {"id": resource_id, "title": info["title"], "version": info["version"], "url": info["url"], "installed": int(time.time())}
    _write_meta(server_dir, meta)
    return {"name": name, "title": info["title"], "version": info["version"], "maps": mods.maps_in_zip(dest)}
