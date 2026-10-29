import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, current_user, server_access
from ..db import get_db
from ..models import Schedule, Server, User
from ..services import scheduler

router = APIRouter(prefix="/api/servers/{server_id}/schedules", tags=["schedules"])


class ScheduleIn(BaseModel):
    name: str = Field("", max_length=128)
    action: str
    cron: str = Field(min_length=9, max_length=64)
    payload: str = Field("", max_length=4000)
    warn_minutes: int = Field(0, ge=0, le=60)
    enabled: bool = True


def schedule_out(s: Schedule) -> dict:
    nxt = scheduler.next_run(s.id)
    return {
        "id": s.id,
        "name": s.name,
        "action": s.action,
        "cron": s.cron,
        "payload": s.payload,
        "warn_minutes": s.warn_minutes,
        "enabled": s.enabled,
        "last_run": s.last_run.isoformat() if s.last_run else None,
        "last_result": s.last_result,
        "next_run": nxt.isoformat() if nxt else None,
    }


def _validate(body: ScheduleIn) -> None:
    if body.action not in scheduler.ACTIONS:
        raise HTTPException(422, f"Action must be one of {', '.join(scheduler.ACTIONS)}")
    if body.action == "command" and not body.payload.strip():
        raise HTTPException(422, "A command schedule needs a console command")
    try:
        scheduler.validate_cron(body.cron)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid cron expression: {exc}") from exc


def _get(db: Session, server: Server, schedule_id: int) -> Schedule:
    sched = db.get(Schedule, schedule_id)
    if sched is None or sched.server_id != server.id:
        raise HTTPException(404, "Schedule not found")
    return sched


@router.get("")
def list_schedules(server: Server = Depends(server_access("viewer")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Schedule).where(Schedule.server_id == server.id).order_by(Schedule.id))
    return [schedule_out(s) for s in rows]


@router.post("", status_code=201)
def create_schedule(
    body: ScheduleIn,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _validate(body)
    sched = Schedule(server_id=server.id, **body.model_dump())
    db.add(sched)
    db.commit()
    scheduler.sync_job(sched)
    audit(db, user, "schedule_create", f"{body.action} @ {body.cron}", server.id)
    return schedule_out(sched)


@router.put("/{schedule_id}")
def update_schedule(
    schedule_id: int,
    body: ScheduleIn,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _validate(body)
    sched = _get(db, server, schedule_id)
    for key, value in body.model_dump().items():
        setattr(sched, key, value)
    db.commit()
    scheduler.sync_job(sched)
    audit(db, user, "schedule_update", f"{body.action} @ {body.cron}", server.id)
    return schedule_out(sched)


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    sched = _get(db, server, schedule_id)
    scheduler.remove_job(sched.id)
    db.delete(sched)
    db.commit()
    audit(db, user, "schedule_delete", f"#{schedule_id}", server.id)
    return {"ok": True}


@router.post("/{schedule_id}/run")
async def run_now(
    schedule_id: int,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    sched = _get(db, server, schedule_id)
    # Runs in the background so a long warning countdown doesn't hold the request open.
    asyncio.create_task(scheduler.run_schedule(sched.id))
    audit(db, user, "schedule_run", f"#{schedule_id}", server.id)
    return {"ok": True}
