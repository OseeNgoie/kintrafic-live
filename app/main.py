from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app import db as database
from app.errors import ApiError, api_error_handler
from app.routers import admin, alerts, billing, pages, reports, session, tiles, traffic
from app.seed import bootstrap_data
from app.jobs import run_tick
from app.veille import maybe_run_veille


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.tile_cache_dir).mkdir(parents=True, exist_ok=True)
    app.state.db_ready = False
    stop = asyncio.Event()

    def boot() -> None:
        database.wait_for_db()
        database.enable_postgis()
        database.Base.metadata.create_all(bind=database.engine)
        session = database.SessionLocal()
        try:
            bootstrap_data(session)
            maybe_run_veille(session)
        finally:
            session.close()
        app.state.db_ready = True
        print("kintrafic-live: schema and seed ready", flush=True)

    boot_task = asyncio.create_task(asyncio.to_thread(boot))

    async def ticker():
        try:
            await boot_task
        except Exception as exc:  # noqa: BLE001
            print(f"kintrafic-live: boot failed: {exc}", flush=True)
            return
        while not stop.is_set():
            try:
                db2 = database.SessionLocal()
                try:
                    run_tick(db2)
                finally:
                    db2.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=60)
            except asyncio.TimeoutError:
                continue

    tick_task = asyncio.create_task(ticker())
    # Yield immediately so uvicorn already listens on PORT (/health) during DB wait/create.
    yield
    stop.set()
    tick_task.cancel()
    if not boot_task.done():
        boot_task.cancel()


app = FastAPI(title="KinTrafic Live", lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(pages.router)
app.include_router(session.router)
app.include_router(reports.router)
app.include_router(alerts.router)
app.include_router(billing.router)
app.include_router(admin.router)
app.include_router(tiles.router)
app.include_router(traffic.router)


@app.get("/health")
def health(request: Request):
    return {
        "ok": True,
        "service": "kintrafic-live",
        "db": bool(getattr(request.app.state, "db_ready", False)),
    }


@app.get("/admin")
def admin_root():
    return RedirectResponse("/admin/login")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "server", "message": "Erreur serveur. Réessaie."}},
        )
    raise exc
