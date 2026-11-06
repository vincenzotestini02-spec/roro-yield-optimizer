"""The FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server import game_api, jobs_api
from server.jobs import QueueFull


def create_app() -> FastAPI:
    app = FastAPI(title="RoRo Yield Optimizer")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(game_api.InvalidDecision)
    def invalid_decision(_: Request, exc: game_api.InvalidDecision) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(QueueFull)
    def queue_full(_: Request, __: QueueFull) -> JSONResponse:
        return JSONResponse({"detail": jobs_api.BUSY_MESSAGE}, status_code=429)

    app.include_router(game_api.router)
    app.include_router(jobs_api.router)
    return app


app = create_app()
