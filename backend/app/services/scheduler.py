"""Cron-style scheduled tasks (restart, backup, console command, update) per server."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Schedule, Server, utcnow
from . import control, releases
from .process_manager import manager

log = logging.getLogger(__name__)

ACTIONS = ("restart", "start", "stop", "backup", "command", "update")
scheduler = AsyncIOScheduler()


def validate_cron(expr: str) -> None:
    CronTrigger.from_crontab(expr)  # raises ValueError


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


def sync_job(schedule: Schedule) -> None:
    job_id = _job_id(schedule.id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if schedule.enabled:
        scheduler.add_job(
            run_schedule,
            CronTrigger.from_crontab(schedule.cron),
            id=job_id,
            args=[schedule.id],
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )


def remove_job(schedule_id: int) -> None:
    if scheduler.get_job(_job_id(schedule_id)):
        scheduler.remove_job(_job_id(schedule_id))


def next_run(schedule_id: int):
    job = scheduler.get_job(_job_id(schedule_id))
    return job.next_run_time if job else None


async def run_schedule(schedule_id: int) -> str:
    with SessionLocal() as db:
        sched = db.get(Schedule, schedule_id)
        if sched is None:
            return "missing"
        server_id, action, payload, warn = sched.server_id, sched.action, sched.payload, sched.warn_minutes
        name = sched.name
    sp = manager.get(server_id)
    ok = True
    try:
        result = await _perform(server_id, action, payload, warn)
    except Exception as exc:  # noqa: BLE001  (recorded on the schedule)
        log.exception("Schedule %s failed", schedule_id)
        result, ok = f"error: {exc}", False
    sp.system_log(f"Scheduled {action}: {result}")
    sp.publish({"type": "notify", "event": "schedule", "action": action, "name": name, "result": result, "ok": ok})
    with SessionLocal() as db:
        sched = db.get(Schedule, schedule_id)
        if sched:
            sched.last_run = utcnow()
            sched.last_result = result[:500]
            db.commit()
    return result


async def _perform(server_id: int, action: str, payload: str, warn: int) -> str:
    sp = manager.get(server_id)
    if action == "backup":
        b = await control.backup(server_id, "scheduled")
        return f"created {b['name']}"
    if action == "command":
        if not sp.running:
            return "skipped (server not running)"
        for line in payload.splitlines():
            await sp.send(line)
        return "sent"
    if action == "start":
        await control.start(server_id)
        return "started"
    if action == "stop":
        await control.warn_players(server_id, warn, "stopping")
        await control.stop(server_id)
        return "stopped"
    if action == "restart":
        if not sp.running:
            return "skipped (server not running)"
        await control.warn_players(server_id, warn, "restarting")
        await control.restart(server_id)
        return "restarted"
    if action == "update":
        with SessionLocal() as db:
            server = db.get(Server, server_id)
            pinned = server.version if server else "latest"
        if pinned != "latest":
            return f"skipped (pinned to {pinned})"
        tag = await releases.latest_tag()
        if tag is None:
            return "skipped (no release info)"
        await releases.ensure_binary(tag)
        if not sp.running or sp.version == tag:
            return f"up to date ({tag})" if sp.version == tag else f"downloaded {tag}"
        await control.warn_players(server_id, warn, f"updating to {tag}")
        await control.restart(server_id)
        return f"updated to {tag}"
    return f"unknown action {action}"


def load_all() -> None:
    with SessionLocal() as db:
        for sched in db.scalars(select(Schedule).where(Schedule.enabled.is_(True))):
            try:
                sync_job(sched)
            except ValueError:
                log.warning("Schedule %s has an invalid cron expression %r", sched.id, sched.cron)
