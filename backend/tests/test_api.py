import io
import zipfile


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_setup_only_once(client):
    assert client.get("/api/auth/status").json() == {"needs_setup": False}
    assert client.post("/api/auth/setup", json={"username": "x", "password": "password123"}).status_code == 409


def test_server_lifecycle_crud(client):
    r = client.post("/api/servers", json={"name": "Alpha", "auth_key": "abc"})
    assert r.status_code == 201, r.text
    alpha = r.json()
    assert alpha["port"] == 30814 and alpha["state"] == "stopped" and alpha["has_auth_key"]

    beta = client.post("/api/servers", json={"name": "Beta"}).json()
    assert beta["port"] == 30815
    assert client.post("/api/servers", json={"name": "Dup", "port": 30815}).status_code == 409
    assert client.post("/api/servers", json={"name": "Out", "port": 40000}).status_code == 422

    # Starting without an auth key is refused before touching the binary.
    assert client.post(f"/api/servers/{beta['id']}/start").status_code == 422

    cfg = client.get(f"/api/servers/{alpha['id']}/config").json()
    assert cfg["values"]["Name"] == "Alpha"
    r = client.put(f"/api/servers/{alpha['id']}/config", json={"Name": "Alpha 2", "MaxPlayers": 4})
    assert r.status_code == 200
    assert client.get(f"/api/servers/{alpha['id']}").json()["name"] == "Alpha 2"
    assert client.put(f"/api/servers/{alpha['id']}/config/raw", json={"text": "not = = toml"}).status_code == 422

    assert client.delete(f"/api/servers/{beta['id']}").status_code == 200
    assert len(client.get("/api/servers").json()) == 1


def test_mods_plugins_bans_backups_schedules(client):
    sid = client.post("/api/servers", json={"name": "Gamma"}).json()["id"]
    base = f"/api/servers/{sid}"

    r = client.post(f"{base}/mods", files=[("files", ("map.zip", _zip({"levels/foo/info.json": "{}"}), "application/zip"))])
    assert r.status_code == 201, r.text
    assert client.post(f"{base}/mods", files=[("files", ("bad.zip", b"nope", "application/zip"))]).status_code == 422
    maps_ = client.get(f"{base}/maps").json()
    assert any(m["level"] == "foo" for m in maps_["maps"])
    assert client.put(f"{base}/maps", json={"path": "/levels/foo/info.json"}).status_code == 200
    assert client.get(f"{base}").json()["map"] == "foo"
    assert client.patch(f"{base}/mods/map.zip", json={"enabled": False}).status_code == 200
    assert client.get(f"{base}/mods").json()[0]["enabled"] is False

    r = client.post(f"{base}/plugins", files={"file": ("Cool.zip", _zip({"Cool/main.lua": "print(1)"}), "application/zip")})
    assert r.status_code == 201, r.text
    plugins = client.get(f"{base}/plugins").json()
    assert plugins == [{"name": "Cool", "enabled": True, "files": 1, "size": 8}]
    bad = _zip({"../evil.lua": "x"})
    assert client.post(f"{base}/plugins", files={"file": ("Evil.zip", bad, "application/zip")}).status_code == 422

    ban = client.post(f"{base}/bans", json={"name": "Griefer", "reason": "ramming"}).json()
    assert client.get(f"{base}/bans").json()[0]["name"] == "Griefer"
    assert client.delete(f"{base}/bans/{ban['id']}").status_code == 200

    b = client.post(f"{base}/backups", json={"label": "test"}).json()
    assert client.get(f"{base}/backups").json()["backups"][0]["name"] == b["name"]
    client.delete(f"{base}/mods/map.zip")
    assert client.post(f"{base}/backups/{b['name']}/restore").status_code == 200
    assert any(m["name"] == "map.zip" for m in client.get(f"{base}/mods").json())

    assert client.post(f"{base}/schedules", json={"action": "restart", "cron": "bad cron"}).status_code == 422
    s = client.post(f"{base}/schedules", json={"action": "backup", "cron": "0 4 * * *"}).json()
    assert s["next_run"] is not None
    assert client.delete(f"{base}/schedules/{s['id']}").status_code == 200


def test_viewer_permissions(client):
    sid = client.post("/api/servers", json={"name": "Delta"}).json()["id"]
    other = client.post("/api/servers", json={"name": "Hidden"}).json()["id"]
    r = client.post("/api/users", json={"username": "viewer", "password": "password123", "role": "viewer", "server_ids": [sid]})
    assert r.status_code == 201
    from fastapi.testclient import TestClient

    from app.main import app

    v = TestClient(app)
    assert v.post("/api/auth/login", json={"username": "viewer", "password": "password123"}).status_code == 200
    ids = [s["id"] for s in v.get("/api/servers").json()]
    assert ids == [sid]
    assert v.get(f"/api/servers/{other}").status_code == 403
    assert v.post(f"/api/servers/{sid}/start").status_code == 403
    assert v.get(f"/api/servers/{sid}/config").status_code == 200
    assert v.get("/api/users").status_code == 403
