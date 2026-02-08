"""Gem Explorer CustomView — rich gem cards with filtering."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView

from gemsieve.web.db import SessionLocal
from gemsieve.web.models import Gem, SenderProfile, SenderSegment


class GemExplorerView(CustomView):
    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        session = SessionLocal()
        try:
            # Filters
            type_filter = request.query_params.get("type", "")
            status_filter = request.query_params.get("status", "")
            min_score = request.query_params.get("min_score", "")
            sort_by = request.query_params.get("sort", "score_desc")

            q = session.query(Gem)
            if type_filter:
                q = q.filter(Gem.gem_type == type_filter)
            if status_filter:
                q = q.filter(Gem.status == status_filter)
            if min_score:
                q = q.filter(Gem.score >= int(min_score))

            if sort_by == "score_desc":
                q = q.order_by(Gem.score.desc())
            elif sort_by == "score_asc":
                q = q.order_by(Gem.score.asc())
            elif sort_by == "newest":
                q = q.order_by(Gem.created_at.desc())
            else:
                q = q.order_by(Gem.score.desc())

            gems = q.limit(100).all()

            # Build rich gem data
            gem_cards = []
            for g in gems:
                profile = (
                    session.query(SenderProfile)
                    .filter(SenderProfile.sender_domain == g.sender_domain)
                    .first()
                )
                explanation = {}
                try:
                    explanation = json.loads(g.explanation) if g.explanation else {}
                except (json.JSONDecodeError, TypeError):
                    pass

                actions = []
                try:
                    actions = json.loads(g.recommended_actions) if g.recommended_actions else []
                except (json.JSONDecodeError, TypeError):
                    pass

                signals = explanation.get("signals", [])

                gem_cards.append({
                    "id": g.id,
                    "gem_type": g.gem_type,
                    "sender_domain": g.sender_domain,
                    "company_name": profile.company_name if profile else None,
                    "industry": profile.industry if profile else None,
                    "score": g.score or 0,
                    "status": g.status,
                    "summary": explanation.get("summary", ""),
                    "signals": signals,
                    "actions": actions,
                    "created_at": g.created_at,
                })

            # Get distinct gem types for filter
            gem_types = [
                r[0] for r in session.query(Gem.gem_type).distinct().all() if r[0]
            ]
            gem_statuses = [
                r[0] for r in session.query(Gem.status).distinct().all() if r[0]
            ]
        finally:
            session.close()

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": "Gem Explorer",
                "gems": gem_cards,
                "gem_types": gem_types,
                "gem_statuses": gem_statuses,
                "type_filter": type_filter,
                "status_filter": status_filter,
                "min_score": min_score,
                "sort_by": sort_by,
                "total": len(gem_cards),
            },
        )
