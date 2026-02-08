"""TaskManager: pipeline stage execution via ThreadPoolExecutor."""

from __future__ import annotations

import json
import time
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from gemsieve.config import Config, load_config


class LoggingAIProvider:
    """Wraps an AIProvider to log every call to ai_audit_log."""

    def __init__(self, wrapped, db_conn: sqlite3.Connection, run_id: int, stage: str):
        self.wrapped = wrapped
        self.db_conn = db_conn
        self.run_id = run_id
        self.stage = stage

    def complete(self, prompt: str, model: str, system: str = "", response_format: str | None = None) -> dict:
        start = time.time()
        result = self.wrapped.complete(prompt, model, system, response_format)
        duration_ms = int((time.time() - start) * 1000)

        # Determine prompt template name by checking content
        template_name = "unknown"
        if "Classify this sender" in prompt:
            template_name = "CLASSIFICATION_PROMPT"
        elif "personalized engagement" in prompt:
            template_name = "ENGAGEMENT_PROMPT"

        # Extract sender domain from prompt if possible
        sender_domain = ""
        for line in prompt.splitlines():
            if line.startswith("SENDER:") and "<" in line:
                addr = line.split("<")[-1].rstrip(">").strip()
                if "@" in addr:
                    sender_domain = addr.split("@", 1)[1]
                break

        try:
            self.db_conn.execute(
                """INSERT INTO ai_audit_log
                   (pipeline_run_id, stage, sender_domain, prompt_template,
                    prompt_rendered, system_prompt, model_used,
                    response_raw, response_parsed, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.run_id,
                    self.stage,
                    sender_domain,
                    template_name,
                    prompt,
                    system,
                    model,
                    json.dumps(result) if isinstance(result, dict) else str(result),
                    json.dumps(result) if isinstance(result, dict) else str(result),
                    duration_ms,
                ),
            )
            self.db_conn.commit()
        except Exception:
            pass  # Don't let logging failures break the pipeline

        return result


# SSE event bus — threads post updates, SSE endpoint reads them
_event_listeners: list = []
_event_lock = threading.Lock()


def publish_event(event: dict) -> None:
    """Publish a pipeline event to all SSE listeners."""
    with _event_lock:
        for q in _event_listeners:
            q.append(event)


def subscribe_events() -> list:
    """Return a new event queue that receives pipeline events."""
    q: list = []
    with _event_lock:
        _event_listeners.append(q)
    return q


def unsubscribe_events(q: list) -> None:
    """Remove an event queue from the listener list."""
    with _event_lock:
        try:
            _event_listeners.remove(q)
        except ValueError:
            pass


# Stage name -> function mapping
STAGE_MAP = {
    "metadata": "_run_metadata",
    "content": "_run_content",
    "entities": "_run_entities",
    "classify": "_run_classify",
    "profile": "_run_profile",
    "segment": "_run_segment",
    "engage": "_run_engage",
}

STAGE_DESCRIPTIONS = {
    "metadata": "Stage 1: Header forensics & ESP fingerprinting",
    "content": "Stage 2: HTML parsing & offer detection",
    "entities": "Stage 3: NER & regex entity extraction",
    "classify": "Stage 4: AI classification",
    "profile": "Stage 5: Sender profiles & gem detection",
    "segment": "Stage 6: Segmentation & scoring",
    "engage": "Stage 7: Engagement draft generation",
}


class TaskManager:
    """Manages pipeline stage execution in background threads."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._active_runs: dict[int, Future] = {}
        self._config: Config | None = None

    def _get_config(self) -> Config:
        if self._config is None:
            self._config = load_config()
        return self._config

    def run_stage(self, stage_name: str, **kwargs) -> int:
        """Submit a pipeline stage to run in background. Returns run_id."""
        from gemsieve.database import get_db, init_db
        config = self._get_config()

        # Create pipeline_runs record
        conn = get_db(config)
        init_db(conn)
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """INSERT INTO pipeline_runs (stage, status, created_at, triggered_by, config_snapshot)
               VALUES (?, 'pending', ?, 'web', ?)""",
            (stage_name, now, json.dumps({"model": f"{config.ai.provider}:{config.ai.model}"})),
        )
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        future = self.executor.submit(self._execute_stage, run_id, stage_name, **kwargs)
        self._active_runs[run_id] = future
        return run_id

    def _execute_stage(self, run_id: int, stage_name: str, **kwargs):
        """Runs in background thread."""
        from gemsieve.database import get_db, init_db
        config = self._get_config()
        conn = get_db(config)
        init_db(conn)

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE pipeline_runs SET status = 'running', started_at = ? WHERE id = ?",
            (now, run_id),
        )
        conn.commit()

        publish_event({"type": "stage_started", "run_id": run_id, "stage": stage_name})

        try:
            count = self._call_stage(conn, stage_name, config, run_id, **kwargs)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE pipeline_runs SET status = 'completed', completed_at = ?,
                   items_processed = ? WHERE id = ?""",
                (now, count, run_id),
            )
            conn.commit()
            publish_event({
                "type": "stage_completed", "run_id": run_id,
                "stage": stage_name, "items_processed": count,
            })
        except Exception as e:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE pipeline_runs SET status = 'failed', completed_at = ?,
                   error_message = ? WHERE id = ?""",
                (now, str(e), run_id),
            )
            conn.commit()
            publish_event({
                "type": "stage_failed", "run_id": run_id,
                "stage": stage_name, "error": str(e),
            })
        finally:
            conn.close()

    def _call_stage(self, conn, stage_name: str, config: Config, run_id: int, **kwargs) -> int:
        """Dispatch to the appropriate stage function. Returns items processed."""
        if stage_name == "metadata":
            from gemsieve.stages.metadata import extract_metadata
            return extract_metadata(conn, esp_rules_path=config.esp_fingerprints_file)

        elif stage_name == "content":
            from gemsieve.stages.content import parse_content
            return parse_content(conn)

        elif stage_name == "entities":
            from gemsieve.stages.entities import extract_entities
            return extract_entities(conn, spacy_model=config.entity_extraction.spacy_model)

        elif stage_name == "classify":
            from gemsieve.stages.classify import classify_messages
            model_spec = f"{config.ai.provider}:{config.ai.model}"
            # Patch get_provider to wrap with logging
            import gemsieve.ai as ai_module
            original_get_provider = ai_module.get_provider

            def logging_get_provider(spec, config=None):
                provider, model_name = original_get_provider(spec, config)
                return LoggingAIProvider(provider, conn, run_id, "classify"), model_name

            ai_module.get_provider = logging_get_provider
            try:
                return classify_messages(
                    conn, model_spec=model_spec,
                    batch_size=config.ai.batch_size,
                    max_body_chars=config.ai.max_body_chars,
                    ai_config=config.ai.to_provider_dict(),
                    use_crew=kwargs.get("use_crew", False),
                )
            finally:
                ai_module.get_provider = original_get_provider

        elif stage_name == "profile":
            from gemsieve.stages.profile import build_profiles, detect_gems
            count = build_profiles(conn)
            count += detect_gems(conn)
            return count

        elif stage_name == "segment":
            from gemsieve.stages.segment import assign_segments, score_gems
            count = assign_segments(conn)
            count += score_gems(conn, config=config.scoring)
            return count

        elif stage_name == "engage":
            from gemsieve.stages.engage import generate_engagement
            model_spec = f"{config.ai.provider}:{config.ai.model}"
            # Patch with logging provider
            import gemsieve.ai as ai_module
            original_get_provider = ai_module.get_provider

            def logging_get_provider(spec, config=None):
                provider, model_name = original_get_provider(spec, config)
                return LoggingAIProvider(provider, conn, run_id, "engage"), model_name

            ai_module.get_provider = logging_get_provider
            try:
                gem_id = kwargs.get("gem_id")
                return generate_engagement(
                    conn, model_spec=model_spec,
                    gem_id=gem_id,
                    engagement_config=config.engagement,
                    ai_config=config.ai.to_provider_dict(),
                    use_crew=kwargs.get("use_crew", False),
                )
            finally:
                ai_module.get_provider = original_get_provider

        else:
            raise ValueError(f"Unknown stage: {stage_name}")

    def get_status(self, run_id: int) -> dict | None:
        """Get current status of a pipeline run."""
        from gemsieve.database import get_db, init_db
        config = self._get_config()
        conn = get_db(config)
        init_db(conn)
        row = conn.execute(
            "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)


# Global singleton
task_manager = TaskManager()
