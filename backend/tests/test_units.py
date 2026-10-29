import io
import zipfile

from app.services import bridge, maps, mods, server_config


def test_config_roundtrip_keeps_comments(tmp_path):
    server_config.create_default(tmp_path, "Test", 30815, "key")
    server_config.update_general(tmp_path, {"MaxPlayers": "12", "Private": False, "Port": 1})
    text = server_config.read_raw(tmp_path)
    assert "# Whether to allow guests" in text
    general = server_config.read_general(tmp_path)
    assert general["MaxPlayers"] == 12
    assert general["Private"] is False
    assert general["Port"] == 30815  # managed key ignored
    assert general["AuthKey"] == "key"


def test_enforce_managed(tmp_path):
    server_config.create_default(tmp_path, "Test", 30815)
    server_config.write_raw(tmp_path, server_config.read_raw(tmp_path).replace("Port = 30815", "Port = 1"))
    server_config.enforce_managed(tmp_path, 30816)
    assert server_config.read_general(tmp_path)["Port"] == 30816


def test_parse_bridge_lines():
    line = '[29/10/26 20:09:01] [LUA] [BMSM]{"n":0,"t":"hello"}\t'
    assert bridge.parse_line(line) == {"n": 0, "t": "hello"}
    assert bridge.parse_line('[LUA] [BMSM]{"players":{},"t":"players"}')["players"] == []
    assert bridge.parse_line("[INFO] normal line") is None
    assert bridge.parse_line("[BMSM]{not json}") is None


def test_maps_in_zip(tmp_path):
    client = tmp_path / "Resources" / "Client"
    client.mkdir(parents=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("levels/my_track/info.json", "{}")
        zf.writestr("levels/my_track/main.decals.json", "{}")
        zf.writestr("vehicles/car/car.jbeam", "{}")
    (client / "track.zip").write_bytes(buf.getvalue())
    assert mods.maps_in_zip(client / "track.zip") == ["my_track"]
    found = [m for m in maps.list_maps(tmp_path) if m["source"] == "track.zip"]
    assert found and found[0]["path"] == "/levels/my_track/info.json"
    mods.set_mod_enabled(tmp_path, "track.zip", False)
    assert mods.list_mods(tmp_path)[0]["enabled"] is False


def test_safe_name_strips_paths():
    assert mods.safe_name("../../etc/passwd") == "passwd"
    assert mods.safe_name("my mod (1).zip") == "my mod (1).zip"
