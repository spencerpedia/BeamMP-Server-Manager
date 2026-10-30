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


def test_discord_webhook_url():
    from app.services.discord import WEBHOOK_RE

    assert WEBHOOK_RE.match("https://discord.com/api/webhooks/123/abc_DEF-1")
    assert WEBHOOK_RE.match("https://canary.discordapp.com/api/webhooks/123/abc")
    assert not WEBHOOK_RE.match("http://discord.com/api/webhooks/123/abc")
    assert not WEBHOOK_RE.match("https://evil.com/api/webhooks/123/abc")
    assert not WEBHOOK_RE.match("https://discord.com.evil.com/api/webhooks/123/abc")


def test_discord_build_embed():
    from app.services.discord import BLUE, GREEN, RED, build_embed

    def text(msg, prev=None, max_players=None):
        built = build_embed("Srv", msg, prev, max_players)
        return built and (built[0], built[1]["description"], built[1]["color"])

    assert text({"type": "state", "state": "running", "version": "v3.4"}) == ("status", "**Server started** (v3.4)", GREEN)
    assert text({"type": "state", "state": "stopped"}, "stopping")[1] == "**Server stopped**"
    assert text({"type": "state", "state": "stopped"}, "starting") is None  # failed start has its own event
    assert text({"type": "state", "state": "starting"}) is None
    assert text({"type": "state", "state": "crashed"}, "running")[2] == RED
    assert text({"type": "notify", "event": "crash_limit"})[0] == "status"
    assert text({"type": "notify", "event": "join", "name": "a_b*", "count": 3}, max_players=8) == (
        "players",
        "**a\\_b\\*** joined (3/8)",
        BLUE,
    )
    assert text({"type": "notify", "event": "leave", "name": "x", "count": 0})[1] == "**x** left (0)"
    sched = {"type": "notify", "event": "schedule", "action": "backup", "name": "", "result": "error: disk", "ok": False}
    assert text(sched) == ("tasks", "**Scheduled backup**: error: disk", RED)
    assert text({"type": "stats"}) is None
