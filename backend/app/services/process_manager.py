"""Runs BeamMP-Server instances as child processes and fans their output out to subscribers."""

import asyncio
import contextlib
import logging
import re
import time
from collections import deque
from dataclasses import dataclass

import psutil

from . import bridge, releases, server_config

log = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
STOP_TIMEOUT = 20
STATS_INTERVAL = 2
CRASH_WINDOW = 300  # seconds
CRASH_LIMIT = 3  # auto-restarts allowed per window


@dataclass
class LaunchSpec:
    server_id: int
    port: int
    version: str
    auto_restart: bool
    bans: list[dict]


class ServerProcess:
    def __init__(self, manager: "ProcessManager", server_id: int):
        self.manager = manager
        self.server_id = server_id
        self.proc: asyncio.subprocess.Process | None = None
        self.state = "stopped"  # stopped | starting | running | stopping | crashed
        self.version: str | None = None
        self.started_at: float | None = None
        self.log: deque[str] = deque(maxlen=3000)
        self.chat: deque[dict] = deque(maxlen=500)
        self.players: list[dict] = []
        self.stats: deque[dict] = deque(maxlen=900)  # 30 min at 2s
        self.subscribers: set[asyncio.Queue] = set()
        self._spec: LaunchSpec | None = None
        self._reader: asyncio.Task | None = None
        self._ps: psutil.Process | None = None
        self._crashes: deque[float] = deque()
        self._lock = asyncio.Lock()

    # ---- pub/sub -------------------------------------------------------------------------

    def publish(self, msg: dict) -> None:
        msg.setdefault("server_id", self.server_id)
        for q in list(self.subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(msg)
        if msg["type"] != "log":
            self.manager.publish_global(msg)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def _set_state(self, state: str) -> None:
        self.state = state
        self.publish({"type": "state", "state": state, "version": self.version})

    def _append_log(self, line: str) -> None:
        self.log.append(line)
        self.publish({"type": "log", "line": line})

    def system_log(self, text: str) -> None:
        self._append_log(f"\x1b[36m[MANAGER]\x1b[0m {text}")

    # ---- lifecycle -----------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    def summary(self) -> dict:
        return {
            "state": self.state,
            "version_running": self.version,
            "uptime": int(time.time() - self.started_at) if self.started_at and self.running else 0,
            "players": self.players,
            "stats": self.stats[-1] if self.stats and self.running else None,
        }

    async def start(self, spec: LaunchSpec) -> None:
        async with self._lock:
            if self.running:
                return
            self._spec = spec
            self._set_state("starting")
            try:
                await self._spawn(spec)
            except Exception as exc:
                self.system_log(f"Failed to start: {exc}")
                self._set_state("stopped")
                raise

    async def _spawn(self, spec: LaunchSpec) -> None:
        sdir = server_config.server_dir(spec.server_id)
        self.system_log(f"Preparing BeamMP-Server ({spec.version})…")
        binary = await releases.ensure_binary(spec.version)
        self.version = binary.parent.name
        server_config.enforce_managed(sdir, spec.port)
        bridge.install(sdir)
        bridge.write_bans(sdir, spec.bans)
        self.players = []
        self.system_log(f"Starting BeamMP-Server {self.version} on port {spec.port}")
        self.proc = await asyncio.create_subprocess_exec(
            str(binary),
            cwd=str(sdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=1 << 20,
            start_new_session=True,
        )
        self.started_at = time.time()
        self._ps = psutil.Process(self.proc.pid)
        self._ps.cpu_percent()  # prime the counter
        self._reader = asyncio.create_task(self._read_output(self.proc))
        self._set_state("running")

    async def _read_output(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:  # line longer than the limit
                continue
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            plain = ANSI_RE.sub("", line)
            event = bridge.parse_line(plain)
            if event is not None:
                self._handle_bridge(event)
            elif plain.startswith("> bmsm "):
                continue  # BeamMP echoing the manager's own bridge commands
            else:
                self._append_log(line)
        rc = await proc.wait()
        await self._on_exit(rc)

    async def _on_exit(self, rc: int) -> None:
        self.proc = None
        self._ps = None
        self.players = []
        self.publish({"type": "players", "players": []})
        if self.state == "stopping":
            self.system_log(f"Server stopped (exit code {rc})")
            self._set_state("stopped")
            return
        self.system_log(f"\x1b[31mServer exited unexpectedly (exit code {rc})\x1b[0m")
        self._set_state("crashed")
        spec = self._spec
        if spec is None or not spec.auto_restart:
            return
        now = time.time()
        while self._crashes and now - self._crashes[0] > CRASH_WINDOW:
            self._crashes.popleft()
        if len(self._crashes) >= CRASH_LIMIT:
            self.system_log(f"Crashed {CRASH_LIMIT} times in {CRASH_WINDOW // 60} minutes; not restarting automatically")
            return
        self._crashes.append(now)
        self.system_log("Auto-restarting in 5 seconds…")
        await asyncio.sleep(5)
        if self.state == "crashed":
            # Re-read the spec from the DB so config changes (and bans) since the crash apply.
            fresh = self.manager.spec_loader(self.server_id) if self.manager.spec_loader else spec
            with contextlib.suppress(Exception):
                await self.start(fresh or spec)

    def _handle_bridge(self, event: dict) -> None:
        kind = event.get("t")
        if kind == "players":
            self.players = event["players"]
            self.publish({"type": "players", "players": self.players})
        elif kind == "join":
            event.pop("t")
            self.players = [p for p in self.players if p.get("id") != event.get("id")] + [event]
            self.system_log(f"{event.get('name')} joined")
            self.publish({"type": "players", "players": self.players})
        elif kind == "leave":
            self.players = [p for p in self.players if p.get("id") != event.get("id")]
            self.system_log(f"{event.get('name')} left")
            self.publish({"type": "players", "players": self.players})
        elif kind == "chat":
            msg = {"ts": time.time(), "name": event.get("name", ""), "message": event.get("message", "")}
            self.chat.append(msg)
            self.publish({"type": "chat", **msg})
        elif kind == "ban_reject":
            self.system_log(f"Rejected banned player {event.get('name')}")

    async def send(self, command: str) -> None:
        if not self.running or self.proc is None or self.proc.stdin is None:
            raise RuntimeError("Server is not running")
        command = command.replace("\r", "").replace("\n", " ").strip()
        if not command:
            return
        self.proc.stdin.write((command + "\n").encode())
        await self.proc.stdin.drain()

    async def stop(self) -> None:
        async with self._lock:
            proc = self.proc
            if proc is None or proc.returncode is not None:
                self._set_state("stopped")
                return
            self._set_state("stopping")
            with contextlib.suppress(Exception):
                await self.send("exit")
            try:
                try:
                    await asyncio.wait_for(asyncio.shield(proc.wait()), 5)
                except asyncio.TimeoutError:
                    # BeamMP can finish shutting down but stay blocked reading its console; EOF releases it.
                    if proc.stdin is not None:
                        proc.stdin.close()
                    await asyncio.wait_for(proc.wait(), STOP_TIMEOUT)
            except asyncio.TimeoutError:
                self.system_log("Graceful shutdown timed out; terminating")
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 10)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    await proc.wait()
            if self._reader:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self._reader, 5)

    async def restart(self, spec: LaunchSpec) -> None:
        await self.stop()
        await self.start(spec)

    def sample_stats(self) -> None:
        if self._ps is None:
            return
        try:
            with self._ps.oneshot():
                cpu = self._ps.cpu_percent()
                mem = self._ps.memory_info().rss
        except psutil.Error:
            return
        point = {"ts": int(time.time()), "cpu": round(cpu, 1), "mem": mem, "players": len(self.players)}
        self.stats.append(point)
        uptime = int(time.time() - self.started_at) if self.started_at else 0
        self.publish({"type": "stats", "uptime": uptime, **point})


class ProcessManager:
    def __init__(self):
        self.servers: dict[int, ServerProcess] = {}
        self.global_subscribers: set[asyncio.Queue] = set()
        self.spec_loader = None  # callable(server_id) -> LaunchSpec | None, set by main
        self._stats_task: asyncio.Task | None = None

    def get(self, server_id: int) -> ServerProcess:
        if server_id not in self.servers:
            self.servers[server_id] = ServerProcess(self, server_id)
        return self.servers[server_id]

    def publish_global(self, msg: dict) -> None:
        for q in list(self.global_subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(msg)

    def subscribe_global(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.global_subscribers.add(q)
        return q

    def unsubscribe_global(self, q: asyncio.Queue) -> None:
        self.global_subscribers.discard(q)

    def start_stats_loop(self) -> None:
        self._stats_task = asyncio.create_task(self._stats_loop())

    async def _stats_loop(self) -> None:
        while True:
            await asyncio.sleep(STATS_INTERVAL)
            for sp in list(self.servers.values()):
                sp.sample_stats()

    async def forget(self, server_id: int) -> None:
        sp = self.servers.pop(server_id, None)
        if sp:
            await sp.stop()

    async def shutdown(self) -> None:
        if self._stats_task:
            self._stats_task.cancel()
        await asyncio.gather(*(sp.stop() for sp in self.servers.values()), return_exceptions=True)


manager = ProcessManager()
