"""WebSockets: per-server console/events and a dashboard feed of state, stats and players."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..auth import can_access, ws_user
from ..db import SessionLocal
from ..models import ServerGrant
from ..services.process_manager import manager

router = APIRouter()


async def _pump(websocket: WebSocket, queue: asyncio.Queue, allowed=None) -> None:
    """Forwards queued events until the client disconnects."""

    async def drain_client():
        # We don't accept input over the socket (commands go through REST), but must read to notice closes.
        while True:
            await websocket.receive_text()

    reader = asyncio.create_task(drain_client())
    try:
        while True:
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({getter, reader}, return_when=asyncio.FIRST_COMPLETED)
            if reader in done:
                getter.cancel()
                break
            msg = getter.result()
            if allowed is None or msg.get("server_id") in allowed:
                await websocket.send_json(msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            await reader


@router.websocket("/ws/servers/{server_id}")
async def server_socket(websocket: WebSocket, server_id: int):
    user = ws_user(websocket)
    with SessionLocal() as db:
        ok = user is not None and can_access(user, server_id, "viewer", db)
    if not ok:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    sp = manager.get(server_id)
    queue = sp.subscribe()
    try:
        await websocket.send_json({"type": "hello", "server_id": server_id, **sp.summary(), "log": list(sp.log)})
        await _pump(websocket, queue)
    finally:
        sp.unsubscribe(queue)


@router.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket):
    user = ws_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    allowed = None
    if user.role != "admin":
        with SessionLocal() as db:
            allowed = set(db.scalars(select(ServerGrant.server_id).where(ServerGrant.user_id == user.id)))
    await websocket.accept()
    queue = manager.subscribe_global()
    try:
        await _pump(websocket, queue, allowed)
    finally:
        manager.unsubscribe_global(queue)
