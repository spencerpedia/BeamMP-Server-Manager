import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import config
from .api import admin, auth_routes, backups, content, extras, players, schedules, servers, ws
from .db import SessionLocal, init_db
from .models import Server
from .services import control, scheduler
from .services.process_manager import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bmsm")


async def _autostart() -> None:
    with SessionLocal() as db:
        ids = list(db.scalars(select(Server.id).where(Server.autostart.is_(True))))
    for server_id in ids:
        try:
            await control.start(server_id)
        except Exception as exc:  # noqa: BLE001  (one bad server shouldn't block the rest)
            log.warning("Autostart of server %s failed: %s", server_id, exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_dirs()
    init_db()
    manager.spec_loader = control.launch_spec
    manager.start_stats_loop()
    scheduler.scheduler.start()
    scheduler.load_all()
    autostart = asyncio.create_task(_autostart())
    yield
    autostart.cancel()
    scheduler.scheduler.shutdown(wait=False)
    await manager.shutdown()


app = FastAPI(title="BeamMP Server Manager", lifespan=lifespan)
for r in (auth_routes, servers, content, players, backups, schedules, admin, extras, ws):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- SPA -----------------------------------------------------------------------------------

if (config.STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith(("api/", "ws/")):
        raise HTTPException(404)
    candidate = (config.STATIC_DIR / path).resolve()
    if path and candidate.is_file() and candidate.is_relative_to(config.STATIC_DIR.resolve()):
        return FileResponse(candidate)
    index = config.STATIC_DIR / "index.html"
    if not index.exists():
        return {"detail": "Frontend not built. Run `npm run build` in frontend/ or use the Docker image."}
    return FileResponse(index)
