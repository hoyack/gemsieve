"""Stage 7: Engagement draft generation."""

from __future__ import annotations

import json
import sqlite3

from gemsieve.ai.prompts import DEFAULT_ENGAGEMENT_PROMPT, STRATEGY_PROMPTS
from gemsieve.config import EngagementConfig
from gemsieve.models import GemType

# Maps gem types to engagement strategy names
GEM_STRATEGY_MAP = {
    GemType.WEAK_MARKETING_LEAD.value: "audit",
    GemType.INDUSTRY_INTEL.value: "industry_report",
    GemType.DORMANT_WARM_THREAD.value: "revival",
    GemType.UNANSWERED_ASK.value: "revival",
    GemType.PARTNER_PROGRAM.value: "partner",
    GemType.RENEWAL_LEVERAGE.value: "renewal_negotiation",
    GemType.VENDOR_UPSELL.value: "mirror",
    GemType.DISTRIBUTION_CHANNEL.value: "distribution_pitch",
    GemType.CO_MARKETING.value: "mirror",
    GemType.PROCUREMENT_SIGNAL.value: "audit",
}

STRATEGY_CHANNELS = {
    "audit": "email reply or cold email",
    "industry_report": "content publication + tag",
    "revival": "reply to original thread",
    "partner": "partner program URL or vendor contact",
    "renewal_negotiation": "email to account manager",
    "mirror": "email reply with value exchange",
    "distribution_pitch": "pitch email to editor/host",
}


