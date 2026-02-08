"""FastAPI application factory — mounts admin UI and API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from gemsieve.web.admin import create_admin
from gemsieve.web.db import engine

_WEB_DIR = Path(__file__).parent
_TEMPLATES_DIR = str(_WEB_DIR / "templates")
_STATIC_DIR = str(_WEB_DIR / "static")


def create_app() -> FastAPI:
    """Build the FastAPI application with admin and API."""
    app = FastAPI(title="GemSieve Admin", version="0.1.0")

    # Mount static files
    app.mount("/static/custom", StaticFiles(directory=_STATIC_DIR), name="custom-static")

    # Set up starlette-admin
    admin = create_admin(engine, templates_dir=_TEMPLATES_DIR)

    # Import and register custom views (lazy to avoid circular imports)
    from gemsieve.web.views.dashboard import DashboardView
    from gemsieve.web.views.pipeline import PipelineView
    from gemsieve.web.views.ai_inspector import AIInspectorView
    from gemsieve.web.views.gem_explorer import GemExplorerView

    admin.add_view(DashboardView(
        label="Dashboard",
        icon="fa fa-tachometer-alt",
        path="/dashboard",
        template_path="dashboard.html",
    ))
    admin.add_view(PipelineView(
        label="Pipeline",
        icon="fa fa-cogs",
        path="/pipeline",
        template_path="pipeline.html",
    ))
    admin.add_view(AIInspectorView(
        label="AI Inspector",
        icon="fa fa-microscope",
        path="/ai-inspector",
        template_path="ai_inspector.html",
    ))
    admin.add_view(GemExplorerView(
        label="Gem Explorer",
        icon="fa fa-gem",
        path="/gem-explorer",
        template_path="gem_explorer.html",
    ))

    admin.mount_to(app)

    # Import and mount API router
    from gemsieve.web.api import router as api_router
    app.include_router(api_router, prefix="/api")

    # Redirect root to admin
    @app.get("/")
    async def _root():
        return RedirectResponse(url="/admin")

    return app
