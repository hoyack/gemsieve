"""AI Inspector CustomView — prompt/IO viewer for AI audit trail."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView

from gemsieve.web.db import SessionLocal
from gemsieve.web.models import AiAuditLog


class AIInspectorView(CustomView):
    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        session = SessionLocal()
        try:
            # Get filter params
            stage_filter = request.query_params.get("stage", "")
            domain_filter = request.query_params.get("domain", "")
            page = int(request.query_params.get("page", "1"))
            per_page = 20

            q = session.query(AiAuditLog).order_by(AiAuditLog.created_at.desc())
            if stage_filter:
                q = q.filter(AiAuditLog.stage == stage_filter)
            if domain_filter:
                q = q.filter(AiAuditLog.sender_domain.contains(domain_filter))

            total = q.count()
            entries = q.offset((page - 1) * per_page).limit(per_page).all()

            entries_data = [
                {
                    "id": e.id, "pipeline_run_id": e.pipeline_run_id,
                    "stage": e.stage, "sender_domain": e.sender_domain,
                    "prompt_template": e.prompt_template,
                    "prompt_rendered": e.prompt_rendered,
                    "system_prompt": e.system_prompt,
                    "model_used": e.model_used,
                    "response_raw": e.response_raw,
                    "response_parsed": e.response_parsed,
                    "duration_ms": e.duration_ms,
                    "created_at": e.created_at,
                }
                for e in entries
            ]

            # Distinct stages for filter dropdown
            stages = [r[0] for r in session.query(AiAuditLog.stage).distinct().all() if r[0]]
        finally:
            session.close()

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": "AI Inspector",
                "entries": entries_data,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if total > 0 else 1,
                "stage_filter": stage_filter,
                "domain_filter": domain_filter,
                "stages": stages,
            },
        )
