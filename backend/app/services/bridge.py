"""Installs the bridge Lua plugin and parses the "[BMSM]{json}" lines it prints."""

import json
import re
import shutil
from pathlib import Path

PLUGIN_NAME = "_BMSM"
_SOURCE = Path(__file__).resolve().parent.parent / "bridge_lua" / "main.lua"
_LINE_RE = re.compile(r"\[BMSM\](\{.*\})\s*$")


def install(server_dir: Path) -> None:
    dest = server_dir / "Resources" / "Server" / PLUGIN_NAME
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "main.lua"
    # Only copy when changed, so BeamMP's plugin hot-reload isn't triggered needlessly.
    if not target.exists() or target.read_bytes() != _SOURCE.read_bytes():
        shutil.copyfile(_SOURCE, target)


def write_bans(server_dir: Path, bans: list[dict]) -> None:
    path = server_dir / ".bmsm" / "bans.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(bans))
    tmp.replace(path)


def parse_line(line: str) -> dict | None:
    m = _LINE_RE.search(line)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "t" not in data:
        return None
    # Lua encodes an empty table as {} rather than [].
    if data["t"] == "players" and not isinstance(data.get("players"), list):
        data["players"] = list((data.get("players") or {}).values())
    return data
