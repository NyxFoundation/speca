"""FastAPI app factory for the SPECA web backend.

The app is intentionally tiny in Slice 0. Other slices wire in routers via the
anchor comments below — each anchor reserves a stable location for a follow-up
patch so that parallel slices can land without conflicting with each other.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

# === routers: auth ===
from web.server.routers import auth
# === routers: runs ===
from web.server.routers import runs as runs_router
# === routers: findings ===
from web.server.routers import findings as findings_router
# === routers: integrations ===
from web.server.routers import integrations as integrations_router
# === routers: chat ===
from web.server.routers import chat as chat_router
# === routers: picker ===
from web.server.routers import picker as picker_router
# === routers: runs_ws ===
from web.server.routers import runs_ws as runs_ws_router
# === routers: diagnostics ===
from web.server.routers import diagnostics as diagnostics_router
# === routers: runtime ===
from web.server.routers import runtime as runtime_router

# === services: bootstrap ===
# Imported lazily inside the startup hook so importing ``main`` for the
# OpenAPI generator (which never executes lifespan events) does not need
# the supervisor's heavier deps. Keep the symbol references here so
# editors and graph-rs tools can still resolve the names.
from web.server.services import run_state as _run_state
from web.server.services import run_supervisor as _run_supervisor


def create_app() -> FastAPI:
    """Build the FastAPI application.

    The factory pattern keeps test setup ergonomic (one app per test) and
    makes the wiring of routers explicit so reviewers can see in one place
    which slices are landed.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # pragma: no cover - exercised via TestClient
        # === startup: reconcile orphans ===
        # On boot, walk ``.speca/runs/*/state.json`` and re-tag runs whose
        # owning supervisor process died. This is the only way the UI can
        # distinguish "still running" from "the box rebooted mid-audit".
        supervisor = _run_supervisor.get_run_supervisor()
        try:
            _run_state.reconcile_orphans(supervisor)
        except Exception:
            # Reconciliation failures must never block the API from
            # coming up — at worst the UI will show stale rows.
            import logging

            logging.getLogger(__name__).exception(
                "speca: reconcile_orphans failed during startup"
            )
        yield
        # Nothing to do on shutdown — the supervisor's runs intentionally
        # outlive uvicorn so a follow-up restart can resume from
        # state.json. Graceful cancel is a deliberate non-goal here.

    app = FastAPI(
        title="SPECA Web API",
        version="0.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # === include_router: auth ===
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    # === include_router: runs ===
    app.include_router(runs_router.router)
    # === include_router: findings ===
    app.include_router(findings_router.router)
    # === include_router: integrations ===
    app.include_router(
        integrations_router.router,
        prefix="/api/integrations",
        tags=["integrations"],
    )
    # === include_router: chat ===
    app.include_router(chat_router.router)
    # === include_router: picker ===
    app.include_router(picker_router.router)
    # === include_router: runs_ws ===
    app.include_router(runs_ws_router.router, prefix="/api")
    # === include_router: diagnostics ===
    app.include_router(diagnostics_router.router, prefix="/api", tags=["diagnostics"])
    # === include_router: runtime ===
    app.include_router(runtime_router.router)

    return app


app = create_app()
