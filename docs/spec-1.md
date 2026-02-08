# Inbox Intelligence & Reverse-Engagement Engine

## Specification Document v0.2

### Changelog from v0.1

- **Added:** Thread-aware ingestion and dormant thread recovery as a first-class gem type
- **Added:** Entity extraction (NER) stage between content parsing and AI classification
- **Added:** Vendor-as-Partner segment and partner ecosystem detection
- **Added:** Spend Map with SaaS renewal window tracking from transactional emails
- **Added:** Distribution Map segment (newsletters, podcasts, events as amplification channels)
- **Added:** Incremental sync via Gmail `historyId` for continuous operation
- **Added:** User override/correction system with feedback loop into classification
- **Added:** Multi-segment membership (messages can belong to multiple economic segments)
- **Added:** Signature/footer/quoted-reply stripping in content parser
- **Added:** Gem abstraction layer with typed opportunities and structured explainability
- **Expanded:** Ingestion scope to include all inbox categories (not just promotions/spam)
- **Expanded:** Opportunity scoring to account for new segment types and gem diversity

---

## 1. Vision

Every email in your inbox is a compressed economic record. Promotional emails reveal sender tech stacks, budgets, and marketing gaps. Transactional emails encode procurement cycles and renewal windows. Dormant threads contain stalled deals and forgotten asks. Newsletters and event invitations are distribution channels waiting to be activated.

This system transforms a Gmail inbox into a **living revenue graph** — extracting structured intelligence from every category of email, scoring it for economic leverage, and generating hyper-targeted engagement that is built from the sender's own data.

The thesis: your inbox already contains the leads, the partners, the leverage, and the distribution. You just can't see it because email clients are designed for reading, not for mining.

---

## 2. System Overview

```
┌──────────┐    ┌───────────┐    ┌──────────┐    ┌─────────┐    ┌───────────┐    ┌──────────┐    ┌───────────┐    ┌────────────┐
│  Gmail   │───▶│ Ingestion │───▶│ Metadata │───▶│ Content │───▶│  Entity  │───▶│    AI    │───▶│ Profiler │───▶│ Engagement │
│  Inbox   │    │ & Sync    │    │ Extract  │    │ Parser  │    │ Extract  │    │ Classify │    │ & Scorer │    │ Generator  │
└──────────┘    └───────────┘    └──────────┘    └─────────┘    └───────────┘    └──────────┘    └───────────┘    └────────────┘
                      │                │               │              │               │               │                │
                      ▼                ▼               ▼              ▼               ▼               ▼                ▼
                 Raw messages     ESP/infra        Clean text     People, orgs   Industry,       Sender          Outreach
                 + threads       fingerprints     CTAs, offers   money, dates   intent, size    profiles +       drafts +
                 + historyId                      links, structure               product type   gems scored      action plans
```

### Pipeline Stages

| Stage | Name | Input | Output | AI Required |
|-------|------|-------|--------|-------------|
| 0 | Ingestion & Sync | Gmail API | Raw messages + threads in local DB | No |
| 1 | Metadata Extraction | Raw headers + envelope | Structured sender/ESP/infra records | No |
| 2 | Content Parsing | Email body (HTML + text) | Clean text, offers, CTAs, structure signals | No |
| 3 | Entity Extraction | Clean text | People, orgs, money, dates, procurement keywords | Light NLP |
| 4 | AI Classification | All parsed data | Industry, intent, sophistication, product type | Yes |
| 5 | Sender Profiling & Gem Detection | Per-domain aggregation | Unified profiles + typed opportunity gems | Yes |
| 6 | Segmentation & Scoring | Profiles + gems | Ranked opportunities across all economic segments | Configurable |
| 7 | Engagement Generation | Top-scored gems | Tailored outreach drafts per gem type | Yes |

Each stage is independently runnable via CLI. Outputs are stored in the database so any stage can be re-run without re-processing upstream.

---

## 3. Stage 0 — Gmail Ingestion & Sync

### 3.1 Scope

Pull messages from Gmail across **all categories** — not just promotions and spam. Dormant thread recovery, procurement signal detection, and vendor-as-partner identification all require access to primary inbox, sent mail, and transactional messages.

Default ingestion query: `newer_than:1y` (all messages from the last year). User can override with any Gmail search query, or specify category-specific queries for targeted runs.

### 3.2 Data Captured Per Message

```
message_id          — Gmail message ID (unique key)
thread_id           — Gmail thread ID
date                — Sent datetime (from Date header, normalized to UTC)
from_address        — Sender email address
from_name           — Sender display name
reply_to            — Reply-To address (often differs from From)
to_address          — Recipient address(es)
cc_addresses        — CC recipients
subject             — Subject line
headers_raw         — Full raw headers as JSON
body_html           — HTML body (largest text/html part)
body_text           — Plain text body (text/plain part or stripped HTML)
attachments         — List of {filename, mime_type, size_bytes, attachment_id}
labels              — Gmail label IDs
snippet             — Gmail's auto-generated snippet
size_estimate       — Message size in bytes
internal_date       — Gmail's internal timestamp
is_sent             — Whether this message was sent BY the user
ingested_at         — When we pulled this message
```

### 3.3 Thread-Aware Ingestion

Threads are first-class objects, not just message groupings:

```sql
CREATE TABLE threads (
    thread_id TEXT PRIMARY KEY,
    subject TEXT,                    -- normalized subject (stripped Re:/Fwd:)
    participant_count INTEGER,       -- unique email addresses in thread
    message_count INTEGER,
    first_message_date TIMESTAMP,
    last_message_date TIMESTAMP,
    last_sender TEXT,                -- who sent the most recent message
    user_participated BOOLEAN,       -- did the inbox owner send any messages in this thread
    user_last_replied TIMESTAMP,     -- when the inbox owner last replied
    awaiting_response_from TEXT,     -- 'user' | 'other' | 'none'
    days_dormant INTEGER,            -- days since last activity
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`awaiting_response_from` is derived by examining the last message in the thread:
- If the last message is FROM someone else and contains a question, ask, or CTA → `'user'` (you owe a reply)
- If the last message is FROM the user → `'other'` (they owe you a reply)
- If the thread is clearly concluded → `'none'`

This single field powers the entire dormant thread recovery system.

### 3.4 Incremental Sync

After the initial full ingestion, subsequent runs use Gmail's `historyId` mechanism for efficient delta sync:

```python
# On first run:
#   1. Full scan with search query
#   2. Store latest historyId from the API response

