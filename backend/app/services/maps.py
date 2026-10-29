"""Maps a server can use: the ones that ship with BeamNG.drive plus any found in enabled mod zips."""

from pathlib import Path

from . import mods

BUILTIN_MAPS = {
    "gridmap_v2": "Grid Map V2",
    "smallgrid": "Grid, Small, Pure",
    "automation_test_track": "Automation Test Track",
    "derby": "Derby Arenas",
    "driver_training": "Driver Training",
    "east_coast_usa": "East Coast, USA",
    "hirochi_raceway": "Hirochi Raceway",
    "industrial": "Industrial Site",
    "italy": "Italy",
    "johnson_valley": "Johnson Valley",
    "jungle_rock_island": "Jungle Rock Island",
    "small_island": "Small Island, USA",
    "utah": "Utah, USA",
    "west_coast_usa": "West Coast, USA",
    "cliff": "Cliff",
}


def level_path(level: str) -> str:
    return f"/levels/{level}/info.json"


def level_from_path(path: str) -> str:
    parts = [p for p in path.strip().split("/") if p]
    return parts[1] if len(parts) >= 2 and parts[0] == "levels" else path


def list_maps(server_dir: Path) -> list[dict]:
    result = [{"level": k, "label": v, "path": level_path(k), "source": "builtin"} for k, v in BUILTIN_MAPS.items()]
    seen = set(BUILTIN_MAPS)
    for mod in mods.list_mods(server_dir):
        for level in mod["maps"]:
            if level in seen:
                continue
            seen.add(level)
            result.append(
                {
                    "level": level,
                    "label": level.replace("_", " ").title(),
                    "path": level_path(level),
                    "source": mod["name"],
                    "enabled": mod["enabled"],
                }
            )
    return result
