"""GemSieve CLI — Typer app with all subcommands."""

from __future__ import annotations

import json
from typing import Optional

import typer

app = typer.Typer(
    name="gemsieve",
    help="Gmail inbox intelligence pipeline — extract gems from your inbox.",
    no_args_is_help=True,
)

# --- Database commands ---

db_app = typer.Typer(help="Database management commands.")
app.add_typer(db_app, name="db")


@db_app.callback(invoke_without_command=True)
def db_callback(
    ctx: typer.Context,
    reset: bool = typer.Option(False, "--reset", help="Wipe and recreate the database."),
    stats: bool = typer.Option(False, "--stats", help="Show row counts for all tables."),
    migrate: bool = typer.Option(False, "--migrate", help="Run pending schema migrations."),
):
    """Database management."""
    from gemsieve.config import load_config
    from gemsieve.database import db_stats, get_db, init_db, reset_db

    config = load_config()

    if reset:
        conn = reset_db(config)
        typer.echo("Database reset and initialized.")
        conn.close()
        return

    if stats:
        conn = get_db(config)
        init_db(conn)
        s = db_stats(conn)
        typer.echo("Table row counts:")
        for table, count in s.items():
            status = f"{count}" if count >= 0 else "missing"
            typer.echo(f"  {table:30s} {status}")
        conn.close()
        return

    if migrate:
        conn = get_db(config)
        init_db(conn)
        typer.echo("Schema migrations applied.")
        conn.close()
        return

    # No flags — show help
    ctx.get_help()


# --- Ingestion commands ---

@app.command()
def ingest(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Gmail search query."),
    sync: bool = typer.Option(False, "--sync", help="Run incremental sync."),
    append: bool = typer.Option(False, "--append", help="Append to existing data."),
):
    """Ingest messages from Gmail (Stage 0)."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.gmail.auth import get_gmail_service, get_user_email
    from gemsieve.gmail.client import GmailClient
    from gemsieve.gmail.sync import SyncEngine

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    typer.echo("Authenticating with Gmail...")
    service = get_gmail_service(config)
    user_email = get_user_email(service)
    typer.echo(f"Authenticated as: {user_email}")

    client = GmailClient(service, user_email)
    engine = SyncEngine(client, conn)

    def progress(current, total, stored):
        typer.echo(f"  [{current}/{total}] {stored} new messages stored")

    if sync:
        typer.echo("Running incremental sync...")
        result = engine.incremental_sync(progress_callback=progress)
        if result == -1:
            typer.echo("History expired. Running full sync instead...")
            search_query = query or config.gmail.default_query
            result = engine.full_sync(search_query, progress_callback=progress)
        typer.echo(f"Sync complete: {result} new messages.")
    else:
        search_query = query or config.gmail.default_query
        typer.echo(f"Full sync with query: {search_query}")
        result = engine.full_sync(search_query, progress_callback=progress)
        typer.echo(f"Ingestion complete: {result} new messages stored.")

    conn.close()


# --- Parse commands ---

@app.command()
def parse(
    stage: str = typer.Option(..., "--stage", "-s", help="Stage to run: metadata, content, entities"),
):
    """Run a parsing stage (Stages 1-3)."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    if stage == "metadata":
        from gemsieve.stages.metadata import extract_metadata
        count = extract_metadata(conn, esp_rules_path=config.esp_fingerprints_file)
        typer.echo(f"Metadata extraction complete: {count} messages processed.")

    elif stage == "content":
        from gemsieve.stages.content import parse_content
        count = parse_content(conn)
        typer.echo(f"Content parsing complete: {count} messages processed.")

    elif stage == "entities":
        from gemsieve.stages.entities import extract_entities
        count = extract_entities(conn, spacy_model=config.entity_extraction.spacy_model)
        typer.echo(f"Entity extraction complete: {count} messages processed.")

    else:
        typer.echo(f"Unknown stage: {stage}. Use: metadata, content, entities", err=True)
        raise typer.Exit(1)

    conn.close()


