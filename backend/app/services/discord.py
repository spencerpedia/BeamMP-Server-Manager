"""Optional Discord notifications: posts server events to each server's webhook, if one is set up."""

import asyncio
import contextlib
import logging
import re
from datetime import datetime, timezone

import httpx

from ..db import SessionLocal
from ..models import Server, ServerNotification
from . import server_config
from .process_manager import CRASH_LIMIT, CRASH_WINDOW, manager

log = logging.getLogger(__name__)

EVENT_GROUPS = ("status", "players", "tasks")
WEBHOOK_RE = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")
USERNAME = "BeamMP Server Manager"
BATCH_DELAY = 2  # seconds to collect a burst of events into one request
MAX_EMBEDS = 10  # Discord's per-message limit

GREEN, GREY, RED, BLUE = 0x22C55E, 0x64748B, 0xEF4444, 0x3B82F6
_MD_RE = re.compile(r"([\\*_~`|>])")


def escape(text: str) -> str:
    return _MD_RE.sub(r"\\\1", text)


def _embed(server_name: str, text: str, color: int) -> dict:
    return {
        "description": text[:4000],
        "color": color,
        "footer": {"text": server_name[:200]},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_embed(server_name: str, msg: dict, prev_state: str | None, max_players: int | None = None):
    """Turns one bus message into (event group, embed), or None if it shouldn't be posted."""
    if msg.get("type") == "state":
        state = msg.get("state")
        if state == "running":
            version = f" ({msg['version']})" if msg.get("version") else ""
            return "status", _embed(server_name, f"**Server started**{version}", GREEN)
        if state == "stopped" and prev_state == "stopping":
            return "status", _embed(server_name, "**Server stopped**", GREY)
        if state == "crashed":
            return "status", _embed(server_name, "**Server crashed**", RED)
        return None
    if msg.get("type") != "notify":
        return None
    event = msg.get("event")
    if event == "start_failed":
        return "status", _embed(server_name, f"**Server failed to start**: {escape(msg.get('error', ''))}", RED)
    if event == "crash_limit":
        text = f"**Crashed {CRASH_LIMIT} times in {CRASH_WINDOW // 60} minutes**; not restarting automatically"
        return "status", _embed(server_name, text, RED)
    if event in ("join", "leave"):
        count = f"{msg.get('count', 0)}/{max_players}" if max_players else str(msg.get("count", 0))
        verb = "joined" if event == "join" else "left"
        return "players", _embed(server_name, f"**{escape(msg.get('name', ''))}** {verb} ({count})", BLUE)
    if event == "schedule":
        label = f" ({escape(msg['name'])})" if msg.get("name") else ""
        text = f"**Scheduled {msg.get('action', 'task')}**{label}: {escape(msg.get('result', ''))}"
        return "tasks", _embed(server_name, text, GREEN if msg.get("ok", True) else RED)
    if event in ("backup", "restore"):
        what = "Backup created" if event == "backup" else "Backup restored"
        return "tasks", _embed(server_name, f"**{what}** by {escape(msg.get('user', ''))}: `{msg.get('name', '')}`", GREEN)
    return None


async def post(client: httpx.AsyncClient, url: str, embeds: list[dict]) -> str | None:
    """Sends embeds to a webhook. Returns an error message, or None on success."""
    payload = {"username": USERNAME, "embeds": embeds, "allowed_mentions": {"parse": []}}
    for _ in range(3):
        try:
            r = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            return f"Couldn't reach Discord: {exc}"
        if r.status_code == 429:
            retry = 1.0
            with contextlib.suppress(Exception):
                retry = float(r.json().get("retry_after", 1))
            await asyncio.sleep(min(retry, 60))
            continue
        if r.is_success:
            return None
        return f"Discord returned HTTP {r.status_code}"
    return "Discord kept rate-limiting the webhook"


async def send_test(url: str, server_name: str) -> str | None:
    async with httpx.AsyncClient(timeout=10) as client:
        embed = _embed(server_name, "**Test message**: Discord notifications are working.", BLUE)
        return await post(client, url, [embed])


def _settings(server_id: int) -> tuple[str, set[str], str] | None:
    """(webhook url, enabled event groups, server name) if notifications are on for this server."""
    with SessionLocal() as db:
        row = db.get(ServerNotification, server_id)
        if row is None or not row.enabled or not row.webhook_url:
            return None
        server = db.get(Server, server_id)
        if server is None:
            return None
        return row.webhook_url, set(row.events.split(",")), server.name


def _max_players(server_id: int) -> int | None:
    try:
        return server_config.read_general(server_config.server_dir(server_id)).get("MaxPlayers")
    except Exception:  # noqa: BLE001  (the count is just shown without a maximum)
        return None


class Notifier:
    """Listens to the global event bus and posts matching events, one sender task per webhook."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._states: dict[int, str] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._senders: dict[str, asyncio.Task] = {}

    def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=10)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        tasks = [t for t in (self._task, *self._senders.values()) if t]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._client:
            await self._client.aclose()

    async def _run(self) -> None:
        q = manager.subscribe_global()
        try:
            while True:
                msg = await q.get()
                try:
                    self._handle(msg)
                except Exception:  # noqa: BLE001  (never let one bad event stop notifications)
                    log.exception("Discord notification failed")
        finally:
            manager.unsubscribe_global(q)

    def _handle(self, msg: dict) -> None:
        if msg.get("type") not in ("state", "notify"):
            return
        server_id = msg["server_id"]
        prev = self._states.get(server_id)
        if msg["type"] == "state":
            self._states[server_id] = msg["state"]
        settings = _settings(server_id)
        if settings is None:
            return
        url, groups, name = settings
        max_players = _max_players(server_id) if msg.get("event") in ("join", "leave") else None
        built = build_embed(name, msg, prev, max_players)
        if built is None or built[0] not in groups:
            return
        self._enqueue(url, built[1])

    def _enqueue(self, url: str, embed: dict) -> None:
        q = self._queues.setdefault(url, asyncio.Queue(maxsize=100))
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(embed)
        sender = self._senders.get(url)
        if sender is None or sender.done():
            self._senders[url] = asyncio.create_task(self._send_loop(url, q))

    async def _send_loop(self, url: str, q: asyncio.Queue) -> None:
        while True:
            batch = [await q.get()]
            await asyncio.sleep(BATCH_DELAY)
            while not q.empty() and len(batch) < MAX_EMBEDS:
                batch.append(q.get_nowait())
            error = await post(self._client, url, batch)
            if error:
                log.warning("Discord webhook post failed: %s", error)


notifier = Notifier()
