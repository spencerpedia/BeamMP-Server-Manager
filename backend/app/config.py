import os
import platform
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))

SERVERS_DIR = DATA_DIR / "servers"
BINARIES_DIR = DATA_DIR / "binaries"
DB_PATH = DATA_DIR / "manager.db"


def _parse_port_range(value: str) -> tuple[int, int]:
    lo, _, hi = value.partition("-")
    lo_i = int(lo)
    return lo_i, int(hi or lo_i)


GAME_PORT_RANGE = _parse_port_range(os.environ.get("GAME_PORT_RANGE", "30814-30823"))

# Which BeamMP-Server release asset to download. Debian 12 matches the runtime image.
_ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower(), "x86_64")
BEAMMP_ASSET = os.environ.get("BEAMMP_ASSET", f"BeamMP-Server.debian.12.{_ARCH}")
BEAMMP_REPO = os.environ.get("BEAMMP_REPO", "BeamMP/BeamMP-Server")

TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "168"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def ensure_dirs() -> None:
    for d in (DATA_DIR, SERVERS_DIR, BINARIES_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def secret_key() -> str:
    """SECRET_KEY env var, or a random key persisted in the data dir."""
    if env := os.environ.get("SECRET_KEY"):
        return env
    path = DATA_DIR / "secret.key"
    if not path.exists():
        ensure_dirs()
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()
