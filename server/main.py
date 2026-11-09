"""The FastAPI application."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server import export_api, game_api, jobs_api, lab_api, reveal_api
from server.jobs import QueueFull


ROOT = Path(__file__).resolve().parent.parent
DEMAND_TABLE = ROOT / "benchmarks" / "results" / "demand_table.json"
WEB_DIST = ROOT / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="RoRo Yield Optimizer")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/demand-table")
    def demand_table() -> dict:
        if not DEMAND_TABLE.exists():
            raise HTTPException(404, "The demand table has not been generated.")
        return json.loads(DEMAND_TABLE.read_text(encoding="utf-8"))

    @app.exception_handler(game_api.InvalidDecision)
    def invalid_decision(_: Request, exc: game_api.InvalidDecision) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(QueueFull)
    def queue_full(_: Request, __: QueueFull) -> JSONResponse:
        return JSONResponse({"detail": jobs_api.BUSY_MESSAGE}, status_code=429)

    app.include_router(game_api.router)
    app.include_router(jobs_api.router)
    app.include_router(reveal_api.router)
    app.include_router(lab_api.router)
    app.include_router(export_api.router)
    if (WEB_DIST / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def single_page_app(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "Not found.")
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()
