"""Starlette-Admin setup: ModelViews for all tables + CustomView registration."""

from __future__ import annotations

from starlette_admin.contrib.sqla import Admin, ModelView

from gemsieve.web.models import (
    AiAuditLog,
    AiClassification,
    Attachment,
    ClassificationOverride,
    EngagementDraft,
    ExtractedEntity,
    Gem,
    Message,
    ParsedContent,
    ParsedMetadata,
    PipelineRun,
    SenderProfile,
    SenderSegment,
    SenderTemporal,
    SyncState,
    Thread,
)


# --- ModelView definitions ---

class MessageView(ModelView):
    page_size = 25
    fields = [
        "message_id", "thread_id", "from_name", "from_address",
        "subject", "date", "is_sent", "snippet", "labels",
        "size_estimate", "ingested_at",
    ]
    exclude_fields_from_list = ["snippet", "labels", "size_estimate", "ingested_at"]
    searchable_fields = ["from_address", "subject", "from_name"]
    sortable_fields = ["date", "from_address", "subject"]
    fields_default_sort = [("date", True)]


class ThreadView(ModelView):
    page_size = 25
    fields = [
        "thread_id", "subject", "message_count", "participant_count",
        "last_sender", "days_dormant", "awaiting_response_from",
        "first_message_date", "last_message_date", "user_participated",
    ]
    exclude_fields_from_list = [
        "first_message_date", "user_participated", "participant_count",
    ]
    searchable_fields = ["subject", "last_sender"]
    sortable_fields = ["days_dormant", "message_count", "last_message_date"]
    fields_default_sort = [("last_message_date", True)]


class AttachmentView(ModelView):
    page_size = 25
    fields = ["id", "message_id", "filename", "mime_type", "size_bytes"]
    searchable_fields = ["filename", "mime_type"]


class ParsedMetadataView(ModelView):
    page_size = 25
    fields = [
        "message_id", "sender_domain", "esp_identified", "esp_confidence",
        "spf_result", "dmarc_result", "dkim_domain", "sending_ip",
        "is_bulk", "envelope_sender", "list_unsubscribe_url", "parsed_at",
    ]
    exclude_fields_from_list = [
        "envelope_sender", "list_unsubscribe_url", "parsed_at", "dkim_domain",
    ]
    searchable_fields = ["sender_domain", "esp_identified"]
    sortable_fields = ["sender_domain", "esp_identified", "esp_confidence"]


class SenderTemporalView(ModelView):
    page_size = 25
    fields = [
        "sender_domain", "first_seen", "last_seen", "total_messages",
        "avg_frequency_days", "most_common_send_hour", "most_common_send_day",
    ]
    searchable_fields = ["sender_domain"]
    sortable_fields = ["total_messages", "avg_frequency_days", "last_seen"]


class ParsedContentView(ModelView):
    page_size = 25
    fields = [
        "message_id", "primary_headline", "link_count",
        "tracking_pixel_count", "offer_types", "cta_texts",
        "has_personalization", "template_complexity_score",
        "image_count", "has_physical_address",
    ]
    exclude_fields_from_list = [
        "has_physical_address", "image_count",
    ]
    searchable_fields = ["primary_headline"]
    sortable_fields = ["link_count", "tracking_pixel_count", "template_complexity_score"]


class ExtractedEntityView(ModelView):
    page_size = 50
    fields = [
        "id", "message_id", "entity_type", "entity_value",
        "entity_normalized", "context", "confidence", "source",
    ]
    exclude_fields_from_list = ["entity_normalized", "context"]
    searchable_fields = ["entity_value", "entity_type"]
    sortable_fields = ["entity_type", "confidence"]
    fields_default_sort = [("confidence", True)]


class AiClassificationView(ModelView):
    page_size = 25
    fields = [
        "message_id", "industry", "company_size_estimate",
        "marketing_sophistication", "sender_intent", "product_type",
        "ai_confidence", "model_used", "has_override",
        "partner_program_detected", "renewal_signal_detected",
        "product_description", "target_audience", "classified_at",
    ]
    exclude_fields_from_list = [
        "product_description", "target_audience", "classified_at",
    ]
    searchable_fields = ["industry", "sender_intent", "product_type"]
    sortable_fields = [
        "industry", "marketing_sophistication", "ai_confidence",
        "company_size_estimate",
    ]
    fields_default_sort = [("ai_confidence", True)]


class ClassificationOverrideView(ModelView):
    page_size = 25
    fields = [
        "id", "sender_domain", "message_id", "field_name",
        "original_value", "corrected_value", "override_scope", "created_at",
    ]
    searchable_fields = ["sender_domain", "field_name"]
    sortable_fields = ["created_at", "field_name"]
    fields_default_sort = [("created_at", True)]


