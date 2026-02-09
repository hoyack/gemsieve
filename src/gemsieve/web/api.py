"""REST API routes for pipeline control, stats, and SSE."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

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
from gemsieve.web.tasks import (
    STAGE_DESCRIPTIONS,
    STAGE_MAP,
    publish_event,
    subscribe_events,
    task_manager,
    unsubscribe_events,
)

router = APIRouter(tags=["api"])


@router.post("/pipeline/run/{stage}")
async def run_pipeline_stage(stage: str, retrain: bool = False):
    """Trigger a pipeline stage. Returns the run_id."""
    if stage not in STAGE_MAP and stage != "all":
        raise HTTPException(400, f"Unknown stage: {stage}. Options: {list(STAGE_MAP.keys())}")

    if stage == "all":
        # Run stages 1-6 sequentially (skip engage)
        run_ids = []
        for s in ["metadata", "content", "entities", "classify", "profile", "segment"]:
            kwargs = {}
            if s == "classify" and retrain:
                kwargs["retrain"] = True
            rid = task_manager.run_stage(s, **kwargs)
            run_ids.append(rid)
        return {"status": "submitted", "run_ids": run_ids, "stages": list(STAGE_MAP.keys())[:6]}

    kwargs = {}
    if stage == "classify" and retrain:
        kwargs["retrain"] = True
    run_id = task_manager.run_stage(stage, **kwargs)
    return {"status": "submitted", "run_id": run_id, "stage": stage}


@router.get("/pipeline/status/{run_id}")
async def get_pipeline_status(run_id: int):
    """Get the status of a pipeline run."""
    status = task_manager.get_status(run_id)
    if status is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return status


@router.get("/pipeline/runs")
async def list_pipeline_runs(limit: int = 20):
    """List recent pipeline runs."""
    session = SessionLocal()
    try:
        runs = (
            session.query(PipelineRun)
            .order_by(PipelineRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id, "stage": r.stage, "status": r.status,
                "started_at": r.started_at, "completed_at": r.completed_at,
                "items_processed": r.items_processed,
                "error_message": r.error_message,
                "triggered_by": r.triggered_by,
                "created_at": r.created_at,
            }
            for r in runs
        ]
    finally:
        session.close()


@router.get("/pipeline/stream")
async def pipeline_event_stream():
    """SSE endpoint for live pipeline updates."""
    queue = subscribe_events()

    async def event_generator():
        try:
            while True:
                if queue:
                    event = queue.pop(0)
                    yield {"event": event.get("type", "message"), "data": json.dumps(event)}
                else:
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            unsubscribe_events(queue)
            raise

    return EventSourceResponse(event_generator())


@router.get("/stats")
async def get_stats():
    """Dashboard statistics."""
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
        return stats
    finally:
        session.close()


@router.get("/stats/gems-by-type")
async def gems_by_type():
    """Gem type distribution for charts."""
    session = SessionLocal()
    try:
        from sqlalchemy import func
        rows = (
            session.query(Gem.gem_type, func.count(Gem.id).label("count"))
            .group_by(Gem.gem_type)
            .all()
        )
        return [{"gem_type": r[0], "count": r[1]} for r in rows]
    finally:
        session.close()


@router.get("/stats/gems-top/{n}")
async def top_gems(n: int = 10):
    """Top N gems by score."""
    session = SessionLocal()
    try:
        rows = (
            session.query(Gem)
            .order_by(Gem.score.desc())
            .limit(n)
            .all()
        )
        result = []
        for g in rows:
            explanation = {}
            try:
                explanation = json.loads(g.explanation) if g.explanation else {}
            except (json.JSONDecodeError, TypeError):
                pass
            result.append({
                "id": g.id, "gem_type": g.gem_type,
                "sender_domain": g.sender_domain,
                "score": g.score, "status": g.status,
                "estimated_value": explanation.get("estimated_value", ""),
                "urgency": explanation.get("urgency", ""),
            })
        return result
    finally:
        session.close()


@router.get("/stats/gems-top-stacked/{n}")
async def top_gems_stacked(n: int = 10):
    """Top N domains by total gem score, with per-gem-type breakdown."""
    session = SessionLocal()
    try:
        from sqlalchemy import func

        # 1. Top N domains by total score
        top_domains = (
            session.query(
                Gem.sender_domain,
                func.sum(Gem.score).label("total"),
            )
            .filter(Gem.sender_domain.isnot(None), Gem.score.isnot(None))
            .group_by(Gem.sender_domain)
            .order_by(func.sum(Gem.score).desc())
            .limit(n)
            .all()
        )
        domains = [r[0] for r in top_domains]
        if not domains:
            return {"domains": [], "gem_types": [], "datasets": {}, "gem_ids": {}}

        # 2. All gems for those domains, grouped by domain + gem_type
        rows = (
            session.query(
                Gem.sender_domain,
                Gem.gem_type,
                func.sum(Gem.score).label("type_score"),
                # highest-scoring gem id per group (for click target)
                func.max(Gem.id).label("best_id"),
            )
            .filter(Gem.sender_domain.in_(domains), Gem.score.isnot(None))
            .group_by(Gem.sender_domain, Gem.gem_type)
            .all()
        )

        # Build lookup: (domain, gem_type) -> (score, gem_id)
        lookup: dict[tuple[str, str], tuple[int, int]] = {}
        gem_types_set: set[str] = set()
        for r in rows:
            lookup[(r[0], r[1])] = (int(r[2]), int(r[3]))
            gem_types_set.add(r[1])

        gem_types = sorted(gem_types_set)

        # 3. Build parallel arrays
        datasets: dict[str, list[int]] = {gt: [] for gt in gem_types}
        gem_ids: dict[str, list[int | None]] = {gt: [] for gt in gem_types}
        for domain in domains:
            for gt in gem_types:
                entry = lookup.get((domain, gt))
                datasets[gt].append(entry[0] if entry else 0)
                gem_ids[gt].append(entry[1] if entry else None)

        return {
            "domains": domains,
            "gem_types": gem_types,
            "datasets": datasets,
            "gem_ids": gem_ids,
        }
    finally:
        session.close()


@router.get("/stats/by-industry")
async def by_industry():
    """Industry breakdown for charts."""
    session = SessionLocal()
    try:
        from sqlalchemy import func
        rows = (
            session.query(
                AiClassification.industry,
                func.count(AiClassification.message_id).label("count"),
            )
            .filter(AiClassification.industry.isnot(None), AiClassification.industry != "")
            .group_by(AiClassification.industry)
            .order_by(func.count(AiClassification.message_id).desc())
            .all()
        )
        return [{"industry": r[0], "count": r[1]} for r in rows]
    finally:
        session.close()


@router.get("/stats/by-esp")
async def by_esp():
    """ESP distribution for charts."""
    session = SessionLocal()
    try:
        from sqlalchemy import func
        rows = (
            session.query(
                ParsedMetadata.esp_identified,
                func.count(ParsedMetadata.message_id).label("count"),
            )
            .filter(ParsedMetadata.esp_identified.isnot(None))
            .group_by(ParsedMetadata.esp_identified)
            .order_by(func.count(ParsedMetadata.message_id).desc())
            .all()
        )
        return [{"esp": r[0], "count": r[1]} for r in rows]
    finally:
        session.close()


@router.get("/stats/pipeline-activity")
async def pipeline_activity():
    """Pipeline activity timeline."""
    session = SessionLocal()
    try:
        runs = (
            session.query(PipelineRun)
            .order_by(PipelineRun.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": r.id, "stage": r.stage, "status": r.status,
                "started_at": r.started_at, "created_at": r.created_at,
                "items_processed": r.items_processed,
            }
            for r in runs
        ]
    finally:
        session.close()


@router.get("/stages")
async def list_stages():
    """List all available pipeline stages with descriptions and row counts."""
    session = SessionLocal()
    try:
        stage_info = []
        table_map = {
            "metadata": ParsedMetadata,
            "content": ParsedContent,
            "entities": ExtractedEntity,
            "classify": AiClassification,
            "profile": SenderProfile,
            "segment": SenderSegment,
            "engage": EngagementDraft,
        }
        for name, desc in STAGE_DESCRIPTIONS.items():
            model = table_map.get(name)
            count = session.query(model).count() if model else 0
            # Last run for this stage
            last_run = (
                session.query(PipelineRun)
                .filter(PipelineRun.stage == name)
                .order_by(PipelineRun.created_at.desc())
                .first()
            )
            stage_info.append({
                "name": name,
                "description": desc,
                "row_count": count,
                "last_run": {
                    "id": last_run.id,
                    "status": last_run.status,
                    "started_at": last_run.started_at,
                    "completed_at": last_run.completed_at,
                    "items_processed": last_run.items_processed,
                } if last_run else None,
            })
        return stage_info
    finally:
        session.close()


@router.post("/gems/{gem_id}/generate")
async def generate_for_gem(gem_id: int):
    """Trigger engagement generation for a specific gem."""
    session = SessionLocal()
    try:
        gem = session.query(Gem).filter(Gem.id == gem_id).first()
        if not gem:
            raise HTTPException(404, f"Gem {gem_id} not found")
    finally:
        session.close()

    run_id = task_manager.run_stage("engage", gem_id=gem_id)
    return {"status": "submitted", "run_id": run_id, "gem_id": gem_id}


@router.get("/ai-audit")
async def list_ai_audit(stage: str | None = None, limit: int = 50, offset: int = 0):
    """List AI audit log entries."""
    session = SessionLocal()
    try:
        q = session.query(AiAuditLog).order_by(AiAuditLog.created_at.desc())
        if stage:
            q = q.filter(AiAuditLog.stage == stage)
        total = q.count()
        rows = q.offset(offset).limit(limit).all()
        return {
            "total": total,
            "items": [
                {
                    "id": r.id, "pipeline_run_id": r.pipeline_run_id,
                    "stage": r.stage, "sender_domain": r.sender_domain,
                    "prompt_template": r.prompt_template,
                    "model_used": r.model_used, "duration_ms": r.duration_ms,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
        }
    finally:
        session.close()


@router.get("/ai-audit/{audit_id}")
async def get_ai_audit_detail(audit_id: int):
    """Get full AI audit log entry."""
    session = SessionLocal()
    try:
        r = session.query(AiAuditLog).filter(AiAuditLog.id == audit_id).first()
        if not r:
            raise HTTPException(404, f"Audit entry {audit_id} not found")
        return {
            "id": r.id, "pipeline_run_id": r.pipeline_run_id,
            "stage": r.stage, "sender_domain": r.sender_domain,
            "prompt_template": r.prompt_template,
            "prompt_rendered": r.prompt_rendered,
            "system_prompt": r.system_prompt,
            "model_used": r.model_used,
            "response_raw": r.response_raw,
            "response_parsed": r.response_parsed,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at,
        }
    finally:
        session.close()