def _resolve_model(model_arg: str | None, config) -> str:
    """Resolve the model spec from CLI arg or config.

    If the user passed --model, use that. Otherwise build from config
    (which includes .env overrides).
    """
    if model_arg:
        return model_arg
    return f"{config.ai.provider}:{config.ai.model}"


# --- Classify command ---

@app.command()
def classify(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model spec (provider:model). Default: from config/env."),
    batch_size: int = typer.Option(10, "--batch-size", "-b", help="Messages per batch."),
    crew: bool = typer.Option(False, "--crew", help="Use CrewAI multi-agent mode."),
):
    """Run AI classification (Stage 4)."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.stages.classify import classify_messages

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    model_spec = _resolve_model(model, config)
    mode = "CrewAI" if crew else "direct"
    typer.echo(f"Classifying with model: {model_spec} ({mode} mode)")
    count = classify_messages(conn, model_spec=model_spec, batch_size=batch_size,
                              max_body_chars=config.ai.max_body_chars,
                              ai_config=config.ai.to_provider_dict(),
                              use_crew=crew)
    typer.echo(f"Classification complete: {count} messages classified.")
    conn.close()


# --- Override commands ---

@app.command()
def override(
    sender: Optional[str] = typer.Option(None, "--sender", help="Sender domain to override."),
    message: Optional[str] = typer.Option(None, "--message", help="Message ID to override."),
    field: str = typer.Option(..., "--field", "-f", help="Field name to override."),
    value: str = typer.Option(..., "--value", "-v", help="New value."),
):
    """Add a classification override."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.overrides import add_override

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    override_id = add_override(conn, field_name=field, corrected_value=value,
                                sender_domain=sender, message_id=message)
    typer.echo(f"Override #{override_id} created.")
    conn.close()


@app.command()
def overrides(
    list_all: bool = typer.Option(False, "--list", help="List all overrides."),
    show_stats: bool = typer.Option(False, "--stats", help="Show override statistics."),
):
    """Manage classification overrides."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.overrides import list_overrides, override_stats

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    if list_all:
        items = list_overrides(conn)
        if not items:
            typer.echo("No overrides found.")
        else:
            for item in items:
                scope = item.get("override_scope", "")
                target = item.get("sender_domain") or item.get("message_id") or ""
                typer.echo(
                    f"  #{item['id']} [{scope}] {target}: "
                    f"{item['field_name']} = {item['corrected_value']} "
                    f"(was: {item.get('original_value', 'unknown')})"
                )

    if show_stats:
        stats = override_stats(conn)
        if not stats:
            typer.echo("No overrides to analyze.")
        else:
            for field, data in stats.items():
                flag = " ⚠ NEEDS TUNING" if data["needs_tuning"] else ""
                typer.echo(
                    f"  {field}: {data['total_overrides']} overrides / "
                    f"{data['total_classifications']} total = "
                    f"{data['override_rate']}%{flag}"
                )

    conn.close()


# --- Profile commands ---

@app.command()
def profile():
    """Build sender profiles (Stage 5)."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.stages.profile import build_profiles

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    count = build_profiles(conn)
    typer.echo(f"Profile building complete: {count} profiles built.")
    conn.close()


# --- Gems commands ---

