"""Shared HTTP helpers: a polite client and streaming downloads with progress."""

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

USER_AGENT = "BeamMP-Server-Manager/0.2 (+self-hosted panel)"
MAX_DOWNLOAD = 8 * 1024**3


def client(**kw) -> httpx.AsyncClient:
    headers = {"User-Agent": USER_AGENT, **kw.pop("headers", {})}
    return httpx.AsyncClient(timeout=kw.pop("timeout", 30), follow_redirects=True, headers=headers, **kw)


def filename_from(resp: httpx.Response) -> str:
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    if m:
        return unquote(m.group(1)).strip()
    return unquote(Path(urlparse(str(resp.url)).path).name)


async def stream_to(url: str, dest_dir: Path, on_progress=None, headers: dict | None = None) -> tuple[Path, str]:
    """Downloads `url` into dest_dir as a .part file. Returns (temp path, server-suggested filename)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    async with client(timeout=httpx.Timeout(30, read=120), headers=headers or {}) as c:
        async with c.stream("GET", url) as resp:
            resp.raise_for_status()
            name = filename_from(resp)
            total = int(resp.headers.get("content-length") or 0)
            tmp = dest_dir / f".download-{abs(hash(url)) % 10**8}.part"
            done = 0
            try:
                with tmp.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(1 << 16):
                        done += len(chunk)
                        if done > MAX_DOWNLOAD:
                            raise ValueError("Download is too large")
                        fh.write(chunk)
                        if on_progress and total:
                            on_progress(done / total, done, total)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
    return tmp, name
