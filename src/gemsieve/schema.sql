-- GemSieve database schema

-- Sync state (singleton row)
CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_history_id TEXT,
    last_full_sync TIMESTAMP,
    last_incremental_sync TIMESTAMP,
    total_messages_synced INTEGER DEFAULT 0
);

-- Threads
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    subject TEXT,
    participant_count INTEGER,
    message_count INTEGER,
    first_message_date TIMESTAMP,
    last_message_date TIMESTAMP,
    last_sender TEXT,
    user_participated BOOLEAN,
    user_last_replied TIMESTAMP,
    awaiting_response_from TEXT,
    days_dormant INTEGER,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT REFERENCES threads(thread_id),
    date TIMESTAMP,
    from_address TEXT,
    from_name TEXT,
    reply_to TEXT,
    to_addresses JSON,
    cc_addresses JSON,
    subject TEXT,
    headers_raw JSON,
    body_html TEXT,
    body_text TEXT,
    labels JSON,
    snippet TEXT,
    size_estimate INTEGER,
    is_sent BOOLEAN DEFAULT FALSE,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_from ON messages(from_address);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

-- Attachments
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT REFERENCES messages(message_id),
    filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    attachment_id TEXT
);

-- Stage 1: Parsed metadata
CREATE TABLE IF NOT EXISTS parsed_metadata (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
    sender_domain TEXT,
    envelope_sender TEXT,
    esp_identified TEXT,
    esp_confidence TEXT,
    dkim_domain TEXT,
    spf_result TEXT,
    dmarc_result TEXT,
    sending_ip TEXT,
    list_unsubscribe_url TEXT,
    list_unsubscribe_email TEXT,
    is_bulk BOOLEAN,
    x_mailer TEXT,
    mail_server TEXT,
    precedence TEXT,
    feedback_id TEXT,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parsed_metadata_domain ON parsed_metadata(sender_domain);

-- Stage 1: Sender temporal patterns
CREATE TABLE IF NOT EXISTS sender_temporal (
    sender_domain TEXT PRIMARY KEY,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    total_messages INTEGER,
    avg_frequency_days REAL,
    most_common_send_hour INTEGER,
    most_common_send_day INTEGER
);

-- Stage 2: Parsed content
CREATE TABLE IF NOT EXISTS parsed_content (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
    body_clean TEXT,
    signature_block TEXT,
    primary_headline TEXT,
    cta_texts JSON,
    offer_types JSON,
    has_personalization BOOLEAN,
    personalization_tokens JSON,
    link_count INTEGER,
    tracking_pixel_count INTEGER,
    unique_link_domains JSON,
    link_intents JSON,
    utm_campaigns JSON,
    has_physical_address BOOLEAN,
    physical_address_text TEXT,
    social_links JSON,
    image_count INTEGER,
    template_complexity_score INTEGER,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stage 3: Extracted entities
CREATE TABLE IF NOT EXISTS extracted_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT REFERENCES messages(message_id),
    entity_type TEXT,
    entity_value TEXT,
    entity_normalized TEXT,
    context TEXT,
    confidence REAL,
    source TEXT,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON extracted_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_message ON extracted_entities(message_id);

-- Stage 4: AI classification
CREATE TABLE IF NOT EXISTS ai_classification (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
    industry TEXT,
    company_size_estimate TEXT,
    marketing_sophistication INTEGER,
    sender_intent TEXT,
    product_type TEXT,
    product_description TEXT,
    pain_points JSON,
    target_audience TEXT,
    partner_program_detected BOOLEAN,
    renewal_signal_detected BOOLEAN,
    ai_confidence REAL,
    model_used TEXT,
    has_override BOOLEAN DEFAULT FALSE,
    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stage 4: Classification overrides
CREATE TABLE IF NOT EXISTS classification_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT REFERENCES messages(message_id),
    sender_domain TEXT,
    field_name TEXT,
    original_value TEXT,
    corrected_value TEXT,
    override_scope TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_overrides_domain ON classification_overrides(sender_domain);

-- Stage 5: Sender profiles
CREATE TABLE IF NOT EXISTS sender_profiles (
    sender_domain TEXT PRIMARY KEY,
    company_name TEXT,
    primary_email TEXT,
    reply_to_email TEXT,
    industry TEXT,
    company_size TEXT,
    marketing_sophistication_avg REAL,
    marketing_sophistication_trend TEXT,
    esp_used TEXT,
    product_type TEXT,
    product_description TEXT,
    pain_points JSON,
    target_audience TEXT,
    known_contacts JSON,
    total_messages INTEGER,
    first_contact TIMESTAMP,
    last_contact TIMESTAMP,
    avg_frequency_days REAL,
    offer_type_distribution JSON,
    cta_texts_all JSON,
    social_links JSON,
    physical_address TEXT,
    utm_campaign_names JSON,
    has_personalization BOOLEAN,
    has_partner_program BOOLEAN,
    partner_program_urls JSON,
    renewal_dates JSON,
    monetary_signals JSON,
    authentication_quality TEXT,
    unsubscribe_url TEXT,
    economic_segments JSON,
    profiled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stage 5: Gems
CREATE TABLE IF NOT EXISTS gems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gem_type TEXT,
    sender_domain TEXT REFERENCES sender_profiles(sender_domain),
    thread_id TEXT,
    score INTEGER,
    explanation JSON,
    recommended_actions JSON,
    source_message_ids JSON,
    status TEXT DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gems_type ON gems(gem_type);
CREATE INDEX IF NOT EXISTS idx_gems_score ON gems(score DESC);
CREATE INDEX IF NOT EXISTS idx_gems_status ON gems(status);

-- Stage 6: Sender segments (junction table)
CREATE TABLE IF NOT EXISTS sender_segments (
    sender_domain TEXT REFERENCES sender_profiles(sender_domain),
    segment TEXT,
    sub_segment TEXT,
    confidence REAL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sender_domain, segment, sub_segment)
);

-- Stage 7: Engagement drafts
CREATE TABLE IF NOT EXISTS engagement_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gem_id INTEGER REFERENCES gems(id),
    sender_domain TEXT REFERENCES sender_profiles(sender_domain),
    strategy TEXT,
    channel TEXT,
    subject_line TEXT,
    body_text TEXT,
    body_html TEXT,
    status TEXT DEFAULT 'draft',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    response_received BOOLEAN DEFAULT FALSE,
    response_sentiment TEXT
);

-- Pipeline run tracking
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    items_processed INTEGER DEFAULT 0,
    error_message TEXT,
    config_snapshot TEXT,
    triggered_by TEXT DEFAULT 'web',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI audit log
CREATE TABLE IF NOT EXISTS ai_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id),
    stage TEXT NOT NULL,
    sender_domain TEXT,
    prompt_template TEXT,
    prompt_rendered TEXT,
    system_prompt TEXT,
    model_used TEXT,
    response_raw TEXT,
    response_parsed TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