@app.command()
def gems(
    list_all: bool = typer.Option(False, "--list", help="List all gems."),
    gem_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by gem type."),
    segment: Optional[str] = typer.Option(None, "--segment", help="Filter by segment."),
    top: Optional[int] = typer.Option(None, "--top", help="Show top N gems."),
    explain: Optional[int] = typer.Option(None, "--explain", help="Show full explanation for a gem ID."),
):
    """View detected gems."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.stages.profile import detect_gems

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    if explain is not None:
        row = conn.execute("SELECT * FROM gems WHERE id = ?", (explain,)).fetchone()
        if not row:
            typer.echo(f"Gem #{explain} not found.")
            raise typer.Exit(1)
        explanation = json.loads(row["explanation"]) if row["explanation"] else {}
        typer.echo(f"Gem #{row['id']} — {row['gem_type']}")
        typer.echo(f"  Domain: {row['sender_domain']}")
        typer.echo(f"  Score:  {row['score']}")
        typer.echo(f"  Status: {row['status']}")
        typer.echo(f"  Summary: {explanation.get('summary', 'N/A')}")
        signals = explanation.get("signals", [])
        if signals:
            typer.echo("  Signals:")
            for s in signals:
                typer.echo(f"    - {s.get('signal', '')}: {s.get('evidence', '')}")
        actions = json.loads(row["recommended_actions"]) if row["recommended_actions"] else []
        if actions:
            typer.echo("  Recommended actions:")
            for a in actions:
                typer.echo(f"    - {a}")
        conn.close()
        return

    # If no flags, detect gems first
    if not list_all and gem_type is None and segment is None and top is None:
        count = detect_gems(conn)
        typer.echo(f"Gem detection complete: {count} gems detected.")
        conn.close()
        return

    # Build query
    query = "SELECT g.*, sp.company_name FROM gems g LEFT JOIN sender_profiles sp ON g.sender_domain = sp.sender_domain"
    conditions = []
    params: list = []

    if gem_type:
        conditions.append("g.gem_type = ?")
        params.append(gem_type)

    if segment:
        query += " JOIN sender_segments ss ON g.sender_domain = ss.sender_domain"
        conditions.append("ss.segment = ?")
        params.append(segment)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY g.score DESC"

    if top:
        query += " LIMIT ?"
        params.append(top)

    rows = conn.execute(query, params).fetchall()

    if not rows:
        typer.echo("No gems found.")
    else:
        typer.echo(f"{'ID':>4}  {'Score':>5}  {'Type':<25}  {'Domain':<30}  {'Company':<20}  Status")
        typer.echo("-" * 120)
        for row in rows:
            typer.echo(
                f"{row['id']:>4}  {row['score']:>5}  {row['gem_type']:<25}  "
                f"{row['sender_domain']:<30}  {(row['company_name'] or ''):<20}  {row['status']}"
            )

    conn.close()


# --- Generate command ---

@app.command()
def generate(
    gem_id: Optional[int] = typer.Option(None, "--gem", help="Generate for specific gem ID."),
    strategy: Optional[str] = typer.Option(None, "--strategy", "-s", help="Filter by strategy."),
    top: Optional[int] = typer.Option(None, "--top", help="Generate for top N gems."),
    all_gems: bool = typer.Option(False, "--all", help="Generate for all matching gems."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model spec. Default: from config/env."),
    crew: bool = typer.Option(False, "--crew", help="Use CrewAI multi-agent mode."),
):
    """Generate engagement drafts (Stage 7)."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.stages.engage import generate_engagement

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    model_spec = _resolve_model(model, config)
    mode = "CrewAI" if crew else "direct"
    typer.echo(f"Generating with model: {model_spec} ({mode} mode)")

    effective_top = top
    if all_gems:
        effective_top = None
    elif gem_id is None and top is None:
        effective_top = 10  # default

    count = generate_engagement(
        conn,
        model_spec=model_spec,
        gem_id=gem_id,
        strategy=strategy,
        top_n=effective_top,
        engagement_config=config.engagement,
        ai_config=config.ai.to_provider_dict(),
        use_crew=crew,
    )
    typer.echo(f"Generated {count} engagement draft(s).")
    conn.close()


# --- Stats command ---

