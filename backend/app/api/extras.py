"""Mod/plugin browsers, templates, importing existing servers, and background job status."""

import asyncio
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config
from ..auth import audit, can_access, current_user, require_admin, server_access
from ..db import SessionLocal, get_db
from ..models import Server, User
from ..services import importer, jobs, provision, repo_beamng, repo_github, server_config, templates
from ..services.process_manager import manager
from .servers import _port_error, server_out

router = APIRouter(prefix="/api", tags=["extras"])


def _upstream_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(502, f"Upstream returned {exc.response.status_code}")
    return HTTPException(502, str(exc) or "Upstream request failed")


def _audit_async(username: str, action: str, detail: str, server_id: int | None) -> None:
    with SessionLocal() as db:
        audit(db, username, action, detail, server_id)


# ---- jobs ----------------------------------------------------------------------------------


@router.get("/jobs")
def list_jobs(server_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for job in jobs.recent(50):
        if server_id is not None and job.server_id != server_id:
            continue
        if user.role != "admin" and job.username != user.username and not (
            job.server_id and can_access(user, job.server_id, "viewer", db)
        ):
            continue
        out.append(job.out())
    return out


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if user.role != "admin" and job.username != user.username and not (job.server_id and can_access(user, job.server_id, "viewer", db)):
        raise HTTPException(403, "No access to this job")
    return job.out()


# ---- BeamNG.com mods -----------------------------------------------------------------------


class ModInstall(BaseModel):
    resource: str = Field(min_length=1, max_length=500)  # id or beamng.com URL


@router.get("/browse/mods/meta")
def mod_browse_meta(_: User = Depends(current_user)):
    return {"categories": repo_beamng.CATEGORIES, "orders": repo_beamng.ORDERS}


@router.get("/browse/mods")
async def browse_mods(category: str = "", order: str = "download_count", page: int = 1, _: User = Depends(current_user)):
    try:
        return await repo_beamng.browse(category, order, page)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise _upstream_error(exc) from exc


@router.get("/browse/mods/{resource_id}")
async def mod_details(resource_id: int, _: User = Depends(current_user)):
    try:
        return await repo_beamng.details(resource_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise _upstream_error(exc) from exc


@router.post("/servers/{server_id}/mods/install")
async def install_mod(body: ModInstall, server: Server = Depends(server_access("operator")), user: User = Depends(current_user)):
    try:
        rid = repo_beamng.parse_resource_id(body.resource)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    sdir = server_config.server_dir(server.id)
    username, sid = user.username, server.id

    async def run(job):
        result = await repo_beamng.install(sdir, rid, job)
        _audit_async(username, "mod_install", f"{result['title']} {result['version']} ({result['name']})", sid)
        result["restart_required"] = manager.get(sid).running
        return result

    return jobs.start("mod_install", f"Installing BeamNG.com mod #{rid}", user.username, run, server.id).out()


@router.post("/servers/{server_id}/mods/check-updates")
async def check_mod_updates(server: Server = Depends(server_access("viewer"))):
    meta = repo_beamng.read_meta(server_config.server_dir(server.id))
    results = []
    for filename, entry in meta.items():
        try:
            info = await repo_beamng.details(entry["id"])
        except (httpx.HTTPError, RuntimeError, LookupError) as exc:
            results.append({"name": filename, "error": str(exc)})
            continue
        results.append(
            {
                "name": filename,
                "id": entry["id"],
                "installed": entry.get("version"),
                "latest": info["version"],
                "update": info["version"] != entry.get("version"),
            }
        )
    return results


# ---- GitHub plugins ------------------------------------------------------------------------


class PluginInstall(BaseModel):
    repo: str = Field(min_length=3, max_length=300)


@router.get("/browse/plugins/featured")
async def featured_plugins(_: User = Depends(current_user)):
    return await repo_github.featured()


@router.get("/browse/plugins")
async def search_plugins(q: str = "", page: int = 1, _: User = Depends(current_user)):
    try:
        return await repo_github.search(q, page)
    except (httpx.HTTPError, RuntimeError) as exc:
        raise _upstream_error(exc) from exc


@router.post("/servers/{server_id}/plugins/install")
async def install_plugin(body: PluginInstall, server: Server = Depends(server_access("operator")), user: User = Depends(current_user)):
    try:
        repo = repo_github.parse_repo(body.repo)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    sdir = server_config.server_dir(server.id)
    username, sid = user.username, server.id

    async def run(job):
        result = await repo_github.install(sdir, repo, job)
        _audit_async(username, "plugin_install", f"{repo} ({result['source']}): {', '.join(result['plugins'] + result['mods'])}", sid)
        result["restart_required"] = manager.get(sid).running
        return result

    return jobs.start("plugin_install", f"Installing {repo}", user.username, run, server.id).out()


# ---- templates -----------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    server_id: int
    name: str = Field(min_length=1, max_length=128)
    description: str = Field("", max_length=1000)
    include_auth_key: bool = False


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=1000)


def _template_or_404(template_id: str) -> dict:
    try:
        return templates.get(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Template not found") from exc


@router.get("/templates")
def list_templates(_: User = Depends(current_user)):
    return templates.list_templates()


@router.post("/templates", status_code=202)
async def create_template(body: TemplateCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    server = db.get(Server, body.server_id)
    if server is None:
        raise HTTPException(404, "Server not found")
    username = user.username

    async def run(job):
        def progress(frac, done, total):
            job.update(progress=frac, message=f"Copying {done // 2**20}/{total // 2**20} MB")

        result = await asyncio.to_thread(templates.create_from_server, server, body.name, body.description, body.include_auth_key, progress)
        _audit_async(username, "template_create", f"{result['name']} from {server.name}", server.id)
        return result

    return jobs.start("template_create", f"Saving template '{body.name}'", user.username, run, server.id).out()


@router.patch("/templates/{template_id}")
def update_template(template_id: str, body: TemplateUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _template_or_404(template_id)
    result = templates.update(template_id, body.name, body.description)
    audit(db, user, "template_update", result["name"])
    return result


@router.delete("/templates/{template_id}")
def delete_template(template_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = _template_or_404(template_id)
    templates.delete(template_id)
    audit(db, user, "template_delete", t["name"])
    return {"ok": True}


@router.get("/templates/{template_id}/export")
async def export_template(template_id: str, background: BackgroundTasks, _: User = Depends(require_admin)):
    t = _template_or_404(template_id)
    path = await asyncio.to_thread(templates.export_zip, template_id)
    background.add_task(path.unlink, missing_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in t["name"])[:60] or "template"
    return FileResponse(path, filename=f"{safe}.bmsm-template.zip", media_type="application/zip", background=background)


@router.post("/templates/import", status_code=201)
async def import_template(file: UploadFile, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    templates.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".zip", dir=templates.TEMPLATES_DIR)
    tmp = Path(tmp_name)
    try:
        with open(fd, "wb") as fh:
            while chunk := await file.read(1 << 20):
                fh.write(chunk)
        result = await asyncio.to_thread(templates.import_zip, tmp)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001  (bad zips raise several types)
        raise HTTPException(422, f"Couldn't read that file: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
    audit(db, user, "template_import", result["name"])
    return result


# ---- import existing servers ---------------------------------------------------------------


class ImportRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    name: str | None = Field(None, max_length=128)
    port: int | None = None


@router.get("/import/scan")
async def scan_imports(_: User = Depends(require_admin)):
    return await asyncio.to_thread(importer.scan)


@router.post("/import", status_code=202)
async def import_server(body: ImportRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        general = importer.source_general(body.path)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    name = (body.name or general.get("Name") or Path(body.path).name or "Imported server").strip()
    try:
        port = body.port or provision.next_free_port(db, general.get("Port"))
        server = provision.create_record(db, name, port, "latest", str(general.get("AuthKey") or ""))
    except provision.PortError as exc:
        raise _port_error(exc) from exc
    sdir = server_config.server_dir(server.id)
    username, sid, rel = user.username, server.id, body.path
    provision.busy.add(sid)

    async def run(job):
        def progress(frac, done, total):
            job.update(progress=frac, message=f"Copying {done // 2**20}/{total // 2**20} MB")

        try:
            result = await asyncio.to_thread(importer.copy_into, rel, sdir, progress)
            server_config.update_general(sdir, {"Name": name})
        finally:
            provision.busy.discard(sid)
        _audit_async(username, "server_import", f"{rel} → {name}: {result['mods']} mods, {result['plugins']} plugins", sid)
        return {"server_id": sid, **result}

    job = jobs.start("import", f"Importing {rel} as {name}", user.username, run, sid)
    audit(db, user, "server_create", f"{name} on port {port} (import)", sid)
    return {**server_out(server, user, db), "job": job.out()}


@router.get("/import/status")
def import_status(_: User = Depends(require_admin)):
    return {"mounted": importer.IMPORT_DIR.is_dir(), "path": str(importer.IMPORT_DIR), "data": str(config.DATA_DIR)}
