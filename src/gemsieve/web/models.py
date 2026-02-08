"""SQLAlchemy ORM models mirroring schema.sql (all 16 tables)."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_history_id: Mapped[str | None] = mapped_column(String)
    last_full_sync: Mapped[str | None] = mapped_column(String)
    last_incremental_sync: Mapped[str | None] = mapped_column(String)
    total_messages_synced: Mapped[int] = mapped_column(Integer, default=0)


class Thread(Base):
    __tablename__ = "threads"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str | None] = mapped_column(String)
    participant_count: Mapped[int | None] = mapped_column(Integer)
    message_count: Mapped[int | None] = mapped_column(Integer)
    first_message_date: Mapped[str | None] = mapped_column(String)
    last_message_date: Mapped[str | None] = mapped_column(String)
    last_sender: Mapped[str | None] = mapped_column(String)
    user_participated: Mapped[bool | None] = mapped_column(Boolean)
    user_last_replied: Mapped[str | None] = mapped_column(String)
    awaiting_response_from: Mapped[str | None] = mapped_column(String)
    days_dormant: Mapped[int | None] = mapped_column(Integer)
    ingested_at: Mapped[str | None] = mapped_column(String)


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(String)
    date: Mapped[str | None] = mapped_column(String)
    from_address: Mapped[str | None] = mapped_column(String)
    from_name: Mapped[str | None] = mapped_column(String)
    reply_to: Mapped[str | None] = mapped_column(String)
    to_addresses: Mapped[str | None] = mapped_column(Text)
    cc_addresses: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String)
    headers_raw: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(String)
    size_estimate: Mapped[int | None] = mapped_column(Integer)
    is_sent: Mapped[bool | None] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[str | None] = mapped_column(String)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str | None] = mapped_column(String)
    filename: Mapped[str | None] = mapped_column(String)
    mime_type: Mapped[str | None] = mapped_column(String)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    attachment_id: Mapped[str | None] = mapped_column(String)


class ParsedMetadata(Base):
    __tablename__ = "parsed_metadata"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    sender_domain: Mapped[str | None] = mapped_column(String)
    envelope_sender: Mapped[str | None] = mapped_column(String)
    esp_identified: Mapped[str | None] = mapped_column(String)
    esp_confidence: Mapped[str | None] = mapped_column(String)
    dkim_domain: Mapped[str | None] = mapped_column(String)
    spf_result: Mapped[str | None] = mapped_column(String)
    dmarc_result: Mapped[str | None] = mapped_column(String)
    sending_ip: Mapped[str | None] = mapped_column(String)
    list_unsubscribe_url: Mapped[str | None] = mapped_column(String)
    list_unsubscribe_email: Mapped[str | None] = mapped_column(String)
    is_bulk: Mapped[bool | None] = mapped_column(Boolean)
    parsed_at: Mapped[str | None] = mapped_column(String)


class SenderTemporal(Base):
    __tablename__ = "sender_temporal"

    sender_domain: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen: Mapped[str | None] = mapped_column(String)
    last_seen: Mapped[str | None] = mapped_column(String)
    total_messages: Mapped[int | None] = mapped_column(Integer)
    avg_frequency_days: Mapped[float | None] = mapped_column(Float)
    most_common_send_hour: Mapped[int | None] = mapped_column(Integer)
    most_common_send_day: Mapped[int | None] = mapped_column(Integer)


class ParsedContent(Base):
    __tablename__ = "parsed_content"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    body_clean: Mapped[str | None] = mapped_column(Text)
    signature_block: Mapped[str | None] = mapped_column(Text)
    primary_headline: Mapped[str | None] = mapped_column(String)
    cta_texts: Mapped[str | None] = mapped_column(Text)
    offer_types: Mapped[str | None] = mapped_column(Text)
    has_personalization: Mapped[bool | None] = mapped_column(Boolean)
    personalization_tokens: Mapped[str | None] = mapped_column(Text)
    link_count: Mapped[int | None] = mapped_column(Integer)
    tracking_pixel_count: Mapped[int | None] = mapped_column(Integer)
    unique_link_domains: Mapped[str | None] = mapped_column(Text)
    link_intents: Mapped[str | None] = mapped_column(Text)
    utm_campaigns: Mapped[str | None] = mapped_column(Text)
    has_physical_address: Mapped[bool | None] = mapped_column(Boolean)
    physical_address_text: Mapped[str | None] = mapped_column(Text)
    social_links: Mapped[str | None] = mapped_column(Text)
    image_count: Mapped[int | None] = mapped_column(Integer)
    template_complexity_score: Mapped[int | None] = mapped_column(Integer)
    parsed_at: Mapped[str | None] = mapped_column(String)


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str | None] = mapped_column(String)
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_value: Mapped[str | None] = mapped_column(String)
    entity_normalized: Mapped[str | None] = mapped_column(String)
    context: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String)
    extracted_at: Mapped[str | None] = mapped_column(String)


class AiClassification(Base):
    __tablename__ = "ai_classification"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    industry: Mapped[str | None] = mapped_column(String)
    company_size_estimate: Mapped[str | None] = mapped_column(String)
    marketing_sophistication: Mapped[int | None] = mapped_column(Integer)
    sender_intent: Mapped[str | None] = mapped_column(String)
    product_type: Mapped[str | None] = mapped_column(String)
    product_description: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(String)
    partner_program_detected: Mapped[bool | None] = mapped_column(Boolean)
    renewal_signal_detected: Mapped[bool | None] = mapped_column(Boolean)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    model_used: Mapped[str | None] = mapped_column(String)
    has_override: Mapped[bool | None] = mapped_column(Boolean, default=False)
    classified_at: Mapped[str | None] = mapped_column(String)


class ClassificationOverride(Base):
    __tablename__ = "classification_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str | None] = mapped_column(String)
    sender_domain: Mapped[str | None] = mapped_column(String)
    field_name: Mapped[str | None] = mapped_column(String)
    original_value: Mapped[str | None] = mapped_column(String)
    corrected_value: Mapped[str | None] = mapped_column(String)
    override_scope: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str | None] = mapped_column(String)


class SenderProfile(Base):
    __tablename__ = "sender_profiles"

    sender_domain: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String)
    primary_email: Mapped[str | None] = mapped_column(String)
    reply_to_email: Mapped[str | None] = mapped_column(String)
    industry: Mapped[str | None] = mapped_column(String)
    company_size: Mapped[str | None] = mapped_column(String)
    marketing_sophistication_avg: Mapped[float | None] = mapped_column(Float)
    marketing_sophistication_trend: Mapped[str | None] = mapped_column(String)
    esp_used: Mapped[str | None] = mapped_column(String)
    product_type: Mapped[str | None] = mapped_column(String)
    product_description: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(String)
    known_contacts: Mapped[str | None] = mapped_column(Text)
    total_messages: Mapped[int | None] = mapped_column(Integer)
    first_contact: Mapped[str | None] = mapped_column(String)
    last_contact: Mapped[str | None] = mapped_column(String)
    avg_frequency_days: Mapped[float | None] = mapped_column(Float)
    offer_type_distribution: Mapped[str | None] = mapped_column(Text)
    cta_texts_all: Mapped[str | None] = mapped_column(Text)
    social_links: Mapped[str | None] = mapped_column(Text)
    physical_address: Mapped[str | None] = mapped_column(Text)
    utm_campaign_names: Mapped[str | None] = mapped_column(Text)
    has_personalization: Mapped[bool | None] = mapped_column(Boolean)
    has_partner_program: Mapped[bool | None] = mapped_column(Boolean)
    partner_program_urls: Mapped[str | None] = mapped_column(Text)
    renewal_dates: Mapped[str | None] = mapped_column(Text)
    monetary_signals: Mapped[str | None] = mapped_column(Text)
    authentication_quality: Mapped[str | None] = mapped_column(String)
    unsubscribe_url: Mapped[str | None] = mapped_column(String)
    economic_segments: Mapped[str | None] = mapped_column(Text)
    profiled_at: Mapped[str | None] = mapped_column(String)


class Gem(Base):
    __tablename__ = "gems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gem_type: Mapped[str | None] = mapped_column(String)
    sender_domain: Mapped[str | None] = mapped_column(String)
    thread_id: Mapped[str | None] = mapped_column(String)
    score: Mapped[int | None] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text)
    recommended_actions: Mapped[str | None] = mapped_column(Text)
    source_message_ids: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String, default="new")
    created_at: Mapped[str | None] = mapped_column(String)
    acted_at: Mapped[str | None] = mapped_column(String)


class SenderSegment(Base):
    __tablename__ = "sender_segments"

    sender_domain: Mapped[str] = mapped_column(String, primary_key=True)
    segment: Mapped[str] = mapped_column(String, primary_key=True)
    sub_segment: Mapped[str] = mapped_column(String, primary_key=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    assigned_at: Mapped[str | None] = mapped_column(String)


class EngagementDraft(Base):
    __tablename__ = "engagement_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gem_id: Mapped[int | None] = mapped_column(Integer)
    sender_domain: Mapped[str | None] = mapped_column(String)
    strategy: Mapped[str | None] = mapped_column(String)
    channel: Mapped[str | None] = mapped_column(String)
    subject_line: Mapped[str | None] = mapped_column(String)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String, default="draft")
    generated_at: Mapped[str | None] = mapped_column(String)
    sent_at: Mapped[str | None] = mapped_column(String)
    response_received: Mapped[bool | None] = mapped_column(Boolean, default=False)
    response_sentiment: Mapped[str | None] = mapped_column(String)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str | None] = mapped_column(String, default="pending")
    started_at: Mapped[str | None] = mapped_column(String)
    completed_at: Mapped[str | None] = mapped_column(String)
    items_processed: Mapped[int | None] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String, default="web")
    created_at: Mapped[str | None] = mapped_column(String)


class AiAuditLog(Base):
    __tablename__ = "ai_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    sender_domain: Mapped[str | None] = mapped_column(String)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    prompt_rendered: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String)
    response_raw: Mapped[str | None] = mapped_column(Text)
    response_parsed: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(String)