@app.command()
def stats(
    by_esp: bool = typer.Option(False, "--by-esp", help="Breakdown by ESP."),
    by_industry: bool = typer.Option(False, "--by-industry", help="Breakdown by industry."),
    by_segment: bool = typer.Option(False, "--by-segment", help="Breakdown by segment."),
    gem_summary: bool = typer.Option(False, "--gem-summary", help="Gem distribution and scores."),
):
    """Show inbox intelligence statistics."""
    from gemsieve.config import load_config
    from gemsieve.database import db_stats, get_db, init_db

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    if by_esp:
        rows = conn.execute(
            """SELECT esp_identified, COUNT(*) as cnt
               FROM parsed_metadata
               WHERE esp_identified IS NOT NULL
               GROUP BY esp_identified ORDER BY cnt DESC"""
        ).fetchall()
        typer.echo("Messages by ESP:")
        for row in rows:
            typer.echo(f"  {row['esp_identified'] or 'Unknown':<25} {row['cnt']}")

    elif by_industry:
        rows = conn.execute(
            """SELECT industry, COUNT(*) as cnt
               FROM ai_classification
               WHERE industry != ''
               GROUP BY industry ORDER BY cnt DESC"""
        ).fetchall()
        typer.echo("Messages by industry:")
        for row in rows:
            typer.echo(f"  {row['industry']:<30} {row['cnt']}")

    elif by_segment:
        rows = conn.execute(
            """SELECT segment, sub_segment, COUNT(*) as cnt
               FROM sender_segments
               GROUP BY segment, sub_segment ORDER BY segment, cnt DESC"""
        ).fetchall()
        typer.echo("Senders by segment:")
        for row in rows:
            typer.echo(f"  {row['segment']:<20} {row['sub_segment'] or '':<25} {row['cnt']}")

    elif gem_summary:
        rows = conn.execute(
            """SELECT gem_type, COUNT(*) as cnt, AVG(score) as avg_score,
                      MAX(score) as max_score
               FROM gems GROUP BY gem_type ORDER BY cnt DESC"""
        ).fetchall()
        typer.echo(f"{'Gem Type':<25} {'Count':>5} {'Avg Score':>10} {'Max Score':>10}")
        typer.echo("-" * 55)
        for row in rows:
            typer.echo(
                f"{row['gem_type']:<25} {row['cnt']:>5} "
                f"{row['avg_score']:>10.1f} {row['max_score']:>10}"
            )

    else:
        # Overview
        s = db_stats(conn)
        typer.echo("GemSieve Inbox Intelligence Overview")
        typer.echo("=" * 40)
        typer.echo(f"  Messages:       {s.get('messages', 0)}")
        typer.echo(f"  Threads:        {s.get('threads', 0)}")
        typer.echo(f"  Parsed meta:    {s.get('parsed_metadata', 0)}")
        typer.echo(f"  Parsed content: {s.get('parsed_content', 0)}")
        typer.echo(f"  Entities:       {s.get('extracted_entities', 0)}")
        typer.echo(f"  Classified:     {s.get('ai_classification', 0)}")
        typer.echo(f"  Profiles:       {s.get('sender_profiles', 0)}")
        typer.echo(f"  Gems:           {s.get('gems', 0)}")
        typer.echo(f"  Drafts:         {s.get('engagement_drafts', 0)}")
        typer.echo(f"  Overrides:      {s.get('classification_overrides', 0)}")

    conn.close()


# --- Export command ---

