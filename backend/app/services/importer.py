"""Imports existing BeamMP server folders (e.g. from ich777's BeamNG-MP container) mounted at /import.

The source is only read, never changed. Disabled content in ich777's layout
(Resources/Client/deactivated_mods, Resources/Server/deactivated_plugins) and in ours (*.disabled) is
imported as disabled.
"""

import os
from pathlib import Path

import tomlkit

from .. import config
from . import bridge, fsutil, provision, server_config

IMPORT_DIR = Path(os.environ.get("IMPORT_DIR", "/import"))
MAX_DEPTH = 4
DISABLED_MOD_DIRS = ("deactivated_mods", "disabled_mods", "disabled")
DISABLED_PLUGIN_DIRS = ("deactivated_plugins", "disabled_plugins", "disabled")


def _resolve(rel: str) -> Path:
    path = (IMPORT_DIR / rel).resolve()
    if not path.is_relative_to(IMPORT_DIR.resolve()) or not (path / server_config.CONFIG_NAME).is_file():
        raise FileNotFoundError("Not a BeamMP server folder under the import mount")
    return path


def _resource_root(src: Path, general: dict) -> Path:
    folder = str(general.get("ResourceFolder") or "Resources")
    root = (src / folder).resolve()
    return root if root.is_relative_to(src) else src / "Resources"


def _plan(src: Path) -> dict:
    """Lists what would be copied: [(source path, destination relative to the new server dir)]."""
    try:
        general = server_config.read_tables(src).get("General", {})
    except (OSError, tomlkit.exceptions.ParseError):
        general = {}
    res = _resource_root(src, general)
    files: list[tuple[Path, str]] = []
    trees: list[tuple[Path, str]] = []
    client, server = res / "Client", res / "Server"
    if client.is_dir():
        files += [(z, f"Resources/Client/{z.name}") for z in client.glob("*.zip")]
        for d in DISABLED_MOD_DIRS:
            if (client / d).is_dir():
                files += [(z, f"Resources/Client.disabled/{z.name}") for z in (client / d).glob("*.zip")]
    if (res / "Client.disabled").is_dir():
        files += [(z, f"Resources/Client.disabled/{z.name}") for z in (res / "Client.disabled").glob("*.zip")]
    if server.is_dir():
        for p in server.iterdir():
            if not p.is_dir() or p.name == bridge.PLUGIN_NAME or p.name.startswith("."):
                continue
            if p.name in DISABLED_PLUGIN_DIRS:
                trees += [(q, f"Resources/Server.disabled/{q.name}") for q in p.iterdir() if q.is_dir()]
            else:
                trees.append((p, f"Resources/Server/{p.name}"))
    if (res / "Server.disabled").is_dir():
        trees += [(q, f"Resources/Server.disabled/{q.name}") for q in (res / "Server.disabled").iterdir() if q.is_dir()]
    return {"general": general, "files": files, "trees": trees}


def scan() -> dict:
    if not IMPORT_DIR.is_dir():
        return {"mounted": False, "path": str(IMPORT_DIR), "servers": []}
    data_dir = config.DATA_DIR.resolve()
    found = []
    base_depth = len(IMPORT_DIR.parts)
    for dirpath, dirnames, filenames in os.walk(IMPORT_DIR):
        here = Path(dirpath)
        depth = len(here.parts) - base_depth
        # Don't descend into our own data, hidden folders, or mod/plugin trees.
        dirnames[:] = [
            d for d in dirnames
            if depth < MAX_DEPTH and not d.startswith(".") and d not in ("Resources", "node_modules")
            and (here / d).resolve() != data_dir
        ]
        if server_config.CONFIG_NAME not in filenames:
            continue
        plan = _plan(here)
        general = plan["general"]
        mods_enabled = sum(1 for _, dst in plan["files"] if dst.startswith("Resources/Client/"))
        found.append(
            {
                "path": str(here.relative_to(IMPORT_DIR)) or ".",
                "name": general.get("Name", here.name),
                "port": general.get("Port"),
                "map": general.get("Map", ""),
                "max_players": general.get("MaxPlayers"),
                "has_auth_key": bool(general.get("AuthKey")),
                "mods": mods_enabled,
                "mods_disabled": len(plan["files"]) - mods_enabled,
                "plugins": len(plan["trees"]),
                "size": fsutil.tree_size([f for f, _ in plan["files"]] + [t for t, _ in plan["trees"]]),
            }
        )
        dirnames[:] = []  # a server folder won't contain another server
    return {"mounted": True, "path": str(IMPORT_DIR), "servers": sorted(found, key=lambda s: s["path"])}


def copy_into(rel: str, server_dir: Path, on_progress=None) -> dict:
    """Blocking. Copies config values, mods and plugins from the import folder into a new server dir."""
    src = _resolve(rel)
    plan = _plan(src)
    copier = fsutil.Copier(fsutil.tree_size([f for f, _ in plan["files"]] + [t for t, _ in plan["trees"]]), on_progress)
    for f, dst in plan["files"]:
        copier.file(f, server_dir / dst)
    for t, dst in plan["trees"]:
        copier.tree(t, server_dir / dst)
    tables = server_config.read_tables(src)
    tables.get("General", {}).pop("IP", None)
    server_config.apply_tables(server_dir, tables)
    return {"mods": len(plan["files"]), "plugins": len(plan["trees"])}


def source_general(rel: str) -> dict:
    return _plan(_resolve(rel))["general"]