# On subsequent runs:
#   1. Call users.history.list(startHistoryId=stored_id)
#   2. Process only new/modified messages
#   3. Update stored historyId

# Fallback: if historyId is expired (>7 days stale), do full re-scan with dedup
```

```sql
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    last_history_id TEXT,
    last_full_sync TIMESTAMP,
    last_incremental_sync TIMESTAMP,
    total_messages_synced INTEGER
);
```

### 3.5 Message Storage

```sql
CREATE TABLE messages (
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

CREATE TABLE attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT REFERENCES messages(message_id),
    filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    attachment_id TEXT
);

CREATE INDEX idx_messages_from ON messages(from_address);
CREATE INDEX idx_messages_date ON messages(date);
CREATE INDEX idx_messages_thread ON messages(thread_id);
```

---

## 4. Stage 1 — Metadata Extraction (Header Forensics)

### 4.1 Purpose

Extract structured intelligence from email headers and envelope data without touching body content. This is the highest-signal, lowest-cost extraction layer.

### 4.2 Fields Extracted

#### Sender Infrastructure

| Field | Source | Example |
|-------|--------|---------|
| `sender_domain` | From address | `acme.com` |
| `envelope_sender` | Return-Path header | `bounce-123@em.acme.com` |
| `esp_identified` | Return-Path, X-Mailer, DKIM domain, tracking domains | `SendGrid` |
| `dkim_domain` | DKIM-Signature d= field | `sendgrid.net` |
| `spf_result` | Received-SPF or Authentication-Results | `pass` |
| `dmarc_result` | Authentication-Results | `pass` |
| `sending_ip` | Received headers (outermost) | `167.89.115.0` |
| `mail_server` | Received headers | `o1.em.acme.com` |
| `x_mailer` | X-Mailer header | `Mailchimp Mailer` |
| `list_unsubscribe` | List-Unsubscribe header | URL or mailto |
| `precedence` | Precedence header | `bulk` |
| `feedback_id` | X-Feedback-ID (Google) | campaign identifiers |

#### ESP Fingerprinting Rules

Map known patterns to ESP identity:

```yaml
sendgrid:
  signals:
    - return_path_contains: "sendgrid.net"
    - dkim_domain: "sendgrid.net"
    - header_present: "X-SG-EID"
  confidence: high

mailchimp:
  signals:
    - return_path_contains: "mcsv.net"
    - dkim_domain: "mcsv.net"
    - x_mailer_contains: "Mailchimp"
    - tracking_domain: "list-manage.com"
  confidence: high

hubspot:
  signals:
    - return_path_contains: "hubspot.com"
    - tracking_domain: "track.hubspot.com"
    - header_present: "X-HS-CampaignId"
  confidence: high

klaviyo:
  signals:
    - return_path_contains: "klaviyo.com"
    - dkim_domain: "klaviyo.com"
    - tracking_domain: "trk.klaviyo.com"
  confidence: high

constant_contact:
  signals:
    - return_path_contains: "constantcontact.com"
    - x_mailer_contains: "Roving Constant Contact"
  confidence: high

amazon_ses:
  signals:
    - return_path_contains: "amazonses.com"
    - dkim_domain: "amazonses.com"
  confidence: medium  # many companies use SES as infra

custom_smtp:
  signals:
    - no_known_esp_match: true
    - dkim_domain_matches_sender: true
  confidence: low  # could be sophisticated or primitive