class SenderProfileView(ModelView):
    page_size = 25
    fields = [
        "sender_domain", "company_name", "industry", "company_size",
        "marketing_sophistication_avg", "esp_used", "total_messages",
        "has_partner_program", "has_personalization",
        "product_type", "product_description", "primary_email",
        "first_contact", "last_contact", "avg_frequency_days",
        "authentication_quality", "profiled_at",
    ]
    exclude_fields_from_list = [
        "product_description", "primary_email", "first_contact",
        "avg_frequency_days", "authentication_quality", "profiled_at",
    ]
    searchable_fields = ["company_name", "sender_domain", "industry"]
    sortable_fields = [
        "company_name", "industry", "marketing_sophistication_avg",
        "total_messages",
    ]
    fields_default_sort = [("total_messages", True)]


class GemView(ModelView):
    page_size = 25
    fields = [
        "id", "gem_type", "sender_domain", "score", "status",
        "thread_id", "explanation", "recommended_actions",
        "created_at", "acted_at",
    ]
    exclude_fields_from_list = [
        "explanation", "recommended_actions", "thread_id", "acted_at",
    ]
    searchable_fields = ["gem_type", "sender_domain"]
    sortable_fields = ["score", "gem_type", "status", "created_at"]
    fields_default_sort = [("score", True)]


class SenderSegmentView(ModelView):
    page_size = 50
    fields = [
        "sender_domain", "segment", "sub_segment", "confidence", "assigned_at",
    ]
    exclude_fields_from_list = ["assigned_at"]
    searchable_fields = ["sender_domain", "segment", "sub_segment"]
    sortable_fields = ["segment", "confidence"]


class EngagementDraftView(ModelView):
    page_size = 25
    fields = [
        "id", "gem_id", "sender_domain", "strategy", "channel",
        "subject_line", "body_text", "status",
        "generated_at", "sent_at", "response_received",
    ]
    exclude_fields_from_list = ["body_text", "sent_at", "response_received"]
    searchable_fields = ["sender_domain", "strategy", "subject_line"]
    sortable_fields = ["strategy", "status", "generated_at"]
    fields_default_sort = [("generated_at", True)]


class PipelineRunView(ModelView):
    page_size = 25
    fields = [
        "id", "stage", "status", "started_at", "completed_at",
        "items_processed", "error_message", "triggered_by", "created_at",
    ]
    exclude_fields_from_list = ["error_message", "created_at"]
    searchable_fields = ["stage", "status"]
    sortable_fields = ["stage", "status", "started_at", "items_processed"]
    fields_default_sort = [("started_at", True)]

    def can_create(self, request) -> bool:
        return False

    def can_edit(self, request) -> bool:
        return False


class AiAuditLogView(ModelView):
    page_size = 25
    fields = [
        "id", "pipeline_run_id", "stage", "sender_domain",
        "model_used", "duration_ms", "prompt_template",
        "prompt_rendered", "system_prompt",
        "response_raw", "response_parsed", "created_at",
    ]
    exclude_fields_from_list = [
        "prompt_template", "prompt_rendered", "system_prompt",
        "response_raw", "response_parsed",
    ]
    searchable_fields = ["sender_domain", "stage", "model_used"]
    sortable_fields = ["stage", "duration_ms", "created_at"]
    fields_default_sort = [("created_at", True)]

    def can_create(self, request) -> bool:
        return False

    def can_edit(self, request) -> bool:
        return False


def create_admin(engine, templates_dir: str | None = None) -> Admin:
    """Create and configure the Starlette-Admin instance."""
    kwargs = {}
    if templates_dir:
        kwargs["templates_dir"] = templates_dir

    admin = Admin(
        engine,
        title="GemSieve",
        base_url="/admin",
        **kwargs,
    )

    # Data tables
    admin.add_view(MessageView(Message, icon="fa fa-envelope", label="Messages"))
    admin.add_view(ThreadView(Thread, icon="fa fa-comments", label="Threads"))
    admin.add_view(AttachmentView(Attachment, icon="fa fa-paperclip", label="Attachments"))

    # Stage outputs
    admin.add_view(ParsedMetadataView(ParsedMetadata, icon="fa fa-fingerprint", label="Metadata"))
    admin.add_view(SenderTemporalView(SenderTemporal, icon="fa fa-clock", label="Temporal"))
    admin.add_view(ParsedContentView(ParsedContent, icon="fa fa-file-alt", label="Content"))
    admin.add_view(ExtractedEntityView(ExtractedEntity, icon="fa fa-tags", label="Entities"))

    # Classification
    admin.add_view(AiClassificationView(AiClassification, icon="fa fa-brain", label="Classifications"))
    admin.add_view(ClassificationOverrideView(ClassificationOverride, icon="fa fa-edit", label="Overrides"))

    # Profiles & Gems
    admin.add_view(SenderProfileView(SenderProfile, icon="fa fa-building", label="Profiles"))
    admin.add_view(GemView(Gem, icon="fa fa-gem", label="Gems"))
    admin.add_view(SenderSegmentView(SenderSegment, icon="fa fa-layer-group", label="Segments"))

    # Engagement
    admin.add_view(EngagementDraftView(EngagementDraft, icon="fa fa-paper-plane", label="Drafts"))

    # Pipeline & Audit
    admin.add_view(PipelineRunView(PipelineRun, icon="fa fa-play-circle", label="Pipeline Runs"))
    admin.add_view(AiAuditLogView(AiAuditLog, icon="fa fa-search", label="AI Audit Log"))

    return admin
