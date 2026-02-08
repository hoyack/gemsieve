"""Dataclasses mirroring DB tables for type safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class GemType(str, Enum):
    WEAK_MARKETING_LEAD = "weak_marketing_lead"
    INDUSTRY_INTEL = "industry_intel"
    DORMANT_WARM_THREAD = "dormant_warm_thread"
    UNANSWERED_ASK = "unanswered_ask"
    PARTNER_PROGRAM = "partner_program"
    RENEWAL_LEVERAGE = "renewal_leverage"
    VENDOR_UPSELL = "vendor_upsell"
    DISTRIBUTION_CHANNEL = "distribution_channel"
    CO_MARKETING = "co_marketing"
    PROCUREMENT_SIGNAL = "procurement_signal"


@dataclass
class Thread:
    thread_id: str
    subject: str | None = None
    participant_count: int = 0
    message_count: int = 0
    first_message_date: str | None = None
    last_message_date: str | None = None
    last_sender: str | None = None
    user_participated: bool = False
    user_last_replied: str | None = None
    awaiting_response_from: str | None = None  # 'user' | 'other' | 'none'
    days_dormant: int = 0


@dataclass
class Message:
    message_id: str
    thread_id: str
    date: str | None = None
    from_address: str = ""
    from_name: str = ""
    reply_to: str | None = None
    to_addresses: str | None = None  # JSON
    cc_addresses: str | None = None  # JSON
    subject: str = ""
    headers_raw: str | None = None  # JSON
    body_html: str | None = None
    body_text: str | None = None
    labels: str | None = None  # JSON
    snippet: str = ""
    size_estimate: int = 0
    is_sent: bool = False


@dataclass
class ParsedMetadata:
    message_id: str
    sender_domain: str = ""
    envelope_sender: str | None = None
    esp_identified: str | None = None
    esp_confidence: str | None = None
    dkim_domain: str | None = None
    spf_result: str | None = None
    dmarc_result: str | None = None
    sending_ip: str | None = None
    list_unsubscribe_url: str | None = None
    list_unsubscribe_email: str | None = None
    is_bulk: bool = False
    x_mailer: str | None = None
    mail_server: str | None = None
    precedence: str | None = None
    feedback_id: str | None = None


@dataclass
class ParsedContent:
    message_id: str
    body_clean: str = ""
    signature_block: str | None = None
    primary_headline: str | None = None
    cta_texts: list[str] = field(default_factory=list)
    offer_types: list[str] = field(default_factory=list)
    has_personalization: bool = False
    personalization_tokens: list[str] = field(default_factory=list)
    link_count: int = 0
    tracking_pixel_count: int = 0
    unique_link_domains: list[str] = field(default_factory=list)
    link_intents: dict[str, list[str]] = field(default_factory=dict)
    utm_campaigns: list[dict] = field(default_factory=list)
    has_physical_address: bool = False
    physical_address_text: str | None = None
    social_links: dict[str, str] = field(default_factory=dict)
    image_count: int = 0
    template_complexity_score: int = 0


@dataclass
class ExtractedEntity:
    message_id: str
    entity_type: str  # person | organization | money | date | procurement_signal
    entity_value: str
    entity_normalized: str | None = None
    context: str | None = None
    confidence: float = 0.0
    source: str = "body"  # body | signature | header | subject


@dataclass
class Classification:
    message_id: str
    industry: str = ""
    company_size_estimate: str = ""
    marketing_sophistication: int = 0
    sender_intent: str = ""
    product_type: str = ""
    product_description: str = ""
    pain_points: list[str] = field(default_factory=list)
    target_audience: str = ""
    partner_program_detected: bool = False
    renewal_signal_detected: bool = False
    ai_confidence: float = 0.0
    model_used: str = ""
    has_override: bool = False


@dataclass
class SenderProfile:
    sender_domain: str
    company_name: str | None = None
    primary_email: str | None = None
    reply_to_email: str | None = None
    industry: str | None = None
    company_size: str | None = None
    marketing_sophistication_avg: float = 0.0
    marketing_sophistication_trend: str | None = None
    esp_used: str | None = None
    product_type: str | None = None
    product_description: str | None = None
    pain_points: list[str] = field(default_factory=list)
    target_audience: str | None = None
    known_contacts: list[dict] = field(default_factory=list)
    total_messages: int = 0
    first_contact: str | None = None
    last_contact: str | None = None
    avg_frequency_days: float = 0.0
    offer_type_distribution: dict[str, int] = field(default_factory=dict)
    cta_texts_all: list[str] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)
    physical_address: str | None = None
    utm_campaign_names: list[str] = field(default_factory=list)
    has_personalization: bool = False
    has_partner_program: bool = False
    partner_program_urls: list[str] = field(default_factory=list)
    renewal_dates: list[str] = field(default_factory=list)
    monetary_signals: list[dict] = field(default_factory=list)
    authentication_quality: str | None = None
    unsubscribe_url: str | None = None
    economic_segments: list[str] = field(default_factory=list)


@dataclass
class Gem:
    gem_type: str
    sender_domain: str
    thread_id: str | None = None
    score: int = 0
    explanation: dict = field(default_factory=dict)
    recommended_actions: list[str] = field(default_factory=list)
    source_message_ids: list[str] = field(default_factory=list)
    status: str = "new"
    id: int | None = None


@dataclass
class EngagementDraft:
    gem_id: int
    sender_domain: str
    strategy: str
    channel: str = ""
    subject_line: str = ""
    body_text: str = ""
    body_html: str = ""
    status: str = "draft"
    id: int | None = None