```

#### Temporal Patterns

| Field | Derivation |
|-------|-----------|
| `send_hour_utc` | From Date header |
| `send_day_of_week` | From Date header |
| `frequency_days` | Average gap between messages from same sender |
| `first_seen` | Earliest message date from this sender |
| `last_seen` | Most recent message date from this sender |
| `total_messages` | Count of messages from this sender |

### 4.3 Output Schema

```sql
CREATE TABLE parsed_metadata (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
    sender_domain TEXT,
    envelope_sender TEXT,
    esp_identified TEXT,
    esp_confidence TEXT,  -- high / medium / low
    dkim_domain TEXT,
    spf_result TEXT,
    dmarc_result TEXT,
    sending_ip TEXT,
    list_unsubscribe_url TEXT,
    list_unsubscribe_email TEXT,
    is_bulk BOOLEAN,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sender_temporal (
    sender_domain TEXT PRIMARY KEY,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    total_messages INTEGER,
    avg_frequency_days REAL,
    most_common_send_hour INTEGER,
    most_common_send_day INTEGER
);
```

---

## 5. Stage 2 — Content Parsing

### 5.1 Purpose

Extract structured intelligence from email body content: what the sender is selling, how they're selling it, and what patterns reveal about their marketing operation.

### 5.2 Pre-Processing: Signature & Boilerplate Stripping

Before any content extraction, strip noise that would poison downstream analysis:

```
1. Quoted reply removal
   - Detect "On <date>, <name> wrote:" patterns and strip everything below
   - Detect ">" prefix quoting and strip
   - Detect Gmail's <div class="gmail_quote"> blocks

2. Signature removal
   - Detect common delimiters: "-- ", "—", "Best regards,", "Sent from my iPhone"
   - Use heuristic: if the last N lines are short, contain a name + title + phone/URL, strip them
   - Preserve the signature content separately (it contains role/title intel for entity extraction)

3. Footer/legal stripping
   - Detect unsubscribe blocks, physical address blocks, "You're receiving this because..." text
   - Strip but preserve the physical address and unsubscribe URL as structured fields

4. HTML boilerplate
   - Strip tracking pixels, spacer GIFs, ESP wrapper HTML
   - Extract meaningful content from the deepest content-bearing table cells
```

Output: `body_clean` (stripped text ready for analysis) and `signature_block` (preserved separately for entity extraction).

### 5.3 HTML Parsing Targets

#### Links & Tracking

- Extract all `<a href>` URLs from HTML body
- Classify links as: CTA (buttons/prominent links), tracking pixel (1x1 images), unsubscribe, social media, website/landing page, UTM-tagged (extract utm_source, utm_medium, utm_campaign, utm_content)
- Count total links, unique domains linked, tracking pixels present
- Extract UTM parameters — these reveal campaign naming conventions, which signal marketing sophistication

#### Link Intent Classification

Beyond basic type, classify each link's *destination intent* — what happens when someone clicks:

```yaml
link_intents:
  pricing_page:
    signals: ["pricing", "plans", "packages", "/pricing", "cost"]
  demo_booking:
    signals: ["demo", "book-a-call", "calendly", "schedule"]
  partner_program:
    signals: ["partner", "affiliate", "referral", "reseller", "/partners"]
  marketplace_listing:
    signals: ["marketplace", "app-store", "integrations", "/apps"]
  job_posting:
    signals: ["careers", "jobs", "hiring", "we-re-hiring", "/jobs"]
  case_study:
    signals: ["case-study", "customer-story", "success-story"]
  free_tool:
    signals: ["free-tool", "calculator", "generator", "template"]
```

This is critical for the Vendor-as-Partner segment — a link to `/partners` or `/affiliate` in a vendor email is a direct signal that partnership is available.

#### Visual & Structural Signals

- Template complexity score: count of HTML tables, inline styles, media queries, images
- Image count and hosting domain (self-hosted vs. CDN vs. ESP-hosted)
- Presence of dynamic/personalization tokens (e.g., `%%FIRST_NAME%%`, `{{name}}`, `*|FNAME|*`)
- Footer analysis: physical address present (CAN-SPAM compliance), social links, unsubscribe prominence

#### Content Extraction

- Primary headline / H1 text
- CTA button text(s) — e.g., "Shop Now", "Start Free Trial", "Book a Demo"
- Offer detection via regex + keyword matching:

```yaml
offer_patterns:
  discount:
    patterns: ['\d+%\s*off', '\$\d+\s*off', 'save\s+\$?\d+', 'coupon', 'promo code']
  free_trial:
    patterns: ['free trial', 'try free', 'start free', '\d+[- ]day trial']
  webinar:
    patterns: ['webinar', 'live demo', 'register now', 'join us live']
  product_launch:
    patterns: ['just launched', 'introducing', 'now available', 'new release', 'announcing']
  urgency:
    patterns: ['limited time', 'expires', 'last chance', 'ends tonight', 'only \d+ left']
  social_proof:
    patterns: ['trusted by', 'join \d+', '\d+ customers', 'as seen in', 'rated \d']
  event:
    patterns: ['conference', 'summit', 'meetup', 'workshop']
  newsletter:
    patterns: ['this week in', 'weekly digest', 'roundup', 'top stories']
  renewal:
    patterns: ['renewal', 'subscription renew', 'upcoming charge', 'plan expires',
               'auto-renew', 'billing cycle', 'annual renewal']
  partnership:
    patterns: ['partner program', 'affiliate', 'referral program', 'reseller',
               'become a partner', 'earn commission', 'revenue share']
  procurement:
    patterns: ['security review', 'vendor assessment', 'SOC 2', 'compliance',
               'data processing agreement', 'DPA', 'MSA', 'terms of service update']
```

### 5.4 Output Schema

```sql
CREATE TABLE parsed_content (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
    body_clean TEXT,              -- stripped of signatures, quotes, boilerplate
    signature_block TEXT,         -- preserved separately for entity extraction
    primary_headline TEXT,
    cta_texts JSON,              -- ["Shop Now", "Learn More"]
    offer_types JSON,            -- ["discount", "urgency"]
    has_personalization BOOLEAN,
    personalization_tokens JSON,
    link_count INTEGER,
    tracking_pixel_count INTEGER,
    unique_link_domains JSON,
    link_intents JSON,           -- {"pricing_page": [...urls], "partner_program": [...urls]}
    utm_campaigns JSON,          -- extracted UTM params
    has_physical_address BOOLEAN,
    physical_address_text TEXT,
    social_links JSON,           -- {"twitter": "...", "linkedin": "..."}
    image_count INTEGER,
    template_complexity_score INTEGER,  -- 0-100
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Stage 3 — Entity Extraction

### 6.1 Purpose

Extract structured entities from email content that signal commercial relationships, buying intent, and human connections. This is what turns "a marketing email" into "an email from Sarah Chen, VP Marketing at Acme Corp, mentioning a $50K annual contract renewal."

### 6.2 Entity Types

#### People

```
name                — Full name
email               — Email address (from headers or body)
role/title          — Job title (from signature block, body, or "sent on behalf of")
organization        — Company they belong to
relationship_type   — vendor_contact | peer | decision_maker | automated
```

Extraction sources, in priority order:
1. Signature blocks (most reliable for role/title)
2. "From" display name + body references
3. CC/BCC addresses (signals organizational structure)
4. Body text mentions ("Please contact Sarah at...")

#### Organizations

```
name                — Company/org name
domain              — Associated domain
relationship        — vendor | customer | partner | prospect | unknown
confidence          — extraction confidence score
```

#### Monetary Values

```
amount              — Numeric value
currency            — USD, EUR, etc.
context             — "pricing", "invoice", "discount", "budget", "contract"
```

Pattern matching:
```regex
\$[\d,]+(?:\.\d{2})?          — USD amounts
\d+[kK]\s*(?:ARR|MRR|/mo|/yr) — SaaS metric shorthand
\d+%\s*(?:off|discount|commission|revenue share)  — percentage-based offers
```

#### Dates & Timelines

```
date                — Parsed datetime
context             — "renewal", "expiration", "event", "deadline", "follow_up"
is_future           — Whether the date is in the future (actionable)
```

Pattern matching:
```regex
renew(?:s|al)?\s+(?:on|by|before)\s+(.+)   — renewal dates
expires?\s+(?:on)?\s+(.+)                    — expiration dates
(?:by|before|due)\s+(.+)                     — deadlines
```

#### Procurement Keywords

Detect language that signals active buying, vendor evaluation, or contractual activity:

```yaml
procurement_signals:
  active_buying:
    - "evaluating solutions"
    - "looking for a vendor"
    - "RFP"
    - "request for proposal"
    - "shortlist"
    - "proof of concept"
    - "POC"
  contract_activity:
    - "terms of service"
    - "SLA"
    - "service level agreement"
    - "data processing agreement"
    - "master service agreement"
    - "SOW"
    - "statement of work"
  security_review:
    - "SOC 2"
    - "ISO 27001"
    - "security questionnaire"
    - "vendor risk assessment"
    - "penetration test"
    - "GDPR compliance"
```

### 6.3 Implementation

**Primary approach:** spaCy NER pipeline with a custom-trained model for email-specific entities. Falls back to regex + heuristic extraction for monetary values and dates.

**Fallback for higher accuracy:** Route ambiguous extractions through the AI classification stage (Stage 4) for resolution.

### 6.4 Output Schema

```sql
CREATE TABLE extracted_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT REFERENCES messages(message_id),
    entity_type TEXT,          -- person | organization | money | date | procurement_signal
    entity_value TEXT,         -- the extracted text
    entity_normalized TEXT,    -- normalized form (e.g., parsed date, cleaned name)
    context TEXT,              -- surrounding text or semantic context
    confidence REAL,
    source TEXT,               -- body | signature | header | subject
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_entities_type ON extracted_entities(entity_type);
CREATE INDEX idx_entities_message ON extracted_entities(message_id);
```

---

## 7. Stage 4 — AI Classification

### 7.1 Purpose

Use an LLM (local via Ollama or API-based) to classify each sender/message into categories that support outreach targeting. This is where raw parsed data becomes actionable intelligence.

### 7.2 Classification Dimensions

#### 7.2.1 Industry / Vertical

Classify sender into one of:

```
SaaS / Software          E-commerce / Retail       Agency / Consulting
Financial Services       Healthcare / Wellness     Education / EdTech
Real Estate              Media / Publishing        Food & Beverage
Travel / Hospitality     Nonprofit                 Developer Tools
Marketing / AdTech       HR / Recruiting           Crypto / Web3
Local Business           Other
```

#### 7.2.2 Company Size Estimate

Inferred from signals:

| Signal | Small (1-50) | Mid (50-500) | Enterprise (500+) |
|--------|-------------|-------------|-------------------|
| ESP used | Mailchimp, ConvertKit | HubSpot, Klaviyo | Salesforce, custom |
| Template quality | Basic / broken | Clean, branded | Pixel-perfect, accessible |
| Sending domain | Gmail/shared domain | Branded subdomain | Dedicated IP/domain |
| Personalization | None or basic | Moderate | Dynamic content blocks |
| Physical address | Sometimes missing | Present | Always present + legal |
| Social proof claims | "100+ users" | "10,000+ users" | "Fortune 500 clients" |

#### 7.2.3 Marketing Sophistication Score (1-10)

Composite score based on:

- ESP tier (1-3 points)
- Personalization depth (0-2 points)
- UTM parameter usage and naming consistency (0-1 point)
- Template quality and responsiveness (0-1 point)
- Segmentation signals (do they send different content over time?) (0-1 point)
- Authentication (SPF + DKIM + DMARC all passing) (0-1 point)
- Unsubscribe implementation quality (0-1 point)

#### 7.2.4 Sender Intent Classification

```
human_1to1          — a real person writing directly to you
cold_outreach       — they're trying to sell TO you directly
nurture_sequence    — you're in an automated drip campaign
newsletter          — regular content / thought leadership
transactional       — receipts, shipping, account alerts
promotional         — sales, discounts, product pushes
event_invitation    — webinars, conferences, meetups
partnership_pitch   — collaboration / affiliate offers
re_engagement       — "we miss you" / win-back campaigns
procurement         — security reviews, vendor assessments, compliance
recruiting          — job opportunities, talent outreach
community           — Slack/Discord/forum notifications, community updates
```

#### 7.2.5 Product/Service Category

What they're actually selling, extracted from body content:

```
Physical product       Digital product        SaaS subscription
Professional service   Course / training      Event tickets
Membership             Free tool / freemium   Marketplace listing
```

### 7.3 AI Prompt Strategy

Each message gets a single structured prompt that returns all classifications. The prompt now includes extracted entities for richer context:

```
You are analyzing an email to build an intelligence profile on the sender.

SENDER: {from_name} <{from_address}>
SUBJECT: {subject}
ESP: {esp_identified}
INTENT SIGNALS: {offer_types}, CTAs: {cta_texts}
ENTITIES FOUND: {extracted_entities_summary}
BODY (first 2000 chars):
{body_clean}

Classify this sender. Respond in JSON only:
{
  "industry": "one of: [list]",
  "company_size_estimate": "small | medium | enterprise",
  "marketing_sophistication": 1-10,
  "sender_intent": "one of: [list]",
  "product_type": "one of: [list]",
  "product_description": "one sentence",
  "pain_points_addressed": ["list of problems their product solves"],
  "target_audience": "who they're selling to",
  "partner_program_detected": true/false,
  "renewal_signal_detected": true/false,
  "confidence": 0.0-1.0
}
```

For cost efficiency, batch multiple messages from the same sender and classify the sender once using the most representative messages.

### 7.4 User Override & Feedback Loop

Users can correct any AI classification. Corrections are stored and used to improve future runs:

```sql
CREATE TABLE classification_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT REFERENCES messages(message_id),
    sender_domain TEXT,
    field_name TEXT,            -- which field was corrected (e.g., "industry", "sender_intent")
    original_value TEXT,
    corrected_value TEXT,
    override_scope TEXT,        -- 'message' | 'sender' (apply to all messages from this sender)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Override application logic:
1. Before classifying a message, check if there's a sender-scoped override for that domain
2. If so, pre-fill the overridden fields and skip AI classification for those dimensions
3. On `classify --retrain`, use accumulated overrides to generate few-shot examples for the AI prompt
4. Track override frequency per field — if >20% of a field's classifications get overridden, flag the prompt for tuning

CLI:
```bash
inbox-intel override --sender acme.com --field industry --value "Developer Tools"
inbox-intel override --message abc123 --field sender_intent --value "partnership_pitch"
inbox-intel overrides --list                    # show all active overrides
inbox-intel overrides --stats                   # override rate per field
```

### 7.5 Output Schema

```sql
CREATE TABLE ai_classification (
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
```

---

## 8. Stage 5 — Sender Profiling & Gem Detection

### 8.1 Purpose

Aggregate all message-level data into unified intelligence profiles per sender domain, then detect typed "gems" — specific, actionable revenue opportunities with structured explainability.

### 8.2 Aggregation Logic

For each unique `sender_domain`:

1. Pull all messages, parsed metadata, parsed content, entities, and AI classifications
2. Resolve conflicts via majority vote (industry, size) or most recent (product description)
3. Apply any user overrides
4. Compute aggregate metrics:
   - Total messages received
   - Date range of contact (first seen → last seen)
   - Average send frequency
   - Offer type distribution (e.g., 60% promotional, 30% newsletter, 10% event)
   - CTA diversity (how many unique CTAs across all messages)
   - Marketing sophistication trend (improving over time? degrading?)
   - People extracted (all named contacts at this company, with roles)
   - Monetary values mentioned (contract sizes, pricing signals)
5. Enrich with domain lookup: WHOIS age, company LinkedIn URL (optional, via web scrape or API)

### 8.3 Profile Schema

```sql
CREATE TABLE sender_profiles (
    sender_domain TEXT PRIMARY KEY,
    company_name TEXT,
    primary_email TEXT,
    reply_to_email TEXT,
    industry TEXT,
    company_size TEXT,
    marketing_sophistication_avg REAL,
    marketing_sophistication_trend TEXT,  -- improving / stable / declining
    esp_used TEXT,
    product_type TEXT,
    product_description TEXT,
    pain_points JSON,
    target_audience TEXT,
    known_contacts JSON,          -- [{"name": "...", "role": "...", "email": "..."}]
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
    partner_program_urls JSON,    -- direct links to their partner/affiliate pages
    renewal_dates JSON,           -- detected renewal/expiration dates
    monetary_signals JSON,        -- [{"amount": "$500/mo", "context": "subscription"}]
    authentication_quality TEXT,
    unsubscribe_url TEXT,
    economic_segments JSON,       -- ["spend_map", "partner_map"] — multi-segment membership
    profiled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 8.4 Gem Detection

A "gem" is a typed, scored, explainable revenue opportunity. Every gem has a type, a score, an explanation of *why* it's a gem, and recommended next actions.

#### Gem Types

```python
class GemType(Enum):
    # From promotional/marketing emails (original v0.1 focus)
    WEAK_MARKETING_LEAD    = "weak_marketing_lead"     # sender has marketing gaps you can fill
    INDUSTRY_INTEL         = "industry_intel"           # useful for market intelligence reports

    # From thread analysis (new in v0.2)
    DORMANT_WARM_THREAD    = "dormant_warm_thread"      # stalled conversation with revenue potential
    UNANSWERED_ASK         = "unanswered_ask"           # someone asked you something and you never replied

    # From vendor/transactional emails (new in v0.2)
    PARTNER_PROGRAM        = "partner_program"          # vendor has affiliate/reseller program you can join
    RENEWAL_LEVERAGE       = "renewal_leverage"         # upcoming renewal = negotiation window
    VENDOR_UPSELL          = "vendor_upsell"            # vendor is pitching upgrades = they value you

    # From newsletters/events (new in v0.2)
    DISTRIBUTION_CHANNEL   = "distribution_channel"     # newsletter/podcast/event that could amplify you
    CO_MARKETING           = "co_marketing"             # sender's audience overlaps yours

    # From procurement signals (new in v0.2)
    PROCUREMENT_SIGNAL     = "procurement_signal"       # signals active buying or vendor evaluation
```

#### Gem Schema

```sql
CREATE TABLE gems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gem_type TEXT,
    sender_domain TEXT REFERENCES sender_profiles(sender_domain),
    thread_id TEXT,                  -- nullable, for thread-based gems
    score INTEGER,                   -- 0-100
    explanation JSON,                -- structured "why this is a gem"
    recommended_actions JSON,        -- ["reply to thread", "apply to partner program", ...]
    source_message_ids JSON,         -- messages that contributed to this gem
    status TEXT DEFAULT 'new',       -- new / reviewed / acted / dismissed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acted_at TIMESTAMP
);

CREATE INDEX idx_gems_type ON gems(gem_type);
CREATE INDEX idx_gems_score ON gems(score DESC);
CREATE INDEX idx_gems_status ON gems(status);
```

#### Gem Explanation Structure

Every gem must explain itself. No black boxes:

```json
{
  "gem_type": "dormant_warm_thread",
  "summary": "Sarah Chen at Acme Corp asked about your API pricing 47 days ago. You never replied.",
  "signals": [
    {"signal": "explicit_ask", "evidence": "Subject: 'Quick question about your API pricing'"},
    {"signal": "decision_maker", "evidence": "Sarah Chen, VP Engineering (from signature)"},
    {"signal": "budget_indicator", "evidence": "Mentioned 'evaluating for our team of 30'"},
    {"signal": "dormant_duration", "value": "47 days", "threshold": "30 days"}
  ],
  "confidence": 0.92,
  "estimated_value": "medium-high",
  "urgency": "high — long dormancy reduces reply viability"
}
```

#### Gem Detection Rules

Each gem type has specific detection logic:

**DORMANT_WARM_THREAD:**
```python
# Thread where:
#   1. awaiting_response_from == 'user' (you owe a reply)
#   2. days_dormant > 14
#   3. Thread contains: pricing language, meeting requests, questions,
#      "circle back", "follow up", "thoughts?", "interested?"
#   4. Sender is a real human (not automated)
# Score boosted by: entity extraction finding money/dates, decision-maker title
```

**PARTNER_PROGRAM:**
```python
# Sender where:
#   1. You already receive their emails (they're a vendor you use or know)
#   2. Link intent classification found "partner_program" URLs
#      OR offer_types includes "partnership"
#      OR AI classification flagged partner_program_detected
#   3. Their target audience overlaps with yours
# Score boosted by: commission/revenue-share percentages extracted, program maturity signals
```

**RENEWAL_LEVERAGE:**
```python
# Message where:
#   1. sender_intent == 'transactional'
#   2. offer_types includes 'renewal'
#   3. Entity extraction found a future date in renewal context
#   4. Sender is a SaaS vendor you pay
# Score boosted by: renewal date proximity (30 days out = highest), monetary value extracted
```

**DISTRIBUTION_CHANNEL:**
```python
# Sender where:
#   1. sender_intent == 'newsletter' OR 'event_invitation'
#   2. Content references: guest posts, speaker applications, "submit your story",
#      podcast interviews, contributed content
#   3. Their audience is relevant to your industry/services
# Score boosted by: audience size signals, frequency of sends (active publication),
#   presence of "contribute" or "pitch" CTAs
```

---

## 9. Stage 6 — Segmentation & Opportunity Scoring

### 9.1 Purpose

Assign every sender profile to one or more **economic segments**, then rank all gems by overall opportunity score.

### 9.2 Economic Segments

Each sender can belong to **multiple segments simultaneously**. A SaaS vendor might be in your Spend Map (you pay them), Partner Map (they have an affiliate program), AND be a Weak Marketing Lead (their emails are unsophisticated).

#### Segment Definitions

**Spend Map** — Companies you pay or have paid:
- Detected via: transactional emails (receipts, invoices, renewal notices), procurement signals
- Sub-segments: active subscriptions, upcoming renewals, dormant/churned vendors
- Value: negotiation leverage, consolidation opportunities, cost intelligence

**Partner Map** — Companies with partnership/affiliate programs accessible to you:
- Detected via: partner program link intents, partnership offer_types, affiliate CTAs
- Sub-segments: referral programs, reseller programs, marketplace integrations, co-marketing
- Value: passive revenue, ecosystem leverage, warm introductions

**Prospect Map** — Companies you could sell to (the original v0.1 focus):
- Detected via: marketing sophistication gaps, small/medium size, relevant industry
- Sub-segments: hot leads, warm prospects, intelligence value
- Value: direct revenue from service sales

**Dormant Threads** — Conversations with stalled commercial potential:
- Detected via: thread analysis, awaiting_response_from, dormancy duration
- Sub-segments: unanswered asks (you owe), unreplied pitches (they owe), mutual ghosting
- Value: revived deals, relationship recovery

**Distribution Map** — Channels that could amplify your reach:
- Detected via: newsletter sender_intent, event_invitation, community content
- Sub-segments: newsletters (guest post opportunities), podcasts, events, communities
- Value: audience reach, authority building, inbound lead generation

**Procurement Map** — Active buying signals from any direction:
- Detected via: procurement keywords, security review language, RFP/SOW mentions
- Sub-segments: you're being evaluated, you're evaluating, third-party procurement signals
- Value: deal acceleration, competitive intelligence

### 9.3 Opportunity Score Formula

The scoring formula now accounts for gem diversity — a sender that shows up across multiple segments is inherently more valuable:

```python
def opportunity_score(profile: SenderProfile, gems: list[Gem]) -> float:
    score = 0.0

    # --- Base profile score (max 60) ---

    # Reachability — can we actually get to a decision-maker?
    if profile.company_size == "small":
        score += 15
    elif profile.company_size == "medium":
        score += 10
    else:
        score += 3

    # Budget signal — are they spending on marketing/tools?
    if profile.esp_used in ["HubSpot", "Klaviyo", "ActiveCampaign"]:
        score += 10
    elif profile.esp_used in ["SendGrid", "Amazon SES"]:
        score += 7
    else:
        score += 3

    # Relevance — do they match our target industries?
    if profile.industry in TARGET_INDUSTRIES:
        score += 10
    else:
        score += 3

    # Recency — are they still active?
    days_since_last = (now() - profile.last_contact).days
    if days_since_last <= 30:
        score += 10
    elif days_since_last <= 90:
        score += 5

    # Known contacts — do we have named people with roles?
    if profile.known_contacts and any(c.get("role") for c in profile.known_contacts):
        score += 10  # we know WHO to reach out to
    else:
        score += 2

    # Monetary signals — have we seen budget/pricing data?
    if profile.monetary_signals:
        score += 5

    # --- Gem diversity bonus (max 40) ---

    gem_types_present = set(g.gem_type for g in gems)

    # Each unique gem type adds value
    score += min(len(gem_types_present) * 8, 24)

    # Specific high-value gem bonuses
    if "dormant_warm_thread" in gem_types_present:
        score += 8   # hottest — someone already wants to talk to you
    if "partner_program" in gem_types_present:
        score += 5   # passive revenue potential
    if "renewal_leverage" in gem_types_present:
        score += 3   # time-sensitive negotiation window

    return min(score, 100)
```

### 9.4 Segment Assignment

```sql
-- Multi-segment membership stored as a junction table
CREATE TABLE sender_segments (
    sender_domain TEXT REFERENCES sender_profiles(sender_domain),
    segment TEXT,              -- spend_map | partner_map | prospect_map | etc.
    sub_segment TEXT,          -- e.g., "active_subscription", "referral_program"
    confidence REAL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sender_domain, segment, sub_segment)
);
```

### 9.5 Custom Segment Tags

User-configurable tags based on any combination of profile fields:

```yaml
custom_segments:
  - name: "AI-ready small businesses"
    rules:
      company_size: "small"
      industry: ["SaaS", "Agency", "Marketing"]
      marketing_sophistication_avg: {"lt": 5}
    priority: "hot"

  - name: "E-commerce with weak email game"
    rules:
      industry: "E-commerce"
      has_personalization: false
      esp_used: ["Mailchimp", "constant_contact"]
    priority: "warm"

  - name: "Partner revenue targets"
    rules:
      has_partner_program: true
      industry: ["SaaS", "Developer Tools", "Marketing"]
    priority: "hot"

  - name: "Renewal negotiation windows"
    rules:
      segment_includes: "spend_map"
      renewal_date_within_days: 60
    priority: "hot"
```

---

## 10. Stage 7 — Engagement Generation

### 10.1 Purpose

Auto-generate personalized engagement drafts for top-scored gems, using the intelligence gathered. Each gem type maps to specific engagement strategies.

### 10.2 Engagement Strategies by Gem Type

#### Strategy A — "I Audited Your Funnel" (for WEAK_MARKETING_LEAD gems)

Direct, consultative outreach highlighting specific observations from their emails.

```
Trigger: marketing_sophistication <= 5 AND company_size IN (small, medium)
Channel: Reply to their email, or cold email to reply-to address
Tone: Peer-to-peer, specific, non-salesy

Template context variables:
  - {company_name}
  - {contact_name} and {contact_role}  — from entity extraction
  - {specific_observation}  — e.g., "your last 5 emails had identical CTAs"
  - {esp_name} — what tool they use
  - {suggested_improvement}
  - {your_service_hook}
```

#### Strategy B — "Industry Intelligence Report" (for INDUSTRY_INTEL gems)

Content-led engagement: publish a report analyzing email marketing patterns in their industry, tag/mention them.

```
Trigger: 10+ senders in same industry segment
Channel: LinkedIn post, blog, or direct email with PDF
Tone: Authority, data-driven

Generation approach:
  - Aggregate stats across all senders in segment
  - Identify outliers (best and worst performers)
  - Generate narrative with specific (anonymized or named) examples
  - Include benchmarks: avg sophistication score, common ESPs, personalization rates
```

#### Strategy C — "Mirror Match" (for any PROSPECT gem)

Match the sender's own style and channel preferences when reaching out.

```
Trigger: any prospect-type gem
Channel: matches their outreach style

Rules:
  - If they send HTML templates → send a polished HTML email
  - If they send plain-text founder-style → send plain-text
  - If they include social proof → include your own social proof
  - If they use urgency → create urgency in your pitch
  - Mirror their approximate email length
  - Reference the same pain points they address, reframed for YOUR service
```

#### Strategy D — "Unsubscribe Judo" (for small company PROSPECT gems)

Use the unsubscribe interaction as a touchpoint.

```
Trigger: company_size == small AND reply_to is personal address
Channel: reply to unsubscribe confirmation or directly after unsubscribing

Approach:
  - Unsubscribe from their list (generates a touchpoint/notification on their end)
  - Within 24 hours, send a separate outreach referencing the context
  - "Just cleaned up my inbox and unsubscribed from your list — but before I go,
     I noticed [specific observation]. I help companies like yours [value prop].
     Worth a 10-minute call?"
```

#### Strategy E — "Thread Revival" (for DORMANT_WARM_THREAD gems)

Re-engage stalled conversations with context-aware follow-ups.

```
Trigger: dormant_warm_thread gem with score > 50
Channel: reply to the original thread
Tone: casual, acknowledges the gap, adds new value

Template context variables:
  - {contact_name}
  - {original_topic}  — from thread subject + body
  - {time_since_last}  — "a few weeks ago" / "back in October"
  - {new_hook}  — something relevant that's changed since the thread died
  - {original_ask}  — what they asked or what you discussed

Rules:
  - Never open with "sorry for the delay" — it's weak
  - Acknowledge the gap briefly, then add value
  - Reference the specific thing discussed, proving you remember
  - Provide something new (insight, update, offer) that justifies re-engagement
  - If THEY owe you a reply: lighter touch, just a bump with added context
  - If YOU owe them: more substantive, bring something to the table
```

#### Strategy F — "Partner Application" (for PARTNER_PROGRAM gems)

Generate application or outreach to join a vendor's partner/affiliate program.

```
Trigger: partner_program gem
Channel: partner program URL (direct application) or email to vendor contact
Tone: professional, emphasizes mutual value

Template context variables:
  - {vendor_name}
  - {partner_program_url}
  - {your_audience_description}  — who you can refer to them
  - {existing_relationship}  — "I've been using [product] for X months"
  - {referral_potential}  — estimated volume or audience overlap

Generation approach:
  - If they have an online application form: generate draft answers
  - If they have a contact email: generate a pitch email
  - Always include: your audience size/type, your use of their product, mutual benefit framing
```

#### Strategy G — "Renewal Negotiation" (for RENEWAL_LEVERAGE gems)

Prepare negotiation strategy for upcoming SaaS renewals.

```
Trigger: renewal_leverage gem with renewal date within 60 days
Channel: email to account manager or reply to renewal notice
Tone: firm but collegial, data-driven

Generation approach:
  - Research: compile usage data, competitive alternatives, pricing benchmarks
  - Draft: negotiation email referencing specific leverage points
  - Include: multi-year discount ask, feature upgrade ask, usage-based pricing ask
  - Context variables: {renewal_date}, {current_price}, {vendor_name}, {competitive_alternatives}
```

#### Strategy H — "Distribution Pitch" (for DISTRIBUTION_CHANNEL gems)

Generate pitches to get featured in newsletters, podcasts, or events.

```
Trigger: distribution_channel gem
Channel: reply to newsletter or dedicated pitch email
Tone: peer-to-peer, brings unique angle

Template context variables:
  - {publication_name}
  - {recent_topic}  — what they recently covered that you can riff on
  - {your_angle}  — unique perspective or data you can contribute
  - {audience_relevance}  — why their audience cares about you
  - {format}  — guest post, interview, data contribution, sponsorship
```

### 10.3 AI Generation Prompt

```
You are generating a personalized engagement message.

STRATEGY: {strategy_name}
GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Size: {company_size}
  ESP: {esp_used}
  Marketing Score: {sophistication}/10
  They sell: {product_description}
  Their pain points: {pain_points}
  Specific observation: {observation}
  Relationship context: {relationship_summary}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write a short engagement message (under 150 words) that:
1. Opens with a specific, non-generic hook referencing real context from the gem
2. Demonstrates insight they'd find valuable (not just flattery)
3. Connects to the specific opportunity this gem represents
4. Ends with a low-friction CTA appropriate to the gem type
5. Addresses {contact_name} by name if available

Do not be sycophantic. Be direct and specific. Sound like a peer, not a vendor.
```

### 10.4 Output Schema

```sql
CREATE TABLE engagement_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gem_id INTEGER REFERENCES gems(id),
    sender_domain TEXT REFERENCES sender_profiles(sender_domain),
    strategy TEXT,
    channel TEXT,
    subject_line TEXT,
    body_text TEXT,
    body_html TEXT,
    status TEXT DEFAULT 'draft',  -- draft / approved / sent / replied
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    response_received BOOLEAN DEFAULT FALSE,
    response_sentiment TEXT       -- positive / neutral / negative (logged manually)
);
```

---

## 11. CLI Interface

```bash
# Full pipeline
gemsieve run --query "newer_than:1y" --all-stages

# Ingestion
gemsieve ingest --query "newer_than:1y"                 # full initial sync
gemsieve ingest --sync                                   # incremental sync via historyId
gemsieve ingest --query "category:promotions" --append   # add specific category

# Parsing (each stage independent)
gemsieve parse --stage metadata
gemsieve parse --stage content
gemsieve parse --stage entities

# Classification
gemsieve classify --model ollama:mistral-nemo
gemsieve classify --model anthropic:claude-sonnet-4-5-20250514 --batch-size 5

# Overrides & feedback
gemsieve override --sender acme.com --field industry --value "Developer Tools"
gemsieve override --message abc123 --field sender_intent --value "partnership_pitch"
gemsieve overrides --list
gemsieve overrides --stats

# Profiling & gem detection
gemsieve profile
gemsieve gems --list                          # all gems, ranked by score
gemsieve gems --type dormant_warm_thread      # filter by gem type
gemsieve gems --segment partner_map           # filter by economic segment
gemsieve gems --top 20                        # top 20 across all types
gemsieve gems --explain <gem_id>              # full explanation for a specific gem

# Engagement generation
gemsieve generate --gem <gem_id>              # generate draft for specific gem
gemsieve generate --strategy audit --top 20   # batch generate for top prospects
gemsieve generate --strategy revival --all    # generate for all dormant threads
gemsieve generate --strategy partner --all    # generate for all partner opportunities

# Analysis & reporting
gemsieve stats                                # overview of inbox intelligence
gemsieve stats --by-esp                       # breakdown by email service provider
gemsieve stats --by-industry                  # breakdown by industry
gemsieve stats --by-segment                   # breakdown by economic segment
gemsieve stats --gem-summary                  # gem distribution and scores
gemsieve export --segment hot                 # export hot leads to CSV
gemsieve export --gems                        # export all gems with explanations
gemsieve export --all                         # export full sender profiles

# Database
gemsieve db --reset                           # wipe and start over
gemsieve db --migrate                         # run pending schema migrations
gemsieve db --stats                           # row counts, DB size
```

---

## 12. Configuration

```yaml
# config.yaml

gmail:
  credentials_file: "credentials.json"
  token_file: "token.json"
  default_query: "newer_than:1y"

storage:
  backend: "sqlite"          # sqlite | postgresql
  sqlite_path: "gemsieve.db"
  # postgres_url: "postgresql://user:pass@localhost/gemsieve"

ai:
  provider: "ollama"         # ollama | anthropic | openai
  model: "mistral-nemo"     # or claude-sonnet-4-5-20250514, gpt-4o, etc.
  ollama_base_url: "http://localhost:11434"
  batch_size: 10             # messages per classification request
  max_body_chars: 2000       # truncate body for AI input

entity_extraction:
  backend: "spacy"           # spacy | ai (route through LLM)
  spacy_model: "en_core_web_trf"  # transformer-based for higher accuracy
  extract_monetary: true
  extract_dates: true
  extract_procurement: true

scoring:
  target_industries:
    - "SaaS"
    - "Agency"
    - "E-commerce"
    - "Marketing"
    - "Developer Tools"
  weights:                   # override default scoring weights
    reachability: 15
    budget_signal: 10
    relevance: 10
    recency: 10
    known_contacts: 10
    monetary_signals: 5
    gem_diversity: 24
    dormant_thread_bonus: 8
    partner_bonus: 5
    renewal_bonus: 3
  dormant_thread:
    min_dormancy_days: 14
    max_dormancy_days: 365   # after this, probably too stale
    require_human_sender: true

engagement:
  your_name: "Brandon"
  your_service: "AI-powered marketing automation and workflow systems"
  your_tone: "direct, technical, peer-to-peer"
  your_audience: "SaaS companies and agencies looking to automate with AI"
  preferred_strategies:
    - "audit"
    - "mirror"
    - "revival"
    - "partner"
  max_outreach_per_day: 20

esp_fingerprints_file: "esp_rules.yaml"
custom_segments_file: "segments.yaml"
```

---

## 13. Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.12+ | Gmail API client, rich ecosystem |
| Gmail API | `google-api-python-client` | Official, well-documented |
| Database | SQLite (default) / PostgreSQL | Portable, upgradeable |
| ORM / Query | Raw SQL via `sqlite3` / `psycopg` | No ORM overhead, full control |
| HTML Parsing | `BeautifulSoup4` + `lxml` | Robust against malformed email HTML |
| NER / Entities | `spaCy` with `en_core_web_trf` | Accurate NER, runs locally on GPU |
| AI Local | Ollama via HTTP API | Free, private, runs on RTX 4090 |
| AI Cloud | Anthropic API (Claude) | Higher quality classification |
| CLI | `typer` | Clean subcommand interface, auto-generated help |
| Config | YAML via `pyyaml` | Human-readable, easy to edit |
| Export | `csv` stdlib + `openpyxl` | CSV and Excel output |

---

## 14. Privacy & Legal Considerations

- All data stays local by default. No sender data leaves your machine unless you explicitly use a cloud AI provider.
- When using cloud AI, only send the minimum context needed (truncated body text, no full headers).
- This system processes emails YOU received — you are not scraping anyone's systems.
- Outreach should comply with CAN-SPAM: include your identity, physical address, and opt-out mechanism.
- The engagement generator produces DRAFTS for human review. No auto-sending.
- Respect unsubscribe requests if anyone replies asking you to stop.
- Entity extraction (names, roles, monetary values) stays in local DB. Never export PII in bulk without user intent.

---

## 15. Future Extensions

- **LinkedIn enrichment** — cross-reference sender domains with LinkedIn company data for richer profiles
- **Website scraping** — fetch sender's homepage to extract pricing tiers, team size, tech stack (via BuiltWith-style analysis)
- **Response tracking** — log when outreach gets replies, feed back into scoring to improve the opportunity model
- **A/B testing** — generate multiple outreach variants per gem, track which strategy/tone converts better
- **CRM sync** — push gems and engagement history to HubSpot, Pipedrive, or Airtable
- **Real-time mode** — webhook/push listener that scores and classifies new emails as they arrive, surfaces gems immediately
- **Chrome extension** — overlay gem scores and sender intelligence directly in Gmail UI
- **Gem lifecycle tracking** — track gems from detection → action → outcome, build a conversion funnel
- **Cross-inbox analysis** — support multiple Gmail accounts, merge intelligence across business + personal

---

## 16. Success Metrics

| Metric | Target |
|--------|--------|
| Messages ingested | 10,000+ |
| Unique sender profiles built | 500+ |
| ESP identification accuracy | >90% |
| AI classification confidence (avg) | >0.75 |
| Entity extraction precision (people + orgs) | >85% |
| Gems detected | 100+ |
| Gem diversity (unique types surfaced) | all 9 types represented |
| Dormant threads recovered | 20+ actionable threads |
| Partner programs identified | 10+ |
| Renewal windows flagged | all active subscriptions |
| Override rate (classification corrections) | <20% (indicates good baseline accuracy) |
| Outreach reply rate | >10% (vs. 1-2% cold outreach baseline) |
| Revenue conversations started | 5+ in first month |
| Partner revenue activated | 2+ programs joined in first month |