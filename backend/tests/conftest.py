import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="bmsm-test-"))
os.environ["DATA_DIR"] = str(_tmp / "data")
os.environ["BACKUP_DIR"] = str(_tmp / "backups")
os.environ["GAME_PORT_RANGE"] = "30814-30820"
os.environ["STATIC_DIR"] = str(_tmp / "static")
os.environ["IMPORT_DIR"] = str(_tmp / "import")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
        assert r.status_code == 200, r.text
        yield c
