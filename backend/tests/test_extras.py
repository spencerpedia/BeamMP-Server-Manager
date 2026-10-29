import io
import os
import time
import zipfile
from pathlib import Path

from app.services import repo_github


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _wait(client, job) -> dict:
    for _ in range(100):
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] != "running":
            assert j["status"] == "done", j
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_import_ich777_layout(client):
    src = Path(os.environ["IMPORT_DIR"]) / "beamng-mp"
    (src / "Resources/Client/deactivated_mods").mkdir(parents=True)
    (src / "Resources/Server/deactivated_plugins/OldPlugin").mkdir(parents=True)
    (src / "Resources/Server/Live").mkdir(parents=True)
    (src / "Resources/Client/car.zip").write_bytes(_zip_bytes({"vehicles/car/a.jbeam": "{}"}))
    (src / "Resources/Client/off.zip").write_bytes(_zip_bytes({"levels/offmap/info.json": "{}"}))
    (src / "Resources/Client/deactivated_mods/old.zip").write_bytes(_zip_bytes({"x": "y"}))
    (src / "Resources/Server/Live/main.lua").write_text("print(1)")
    (src / "Resources/Server/deactivated_plugins/OldPlugin/main.lua").write_text("print(2)")
    (src / "ServerConfig.toml").write_text(
        '[Misc]\nImScaredOfUpdates = false\n[General]\nName = "SpeeMP"\nPort = 30814\nAuthKey = "k"\n'
        'Map = "/levels/utah/info.json"\nMaxCars = 100\nResourceFolder = "Resources"\n'
    )
    scan = client.get("/api/import/scan").json()
    assert scan["mounted"] and len(scan["servers"]) == 1
    found = scan["servers"][0]
    assert (found["name"], found["mods"], found["mods_disabled"], found["plugins"]) == ("SpeeMP", 2, 1, 2)

    r = client.post("/api/import", json={"path": found["path"]})
    assert r.status_code == 202, r.text
    sid = r.json()["id"]
    _wait(client, r.json()["job"])
    mods_ = {m["name"]: m["enabled"] for m in client.get(f"/api/servers/{sid}/mods").json()}
    assert mods_ == {"car.zip": True, "off.zip": True, "old.zip": False}
    plugins = {p["name"]: p["enabled"] for p in client.get(f"/api/servers/{sid}/plugins").json()}
    assert plugins == {"Live": True, "OldPlugin": False}
    cfg = client.get(f"/api/servers/{sid}/config").json()["values"]
    assert cfg["MaxCars"] == 100 and cfg["AuthKey"] == "k" and cfg["Map"] == "/levels/utah/info.json"
    assert (src / "Resources/Client/car.zip").exists()  # source untouched

    # Template from the imported server, then a new server from it, then a clone.
    job = client.post("/api/templates", json={"server_id": sid, "name": "Utah drift"}).json()
    t = _wait(client, job)["result"]
    assert (t["mods"], t["plugins"], t["includes_auth_key"]) == (3, 2, False)
    r = client.post("/api/servers", json={"name": "From template", "template_id": t["id"], "auth_key": "new"})
    assert r.status_code == 201, r.text
    _wait(client, r.json()["job"])
    new_id = r.json()["id"]
    cfg = client.get(f"/api/servers/{new_id}/config").json()["values"]
    assert cfg["Name"] == "From template" and cfg["AuthKey"] == "new" and cfg["MaxCars"] == 100
    assert len(client.get(f"/api/servers/{new_id}/mods").json()) == 3

    r = client.post("/api/servers", json={"name": "Clone", "clone_from": sid})
    _wait(client, r.json()["job"])
    clone_cfg = client.get(f"/api/servers/{r.json()['id']}/config").json()["values"]
    assert clone_cfg["AuthKey"] == "k" and clone_cfg["Name"] == "Clone"

    # Export → import round trip.
    exported = client.get(f"/api/templates/{t['id']}/export")
    assert exported.status_code == 200
    r = client.post("/api/templates/import", files={"file": ("t.zip", exported.content, "application/zip")})
    assert r.status_code == 201, r.text
    assert r.json()["mods"] == 3 and r.json()["name"] == "Utah drift"
    assert client.post("/api/templates/import", files={"file": ("x.zip", _zip_bytes({"a": "b"}), "application/zip")}).status_code == 422


def test_plugin_layout_detection(tmp_path):
    def tree(files):
        root = tmp_path / str(len(list(tmp_path.iterdir())))
        for name, data in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)
        return root

    plan = repo_github.analyze(tree({"Repo-main/Resources/Server/Cobalt/main.lua": "", "Repo-main/README.md": ""}), "Repo")
    assert [n for n, _ in plan["plugins"]] == ["Cobalt"]
    plan = repo_github.analyze(tree({"main.lua": "", "lib/x.lua": ""}), "Nickel")
    assert [n for n, _ in plan["plugins"]] == ["Nickel"]
    plan = repo_github.analyze(tree({"r/Core/Core.lua": "", "r/Chat/Chat.lua": "", "r/Interface/lua/ge/extensions/x.lua": "", "r/.github/w.yml": ""}), "BJ")
    assert sorted(n for n, _ in plan["plugins"]) == ["Chat", "Core"]
    assert [n for n, _ in plan["client_dirs"]] == ["Interface"]
