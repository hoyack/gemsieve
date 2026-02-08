"""CrewAI multi-agent orchestration for classification and engagement stages."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------

class SenderClassification(BaseModel):
    """Structured output for Stage 4: AI Classification."""

    industry: str = Field(
        description=(
            "SaaS, E-commerce, Agency, Financial Services, Healthcare, "
            "Education, Real Estate, Media, Marketing, Developer Tools, "
            "HR, Crypto, Local Business, Nonprofit, Other"
        )
    )
    company_size_estimate: str = Field(description="small | medium | enterprise")
    marketing_sophistication: int = Field(ge=1, le=10)
    sender_intent: str = Field(
        description=(
            "human_1to1 | cold_outreach | nurture_sequence | newsletter | "
            "transactional | promotional | event_invitation | "
            "partnership_pitch | re_engagement | procurement | recruiting | community"
        )
    )
    product_type: str = Field(default="")
    product_description: str = Field(default="")
    pain_points_addressed: list[str] = Field(default_factory=list)
    target_audience: str = Field(default="")
    partner_program_detected: bool = False
    renewal_signal_detected: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EngagementMessage(BaseModel):
    """Structured output for Stage 7: Engagement Draft."""

    subject_line: str = Field(description="Email subject line, under 60 chars")
    body: str = Field(description="Email body text, under 150 words")


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _make_llm(
    model_spec: str,
    ai_config: dict | None = None,
) -> Any:
    """Create a CrewAI LLM instance from gemsieve model_spec format.

    Translates 'ollama:mistral-nemo' → LLM(model='ollama/mistral-nemo', ...).
    """
    from crewai import LLM

    ai_config = ai_config or {}

    if ":" in model_spec:
        provider, model_name = model_spec.split(":", 1)
    else:
        provider = "ollama"
        model_name = model_spec

    if provider == "ollama":
        base_url = ai_config.get("ollama_base_url", "http://localhost:11434")
        api_key = ai_config.get("ollama_api_key", "")
        kwargs: dict[str, Any] = {
            "model": f"ollama/{model_name}",
            "base_url": base_url,
            "temperature": 0.1,
        }
        if api_key:
            kwargs["api_key"] = api_key
        return LLM(**kwargs)
    elif provider == "anthropic":
        return LLM(
            model=f"anthropic/{model_name}",
            temperature=0.2,
            max_tokens=4096,
        )
    else:
        raise ValueError(f"Unknown provider for CrewAI: {provider!r}")


# ---------------------------------------------------------------------------
# Agent builders
# ---------------------------------------------------------------------------

def _build_classifier_agent(llm: Any) -> Any:
    from crewai import Agent

    return Agent(
        role="Email Intelligence Analyst",
        goal=(
            "Classify email senders by industry, company size, marketing "
            "sophistication, intent, and product type with high accuracy "
            "and calibrated confidence scores."
        ),
        backstory=(
            "You are a veteran B2B email analyst who has reviewed over "
            "100,000 marketing emails. You can identify a sender's industry "
            "from their ESP choice, their sophistication from CTA patterns, "
            "and their intent from email structure. You are precise — you "
            "assign low confidence when signals are ambiguous rather than "
            "guessing."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
        max_retry_limit=2,
    )


def _build_engagement_agent(llm: Any) -> Any:
    from crewai import Agent

    return Agent(
        role="B2B Outreach Strategist",
        goal=(
            "Generate personalized engagement messages that reference "
            "specific intelligence about the recipient, demonstrate "
            "genuine expertise, and create clear next-step opportunities."
        ),
        backstory=(
            "You write outreach that gets replies. Your secret: every "
            "sentence proves you did your homework. You never use generic "
            "openers, empty flattery, or vague value props. You match "
            "your tone to the recipient's sophistication level — casual "
            "for startups, polished for enterprise."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
        max_retry_limit=2,
    )


# ---------------------------------------------------------------------------
# Task builders
# ---------------------------------------------------------------------------

def _build_classification_task(agent: Any) -> Any:
    from crewai import Task

    return Task(
        description=(
            "Analyze this email sender and produce a structured classification.\n\n"
            "SENDER: {from_name} <{from_address}>\n"
            "SUBJECT: {subject}\n"
            "ESP IDENTIFIED: {esp_identified}\n"
            "OFFER TYPES: {offer_types}\n"
            "CTA TEXTS: {cta_texts}\n"
            "EXTRACTED ENTITIES: {extracted_entities_summary}\n\n"
            "BODY (first 2000 chars):\n{body_clean}"
        ),
        expected_output=(
            "A JSON classification with industry, company_size_estimate, "
            "marketing_sophistication (1-10), sender_intent, product_type, "
            "product_description, pain_points_addressed, target_audience, "
            "partner_program_detected, renewal_signal_detected, and confidence."
        ),
        agent=agent,
        output_pydantic=SenderClassification,
    )


def _build_engagement_task(agent: Any) -> Any:
    from crewai import Task

    return Task(
        description=(
            "Generate a personalized engagement message.\n\n"
            "STRATEGY: {strategy_name}\n"
            "GEM TYPE: {gem_type}\n"
            "GEM EXPLANATION: {gem_explanation_json}\n\n"
            "RECIPIENT PROFILE:\n"
            "  Company: {company_name}\n"
            "  Contact: {contact_name}, {contact_role}\n"
            "  Industry: {industry}\n"
            "  Size: {company_size}\n"
            "  ESP: {esp_used}\n"
            "  Marketing Score: {sophistication}/10\n"
            "  They sell: {product_description}\n"
            "  Their pain points: {pain_points}\n"
            "  Specific observation: {observation}\n"
            "  Relationship context: {relationship_summary}\n\n"
            "MY SERVICES: {user_service_description}\n"
            "MY TONE: {user_preferred_tone}\n\n"
            "Write a short engagement message (under 150 words) that:\n"
            "1. Opens with a specific, non-generic hook\n"
            "2. Demonstrates valuable insight\n"
            "3. Connects to the opportunity\n"
            "4. Ends with a low-friction CTA\n"
            "5. Addresses the contact by name if available\n\n"
            "Be direct and specific. Sound like a peer, not a vendor."
        ),
        expected_output=(
            "A JSON object with subject_line (under 60 chars) and body "
            "(under 150 words) for the engagement email."
        ),
        agent=agent,
        output_pydantic=EngagementMessage,
    )


# ---------------------------------------------------------------------------
# Public API — crew runners
# ---------------------------------------------------------------------------

def crew_classify(
    sender_data: dict,
    model_spec: str = "ollama:mistral-nemo",
    ai_config: dict | None = None,
) -> dict:
    """Classify a sender using CrewAI agents.

    Args:
        sender_data: dict with keys matching task template variables:
            from_name, from_address, subject, esp_identified,
            offer_types, cta_texts, extracted_entities_summary, body_clean
        model_spec: provider:model format
        ai_config: provider config (base_url, api_key, etc.)

    Returns:
        Classification dict matching SenderClassification schema.
    """
    from crewai import Crew, Process

    llm = _make_llm(model_spec, ai_config)
    agent = _build_classifier_agent(llm)
    task = _build_classification_task(agent)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff(inputs=sender_data)

    # Extract structured result
    if result.pydantic:
        return result.pydantic.model_dump()
    elif result.json_dict:
        return result.json_dict
    else:
        # Fallback: try parsing raw output
        try:
            return json.loads(result.raw)
        except (json.JSONDecodeError, TypeError):
            return {"text": str(result.raw), "confidence": 0.0}


def crew_engage(
    engagement_data: dict,
    model_spec: str = "ollama:mistral-nemo",
    ai_config: dict | None = None,
) -> dict:
    """Generate an engagement draft using CrewAI agents.

    Args:
        engagement_data: dict with keys matching task template variables:
            strategy_name, gem_type, gem_explanation_json, company_name,
            contact_name, contact_role, industry, company_size, esp_used,
            sophistication, product_description, pain_points, observation,
            relationship_summary, user_service_description, user_preferred_tone
        model_spec: provider:model format
        ai_config: provider config (base_url, api_key, etc.)

    Returns:
        Dict with subject_line and body keys.
    """
    from crewai import Crew, Process

    llm = _make_llm(model_spec, ai_config)
    agent = _build_engagement_agent(llm)
    task = _build_engagement_task(agent)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff(inputs=engagement_data)

    if result.pydantic:
        return result.pydantic.model_dump()
    elif result.json_dict:
        return result.json_dict
    else:
        try:
            return json.loads(result.raw)
        except (json.JSONDecodeError, TypeError):
            return {"subject_line": "", "body": str(result.raw)}
