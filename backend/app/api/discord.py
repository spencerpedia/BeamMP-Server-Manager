"""Per-server Discord webhook settings (operators only, since the webhook URL is a secret)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import audit, current_user, server_access
from ..db import get_db
from ..models import Server, ServerNotification, User
from ..services import discord

router = APIRouter(prefix="/api/servers/{server_id}/discord", tags=["discord"])


class DiscordSettings(BaseModel):
    webhook_url: str = Field("", max_length=512)
    enabled: bool = False
    events: list[str] = list(discord.EVENT_GROUPS)


class DiscordTest(BaseModel):
    webhook_url: str | None = Field(None, max_length=512)


def _check_url(url: str) -> None:
    if not discord.WEBHOOK_RE.match(url):
        raise HTTPException(422, "That isn't a Discord webhook URL (https://discord.com/api/webhooks/…)")


@router.get("")
def get_settings(server: Server = Depends(server_access("operator")), db: Session = Depends(get_db)):
    row = db.get(ServerNotification, server.id)
    if row is None:
        return DiscordSettings().model_dump()
    return {"webhook_url": row.webhook_url, "enabled": row.enabled, "events": [e for e in row.events.split(",") if e]}


@router.put("")
def save_settings(
    body: DiscordSettings,
    server: Server = Depends(server_access("operator")),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    url = body.webhook_url.strip()
    if url:
        _check_url(url)
    elif body.enabled:
        raise HTTPException(422, "Add a webhook URL before turning notifications on")
    unknown = set(body.events) - set(discord.EVENT_GROUPS)
    if unknown:
        raise HTTPException(422, f"Unknown event types: {', '.join(sorted(unknown))}")
    row = db.get(ServerNotification, server.id) or ServerNotification(server_id=server.id)
    row.webhook_url = url
    row.enabled = body.enabled
    row.events = ",".join(e for e in discord.EVENT_GROUPS if e in body.events)
    db.add(row)
    db.commit()
    state = f"on ({row.events or 'no events'})" if row.enabled else "off"
    audit(db, user, "discord_update", state, server.id)
    return {"webhook_url": row.webhook_url, "enabled": row.enabled, "events": [e for e in row.events.split(",") if e]}


@router.post("/test")
async def send_test(body: DiscordTest, server: Server = Depends(server_access("operator")), db: Session = Depends(get_db)):
    url = (body.webhook_url or "").strip()
    if not url:
        row = db.get(ServerNotification, server.id)
        url = row.webhook_url if row else ""
    if not url:
        raise HTTPException(422, "Add a webhook URL first")
    _check_url(url)
    error = await discord.send_test(url, server.name)
    if error:
        raise HTTPException(502, error)
    return {"ok": True}
