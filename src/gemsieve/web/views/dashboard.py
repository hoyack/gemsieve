"""Dashboard CustomView — stats cards + Chart.js graphs."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView

from gemsieve.web.db import SessionLocal
from gemsieve.web.models import (
    AiAuditLog,
    AiClassification,
    EngagementDraft,
    ExtractedEntity,
    Gem,
    Message,
    ParsedContent,
    ParsedMetadata,
    PipelineRun,
    SenderProfile,
    SenderSegment,
    Thread,
)


class DashboardView(CustomView):
    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        session = SessionLocal()
        try:
            stats = {
                "messages": session.query(Message).count(),
                "threads": session.query(Thread).count(),
                "metadata": session.query(ParsedMetadata).count(),
                "content": session.query(ParsedContent).count(),
                "entities": session.query(ExtractedEntity).count(),
                "classifications": session.query(AiClassification).count(),
                "profiles": session.query(SenderProfile).count(),
                "gems": session.query(Gem).count(),
                "segments": session.query(SenderSegment).count(),
                "drafts": session.query(EngagementDraft).count(),
                "pipeline_runs": session.query(PipelineRun).count(),
                "ai_calls": session.query(AiAuditLog).count(),
            }

            # Pipeline health: which stages have data
            pipeline_health = {
                "metadata": stats["metadata"],
                "content": stats["content"],
                "entities": stats["entities"],
                "classify": stats["classifications"],
                "profile": stats["profiles"],
                "segment": stats["segments"],
                "engage": stats["drafts"],
            }

            # Recent pipeline runs
            recent_runs = (
                session.query(PipelineRun)
                .order_by(PipelineRun.created_at.desc())
                .limit(10)
                .all()
            )
            recent_runs_data = [
                {
                    "id": r.id, "stage": r.stage, "status": r.status,
                    "started_at": r.started_at, "completed_at": r.completed_at,
                    "items_processed": r.items_processed,
                    "error_message": r.error_message,
                }
                for r in recent_runs
            ]
        finally:
            session.close()

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": "Dashboard",
                "stats": stats,
                "pipeline_health": pipeline_health,
                "recent_runs": recent_runs_data,
            },
        )