def _build_strategy_context(
    strategy: str,
    gem: dict,
    profile: dict,
    engagement_config: EngagementConfig,
) -> dict:
    """Assemble strategy-specific context variables for prompt formatting.

    Returns a dict ready to be passed to prompt.format(**context).
    """
    explanation = {}
    try:
        explanation = json.loads(gem["explanation"]) if gem["explanation"] else {}
    except (json.JSONDecodeError, TypeError):
        pass

    # Parse contacts for the most relevant one
    contacts = []
    try:
        contacts = json.loads(profile["known_contacts"]) if profile["known_contacts"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    contact_name = contacts[0]["name"] if contacts else ""
    contact_role = contacts[0].get("role", "") if contacts else ""

    # Base context shared by all strategies
    context = {
        "strategy_name": strategy,
        "gem_type": gem["gem_type"],
        "gem_explanation_json": json.dumps(explanation, indent=2),
        "company_name": profile["company_name"] or profile["sender_domain"],
        "contact_name": contact_name,
        "contact_role": contact_role,
        "industry": profile["industry"] or "Unknown",
        "company_size": profile["company_size"] or "Unknown",
        "esp_used": profile["esp_used"] or "Unknown",
        "sophistication": profile["marketing_sophistication_avg"] or 0,
        "product_description": profile["product_description"] or "Unknown",
        "pain_points": json.dumps(
            json.loads(profile["pain_points"]) if profile["pain_points"] else []
        ),
        "observation": explanation.get("summary", ""),
        "relationship_summary": f"{profile['total_messages']} messages over time",
        "user_service_description": engagement_config.your_service or "consulting services",
        "user_preferred_tone": engagement_config.your_tone or "professional",
        "user_audience": getattr(engagement_config, "your_audience", "") or "",
    }

    # Strategy-specific context additions
    if strategy == "revival":
        # Thread context for revival
        thread_subject = ""
        dormancy_days = 0
        if gem.get("thread_id"):
            # Will be filled from explanation signals
            signals = explanation.get("signals", [])
            for sig in signals:
                if sig.get("signal") == "dormancy":
                    try:
                        dormancy_days = int(sig.get("evidence", "0").split()[0])
                    except (ValueError, IndexError):
                        pass
        context["thread_subject"] = explanation.get("summary", "").split("'")[1] if "'" in explanation.get("summary", "") else ""
        context["dormancy_days"] = dormancy_days or explanation.get("summary", "").split("dormant for ")[-1].split(" days")[0] if "dormant for" in explanation.get("summary", "") else "unknown"

    elif strategy == "renewal_negotiation":
        # Renewal dates and monetary signals
        renewal_dates = []
        monetary_signals = []
        try:
            renewal_dates = json.loads(profile["renewal_dates"]) if profile["renewal_dates"] else []
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            monetary_signals = json.loads(profile["monetary_signals"]) if profile["monetary_signals"] else []
        except (json.JSONDecodeError, TypeError):
            pass
        context["renewal_dates"] = json.dumps(renewal_dates)
        context["monetary_signals"] = json.dumps(monetary_signals)

    elif strategy == "partner":
        # Partner URLs
        partner_urls = []
        try:
            partner_urls = json.loads(profile["partner_program_urls"]) if profile["partner_program_urls"] else []
        except (json.JSONDecodeError, TypeError):
            pass
        context["partner_urls"] = json.dumps(partner_urls)

    elif strategy == "distribution_pitch":
        context["target_audience"] = profile["target_audience"] or ""

    return context


def generate_engagement(
    db: sqlite3.Connection,
    model_spec: str = "ollama:mistral-nemo",
    gem_id: int | None = None,
    strategy: str | None = None,
    top_n: int | None = None,
    engagement_config: EngagementConfig | None = None,
    ai_config: dict | None = None,
    use_crew: bool = False,
) -> int:
    """Generate engagement drafts for gems.

    Args:
        db: database connection
        model_spec: AI model to use
        gem_id: specific gem to generate for
        strategy: filter by strategy type
        top_n: limit to top N gems by score
        engagement_config: user engagement preferences
        ai_config: AI provider config dict (base_url, api_key, etc.)
        use_crew: If True, use CrewAI multi-agent mode instead of direct calls.

    Returns count of drafts generated.
    """
    if engagement_config is None:
        engagement_config = EngagementConfig()

    # Build query for gems to process
    query = "SELECT * FROM gems WHERE status = 'new'"
    params: list = []

    if gem_id is not None:
        query = "SELECT * FROM gems WHERE id = ?"
        params = [gem_id]
    elif strategy:
        # Filter by gem types that map to this strategy
        matching_types = [k for k, v in GEM_STRATEGY_MAP.items() if v == strategy]
        if matching_types:
            placeholders = ",".join("?" for _ in matching_types)
            query += f" AND gem_type IN ({placeholders})"
            params.extend(matching_types)

    query += " ORDER BY score DESC"

    if top_n:
        query += " LIMIT ?"
        params.append(top_n)

    gems = db.execute(query, params).fetchall()

    # Filter by preferred_strategies (Spec §15)
    preferred = getattr(engagement_config, "preferred_strategies", None)
    if preferred and gem_id is None:
        gems = [
            g for g in gems
            if GEM_STRATEGY_MAP.get(g["gem_type"], "audit") in preferred
        ]

    generated = 0

    for gem in gems:
        # Daily limit enforcement (Spec §15)
        max_per_day = getattr(engagement_config, "max_outreach_per_day", 20)
        today_count = db.execute(
            "SELECT COUNT(*) as cnt FROM engagement_drafts WHERE date(generated_at) = date('now')"
        ).fetchone()
        if today_count and today_count["cnt"] >= max_per_day:
            break

        # Get sender profile
        profile = db.execute(
            "SELECT * FROM sender_profiles WHERE sender_domain = ?",
            (gem["sender_domain"],),
        ).fetchone()

        if not profile:
            continue

        gem_type = gem["gem_type"]
        strat = GEM_STRATEGY_MAP.get(gem_type, "audit")
        channel = STRATEGY_CHANNELS.get(strat, "email")

        # Build strategy context
        context = _build_strategy_context(strat, dict(gem), dict(profile), engagement_config)

        # Select strategy prompt or fallback to default
        prompt_template = STRATEGY_PROMPTS.get(strat, DEFAULT_ENGAGEMENT_PROMPT)

        try:
            if use_crew:
                from gemsieve.ai.crews import crew_engage
                result = crew_engage(context, model_spec=model_spec, ai_config=ai_config)
                subject_line = result.get("subject_line", "")
                body_text = result.get("body", result.get("body_text", ""))
            else:
                from gemsieve.ai import get_provider

                provider, model_name = get_provider(model_spec, config=ai_config)
                prompt = prompt_template.format(**context)
                result = provider.complete(
                    prompt=prompt,
                    model=model_name,
                    system="You are generating personalized engagement messages. Write naturally, not like a template.",
                )

                # Parse result — could be a dict with subject/body or raw text
                if isinstance(result, dict):
                    subject_line = result.get("subject_line", result.get("subject", ""))
                    body_text = result.get("body_text", result.get("body", result.get("message", "")))
                else:
                    subject_line = ""
                    body_text = str(result)

            db.execute(
                """INSERT INTO engagement_drafts
                   (gem_id, sender_domain, strategy, channel,
                    subject_line, body_text, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'draft')""",
                (
                    gem["id"], gem["sender_domain"], strat, channel,
                    subject_line, body_text,
                ),
            )
            generated += 1

        except Exception as e:
            print(f"  Engagement generation failed for gem {gem['id']}: {e}")

    db.commit()
    return generated