@app.command()
def export(
    segment_name: Optional[str] = typer.Option(None, "--segment", help="Export a specific segment."),
    export_gems: bool = typer.Option(False, "--gems", help="Export all gems."),
    export_all: bool = typer.Option(False, "--all", help="Export all profiles."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("csv", "--format", "-f", help="Output format: csv or excel."),
):
    """Export data to CSV or Excel."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db
    from gemsieve.export import export_all_profiles, export_gems as do_export_gems, export_segment

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    if segment_name:
        path = export_segment(conn, segment_name, output_path=output)
        typer.echo(f"Exported segment '{segment_name}' to {path}")

    elif export_gems:
        path = do_export_gems(conn, output_path=output or "gems_export.csv")
        typer.echo(f"Exported gems to {path}")

    elif export_all:
        path = export_all_profiles(conn, output_path=output or "profiles_export.csv", fmt=fmt)
        typer.echo(f"Exported all profiles to {path}")

    else:
        typer.echo("Specify --segment, --gems, or --all", err=True)
        raise typer.Exit(1)

    conn.close()


# --- Full pipeline ---

@app.command()
def run(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Gmail search query."),
    all_stages: bool = typer.Option(False, "--all-stages", help="Run all stages."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model spec. Default: from config/env."),
    crew: bool = typer.Option(False, "--crew", help="Use CrewAI multi-agent mode for AI stages."),
):
    """Run the full pipeline or specific stages."""
    from gemsieve.config import load_config
    from gemsieve.database import get_db, init_db

    config = load_config()
    conn = get_db(config)
    init_db(conn)

    model = _resolve_model(model, config)

    if not all_stages:
        typer.echo("Use --all-stages to run the full pipeline.")
        raise typer.Exit(1)

    # Stage 0: Ingest
    typer.echo("Stage 0: Ingesting from Gmail...")
    from gemsieve.gmail.auth import get_gmail_service, get_user_email
    from gemsieve.gmail.client import GmailClient
    from gemsieve.gmail.sync import SyncEngine

    service = get_gmail_service(config)
    user_email = get_user_email(service)
    client = GmailClient(service, user_email)
    engine = SyncEngine(client, conn)

    search_query = query or config.gmail.default_query
    count = engine.full_sync(search_query)
    typer.echo(f"  Ingested {count} messages.")

    # Stage 1: Metadata
    typer.echo("Stage 1: Extracting metadata...")
    from gemsieve.stages.metadata import extract_metadata
    count = extract_metadata(conn, esp_rules_path=config.esp_fingerprints_file)
    typer.echo(f"  Processed {count} messages.")

    # Stage 2: Content
    typer.echo("Stage 2: Parsing content...")
    from gemsieve.stages.content import parse_content
    count = parse_content(conn)
    typer.echo(f"  Processed {count} messages.")

    # Stage 3: Entities
    typer.echo("Stage 3: Extracting entities...")
    from gemsieve.stages.entities import extract_entities
    count = extract_entities(conn, spacy_model=config.entity_extraction.spacy_model)
    typer.echo(f"  Processed {count} messages.")

    # Stage 4: Classification
    mode_label = " (CrewAI)" if crew else ""
    typer.echo(f"Stage 4: AI classification with {model}{mode_label}...")
    from gemsieve.stages.classify import classify_messages
    count = classify_messages(conn, model_spec=model, batch_size=config.ai.batch_size,
                              max_body_chars=config.ai.max_body_chars,
                              ai_config=config.ai.to_provider_dict(),
                              use_crew=crew)
    typer.echo(f"  Classified {count} messages.")

    # Stage 5: Profiling & Gems
    typer.echo("Stage 5: Building profiles...")
    from gemsieve.stages.profile import build_profiles, detect_gems
    count = build_profiles(conn)
    typer.echo(f"  Built {count} profiles.")
    count = detect_gems(conn)
    typer.echo(f"  Detected {count} gems.")

    # Stage 6: Scoring
    typer.echo("Stage 6: Scoring & segmentation...")
    from gemsieve.stages.segment import assign_segments, evaluate_custom_segments, score_gems
    assign_segments(conn)
    score_gems(conn, config=config.scoring)
    evaluate_custom_segments(conn, segments_file=config.custom_segments_file)
    typer.echo("  Scoring complete.")

    # Stage 7 skipped in batch mode — user should run generate manually
    typer.echo("\nPipeline complete. Run 'gemsieve gems --list' to see results.")
    typer.echo("Run 'gemsieve generate --gem <id>' to create engagement drafts.")

    conn.close()


# --- Web admin command ---

@app.command()
def web(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development."),
):
    """Start the web admin interface."""
    import uvicorn

    typer.echo(f"Starting GemSieve Admin at http://{host}:{port}/admin")
    uvicorn.run(
        "gemsieve.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )
