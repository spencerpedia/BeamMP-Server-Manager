"""Reads and writes a server's ServerConfig.toml while keeping its comments intact."""

from pathlib import Path

import tomlkit

from .. import config

CONFIG_NAME = "ServerConfig.toml"

# Mirrors the file BeamMP-Server v3.9 generates on first run.
DEFAULT_TEMPLATE = """\
# This is the BeamMP-Server config file.
# Help & Documentation: `https://docs.beammp.com/server/server-maintenance/`
# IMPORTANT: Fill in the AuthKey with the key you got from `https://keymaster.beammp.com/` on the left under "Keys"
[Misc]
# Specifies the time between update reminders.
UpdateReminderTime = "30s"
# Hides the periodic update message which notifies you of a new server version.
ImScaredOfUpdates = true

[General]
Description = "BeamMP Default Description"
MaxCars = 1
# Whether to log chat messages in the console / log
LogChat = true
ResourceFolder = "Resources"
# The IP address to bind the server to, this is NOT related to your public IP.
IP = "::"
Name = "BeamMP Server"
Private = true
# Whether to allow unconnected clients to get the public server information without joining
InformationPacket = true
# Whether to allow guests
AllowGuests = true
Port = 30814
Debug = false
# Add custom identifying tags to your server to make it easier to find. Format should be TagA,TagB,TagC.
Tags = "Freeroam"
# AuthKey has to be filled out in order to run the server
AuthKey = ""
MaxPlayers = 8
Map = "/levels/gridmap_v2/info.json"
"""

# Fields shown on the config form. Keys not listed here stay editable through the raw editor.
FIELDS: list[dict] = [
    {"key": "Name", "type": "string", "label": "Server name", "help": "Shown in the BeamMP server browser. Supports ^ colour codes."},
    {"key": "Description", "type": "text", "label": "Description"},
    {"key": "AuthKey", "type": "secret", "label": "Auth key", "help": "From keymaster.beammp.com → Keys."},
    {"key": "Map", "type": "map", "label": "Map"},
    {"key": "MaxPlayers", "type": "int", "label": "Max players", "min": 1, "max": 500},
    {"key": "MaxCars", "type": "int", "label": "Max cars per player", "min": 0, "max": 100},
    {"key": "Private", "type": "bool", "label": "Private", "help": "Hide from the public server list."},
    {"key": "AllowGuests", "type": "bool", "label": "Allow guests"},
    {"key": "Tags", "type": "string", "label": "Tags", "help": "Comma separated, e.g. Freeroam,Drift"},
    {"key": "LogChat", "type": "bool", "label": "Log chat"},
    {"key": "InformationPacket", "type": "bool", "label": "Information packet", "help": "Let unconnected clients query server info."},
    {"key": "Debug", "type": "bool", "label": "Debug logging"},
]
_TYPES = {f["key"]: f["type"] for f in FIELDS}
# Owned by the manager: Port comes from the server record, ResourceFolder is fixed so mods/plugins can be found.
MANAGED_KEYS = {"Port", "ResourceFolder"}


def path_for(server_dir: Path) -> Path:
    return server_dir / CONFIG_NAME


def server_dir(server_id: int) -> Path:
    return config.SERVERS_DIR / str(server_id)


def _load(server_dir: Path) -> tomlkit.TOMLDocument:
    path = path_for(server_dir)
    text = path.read_text() if path.exists() else DEFAULT_TEMPLATE
    return tomlkit.parse(text)


def _save(server_dir: Path, doc: tomlkit.TOMLDocument) -> None:
    path = path_for(server_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomlkit.dumps(doc))
    tmp.replace(path)


def create_default(server_dir: Path, name: str, port: int, auth_key: str = "") -> None:
    server_dir.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.parse(DEFAULT_TEMPLATE)
    doc["General"]["Name"] = name
    doc["General"]["Port"] = port
    doc["General"]["AuthKey"] = auth_key
    _save(server_dir, doc)
    for sub in ("Resources/Client", "Resources/Server"):
        (server_dir / sub).mkdir(parents=True, exist_ok=True)


def read_general(server_dir: Path) -> dict:
    return _load(server_dir).get("General", {}).unwrap()


def _coerce(key: str, value):
    kind = _TYPES.get(key)
    if kind == "int":
        return int(value)
    if kind == "bool":
        return bool(value)
    if kind in ("string", "text", "secret", "map"):
        return str(value)
    return value


def update_general(server_dir: Path, values: dict) -> dict:
    doc = _load(server_dir)
    general = doc.setdefault("General", tomlkit.table())
    for key, value in values.items():
        if key in MANAGED_KEYS:
            continue
        general[key] = _coerce(key, value)
    _save(server_dir, doc)
    return general.unwrap()


def enforce_managed(server_dir: Path, port: int) -> None:
    """Called before every start so hand edits can't break the port or resource layout."""
    doc = _load(server_dir)
    general = doc.setdefault("General", tomlkit.table())
    if general.get("Port") != port:
        general["Port"] = port
    if general.get("ResourceFolder") != "Resources":
        general["ResourceFolder"] = "Resources"
    _save(server_dir, doc)


def read_tables(server_dir: Path) -> dict:
    """{"General": {...}, "Misc": {...}} as plain values, for templates and imports."""
    doc = _load(server_dir)
    return {t: doc[t].unwrap() for t in ("General", "Misc") if t in doc}


def apply_tables(server_dir: Path, tables: dict) -> None:
    """Merges table values into the config, leaving manager-owned keys alone."""
    doc = _load(server_dir)
    for table, values in tables.items():
        if table not in ("General", "Misc") or not isinstance(values, dict):
            continue
        target = doc.setdefault(table, tomlkit.table())
        for key, value in values.items():
            if table == "General" and key in MANAGED_KEYS:
                continue
            if isinstance(value, (str, int, float, bool)):
                target[key] = value
    _save(server_dir, doc)


def read_raw(server_dir: Path) -> str:
    path = path_for(server_dir)
    return path.read_text() if path.exists() else DEFAULT_TEMPLATE


def write_raw(server_dir: Path, text: str) -> None:
    doc = tomlkit.parse(text)  # raises tomlkit.exceptions.ParseError on bad input
    if "General" not in doc:
        raise ValueError("Config must contain a [General] table")
    _save(server_dir, doc)
