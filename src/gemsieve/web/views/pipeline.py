"""Pipeline Control CustomView — trigger stages, monitor progress."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView

from gemsieve.web.db import SessionLocal
from gemsieve.web.models import (
    AiClassification,
    EngagementDraft,
    ExtractedEntity,
    ParsedContent,
    ParsedMetadata,
    PipelineRun,
    SenderProfile,
    SenderSegment,
)
from gemsieve.web.tasks import STAGE_DESCRIPTIONS


class PipelineView(CustomView):
    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        session = SessionLocal()
        try:
            table_map = {
                "metadata": ParsedMetadata,
                "content": ParsedContent,
                "entities": ExtractedEntity,
                "classify": AiClassification,
                "profile": SenderProfile,
                "segment": SenderSegment,
                "engage": EngagementDraft,
            }

            stages = []
            for name, desc in STAGE_DESCRIPTIONS.items():
                model = table_map.get(name)
                count = session.query(model).count() if model else 0
                last_run = (
                    session.query(PipelineRun)
                    .filter(PipelineRun.stage == name)
                    .order_by(PipelineRun.created_at.desc())
                    .first()
                )
                stages.append({
                    "name": name,
                    "description": desc,
                    "row_count": count,
                    "last_run": {
                        "id": last_run.id,
                        "status": last_run.status,
                        "started_at": last_run.started_at,
                        "completed_at": last_run.completed_at,
                        "items_processed": last_run.items_processed,
                        "error_message": last_run.error_message,
                    } if last_run else None,
                })

            # Run history
            runs = (
                session.query(PipelineRun)
                .order_by(PipelineRun.created_at.desc())
                .limit(30)
                .all()
            )
            run_history = [
                {
                    "id": r.id, "stage": r.stage, "status": r.status,
                    "started_at": r.started_at, "completed_at": r.completed_at,
                    "items_processed": r.items_processed,
                    "error_message": r.error_message,
                    "triggered_by": r.triggered_by,
                }
                for r in runs
            ]
        finally:
            session.close()

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": "Pipeline Control",
                "stages": stages,
                "run_history": run_history,
            },
        )
