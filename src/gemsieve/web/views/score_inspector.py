"""Score Inspector CustomView — D3.js score decomposition drill-down."""

from __future__ import annotations

from sqlalchemy import func
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView

from gemsieve.web.db import SessionLocal
from gemsieve.web.models import Gem


class ScoreInspectorView(CustomView):
    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        domain = request.query_params.get("domain", "")
        session = SessionLocal()
        try:
            # Get scored domains for the selector dropdown
            scored_domains = (
                session.query(
                    Gem.sender_domain,
                    func.max(Gem.score).label("max_score"),
                )
                .filter(Gem.sender_domain.isnot(None), Gem.score.isnot(None))
                .group_by(Gem.sender_domain)
                .order_by(func.max(Gem.score).desc())
                .limit(50)
                .all()
            )
            domains = [
                {"domain": r[0], "max_score": r[1]} for r in scored_domains
            ]
        finally:
            session.close()

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": "Score Inspector",
                "selected_domain": domain,
                "scored_domains": domains,
            },
        )
