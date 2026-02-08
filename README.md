# GemSieve

Gmail inbox intelligence pipeline. Transforms your inbox into a structured revenue graph by extracting sender profiles, detecting commercial opportunities ("gems"), and generating personalized engagement drafts.

## What it does

GemSieve runs an 8-stage pipeline over your Gmail inbox:

```
Gmail  -->  Ingestion  -->  Metadata  -->  Content  -->  Entity  -->  AI       -->  Profiler  -->  Engagement
Inbox       & Sync         Extract       Parser       Extract      Classify      & Scorer       Generator
              |               |             |            |             |             |              |
              v               v             v            v             v             v              v
         Raw messages    ESP/infra      Clean text   People, orgs  Industry,     Sender        Outreach
         + threads      fingerprints   CTAs, offers  money, dates  intent, size  profiles +    drafts
         + historyId                   links                       product type  gems scored
```

| Stage | Name | AI Required |
|-------|------|-------------|
| 0 | Ingestion & Sync | No |
| 1 | Metadata Extraction (header forensics, ESP fingerprinting, mail server, X-Mailer) | No |
| 2 | Content Parsing (HTML, offers, CTAs, links, footer stripping) | No |
| 3 | Entity Extraction (people, orgs, money, dates, relationship classification) | No (spaCy NLP) |
| 4 | AI Classification (industry, intent, sophistication) + feedback loop | Yes |
| 5 | Sender Profiling & Gem Detection (warm signals, deterministic scoring) | No (rule-based) |
| 6 | Segmentation & Opportunity Scoring | No |
| 7 | Engagement Draft Generation | Yes |

Stages 0-3 require no AI provider and are valuable on their own. Each stage is independently re-runnable and idempotent.

## Gem types

GemSieve detects 10 types of commercial opportunities:

| Gem Type | What it finds |
|----------|--------------|
| `dormant_warm_thread` | Stalled conversations with warm signals (pricing questions, meeting requests, decision-maker involvement) |
| `unanswered_ask` | Recent messages awaiting your response |
| `weak_marketing_lead` | Senders with marketing gaps you can fill |
| `partner_program` | Vendors with affiliate/reseller programs you can join |
| `renewal_leverage` | Upcoming SaaS renewals = negotiation windows |
| `vendor_upsell` | Vendors pitching upgrades (they value your business) |
| `distribution_channel` | Newsletters/podcasts/events that could amplify you (includes content opportunity signals like guest posts, speaker applications) |
| `co_marketing` | Senders whose audience overlaps with yours (requires `engagement.your_audience` config) |
| `industry_intel` | Senders providing useful market intelligence |
| `procurement_signal` | Active buying or vendor evaluation signals |

Every gem includes a structured explanation with confidence score, **estimated value** (low/medium/high), **urgency** level, and recommended next actions.

## Installation

Requires Python 3.12+.

```bash
# Clone and install
cd gemail
pip install -e .

# For the web admin interface
pip install -e ".[web]"

# For development (adds pytest)
pip install -e ".[dev]"

# Download spaCy model for entity extraction (Stage 3)
python -m spacy download en_core_web_sm    # fast, good enough for most use
python -m spacy download en_core_web_trf   # transformer-based, higher accuracy
```

### Gmail API setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select an existing one)
3. Enable the **Gmail API**
4. Create **OAuth 2.0 credentials** (Desktop application type)
5. Download the credentials JSON and save as `credentials.json` in your working directory

On the first run, GemSieve will open a browser window for OAuth consent. The token is cached to `token.json` for subsequent runs.

### AI provider setup

GemSieve supports two AI backends for classification (Stage 4) and engagement generation (Stage 7):

**Ollama (local, free, private):**
```bash
# Install Ollama: https://ollama.ai
ollama pull mistral-nemo
# GemSieve uses http://localhost:11434 by default
```

**Ollama Cloud (hosted, no local GPU needed):**

Create a `.env` file in your working directory:

```bash
ollama_host=https://ollama.com
ollama_api_key=your-api-key-here
model_name=mistral-large-3:675b-cloud
```

GemSieve automatically loads `.env` and maps these variables to the AI config. No `config.yaml` changes needed. The API key is sent as a `Bearer` token in the `Authorization` header.

**Anthropic (cloud, higher quality):**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Use with: gemsieve classify --model anthropic:claude-sonnet-4-5-20250514
```

**CrewAI multi-agent mode (advanced):**

GemSieve can use CrewAI to orchestrate multiple specialized AI agents for classification and engagement. This provides structured output validation, automatic retries, and agent-chained reasoning:

```bash
# Classify with CrewAI agents
gemsieve classify --crew

# Generate engagement drafts with CrewAI agents
gemsieve generate --crew --gem 42
```

See the [CrewAI integration](#crewai-multi-agent-mode) section below for details.

## Configuration

Copy the example config and customize:

```bash
cp config.example.yaml config.yaml
```

GemSieve searches for config in this order:
1. `$GEMSIEVE_CONFIG` environment variable
2. `./config.yaml` (current directory)
3. `~/.config/gemsieve/config.yaml`

If no config file is found, sensible defaults are used.

### Environment variable overrides

GemSieve loads `.env` from the current directory and supports these environment variables (they override `config.yaml`):

| Variable | Config field | Description |
|----------|-------------|-------------|
| `ollama_host` | `ai.ollama_base_url` | Ollama API endpoint (e.g., `https://ollama.com`) |
| `ollama_api_key` | `ai.ollama_api_key` | Bearer token for authenticated Ollama endpoints |
| `model_name` | `ai.model` | Model name override (e.g., `mistral-large-3:675b-cloud`) |
| `ANTHROPIC_API_KEY` | (standard) | Anthropic SDK reads this automatically |
| `GEMSIEVE_CONFIG` | (path) | Path to config YAML file |
| `DATABASE_URL` | (connection string) | SQLAlchemy database URL (default: `sqlite:///gemsieve.db`) |

Environment variables take precedence over config file values but do not override CLI `--model` flags.

### Key config sections

```yaml
gmail:
  credentials_file: "credentials.json"
  token_file: "token.json"
  default_query: "newer_than:1y"          # default Gmail search scope

storage:
  sqlite_path: "gemsieve.db"              # local database path

ai:
  provider: "ollama"                       # ollama | anthropic
  model: "mistral-nemo"                   # model name
  ollama_base_url: "http://localhost:11434" # or https://ollama.com for cloud
  ollama_api_key: ""                       # API key for Ollama cloud
  batch_size: 10                           # messages per classification batch
  max_body_chars: 2000                     # body text truncation for AI input

entity_extraction:
  spacy_model: "en_core_web_sm"            # or en_core_web_trf for accuracy
  extract_monetary: true                   # toggle monetary entity extraction
  extract_dates: true                      # toggle date entity extraction
  extract_procurement: true                # toggle procurement signal extraction

scoring:
  target_industries:                       # industries you want to sell to
    - "SaaS"
    - "Agency"
    - "E-commerce"
  weights:                                 # tune opportunity scoring formula
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
  dormant_thread:                          # dormant thread gem detection tuning
    min_dormancy_days: 14
    require_human_sender: true             # skip auto-generated/transactional threads

engagement:
  your_name: "Brandon"
  your_service: "AI-powered marketing automation"
  your_tone: "direct, technical, peer-to-peer"
  your_audience: "SaaS companies and agencies"  # used for co_marketing audience overlap
  preferred_strategies:                    # only generate drafts for these strategies
    - "audit"
    - "revival"
    - "partner"
    - "renewal_negotiation"
    - "industry_report"
    - "mirror"
    - "distribution_pitch"
  max_outreach_per_day: 10                 # daily engagement draft limit
```

See `config.example.yaml` for the full reference with all options.

## Usage

### Quick start — full pipeline

```bash
# Initialize the database
gemsieve db --reset

# Run everything (requires Gmail credentials + AI provider)
gemsieve run --query "newer_than:1y" --all-stages

# View results
gemsieve gems --top 20
gemsieve gems --explain 1
```

### Stage-by-stage execution

Run each stage independently for more control:

```bash
# Stage 0: Pull messages from Gmail (content-aware thread response tracking)
gemsieve ingest --query "newer_than:1y"
gemsieve ingest --query "category:promotions" --append   # add specific category
gemsieve ingest --sync                                    # incremental sync

# Stage 1: Parse email headers, identify ESPs, extract X-Mailer/mail server
gemsieve parse --stage metadata

# Stage 2: Parse HTML content, extract offers/CTAs/links, strip marketing footers
gemsieve parse --stage content

# Stage 3: Extract entities (people, orgs, money, dates) with relationship classification
gemsieve parse --stage entities

# Stage 4: AI classification
gemsieve classify --model ollama:mistral-nemo
gemsieve classify --model anthropic:claude-sonnet-4-5-20250514 --batch-size 5
gemsieve classify --retrain                      # append few-shot corrections from overrides

# Stage 5: Build profiles and detect gems
gemsieve profile
gemsieve gems                     # runs gem detection
gemsieve gems --list              # view all gems
gemsieve gems --top 20            # top 20 by score

# Stage 7: Generate engagement drafts (7 strategy-specific prompts)
gemsieve generate --gem 42                       # specific gem
gemsieve generate --strategy audit --top 20      # batch by strategy
gemsieve generate --strategy revival --all       # all dormant threads
```

### Viewing results

```bash
# Overview statistics
gemsieve stats
gemsieve stats --by-esp              # breakdown by email service provider
gemsieve stats --by-industry         # breakdown by industry
gemsieve stats --by-segment          # breakdown by economic segment
gemsieve stats --gem-summary         # gem type distribution and scores

# Gem exploration
gemsieve gems --list                              # all gems, ranked by score
gemsieve gems --type dormant_warm_thread          # filter by gem type
gemsieve gems --segment partner_map               # filter by segment
gemsieve gems --top 20                            # top 20 across all types
gemsieve gems --explain 42                        # full explanation for gem #42
```

### Web admin interface

GemSieve includes a browser-based admin portal for pipeline control, data inspection, and AI transparency.

```bash
# Install web dependencies
pip install -e ".[web]"

# Initialize the database (if not already done)
gemsieve db --reset

# Start the web admin
gemsieve web                     # http://localhost:8000/admin
gemsieve web --port 9000         # custom port
gemsieve web --reload            # auto-reload for development
```

Or run directly with uvicorn:

```bash
uvicorn gemsieve.web.app:create_app --factory --reload
```

The admin UI provides:

- **Dashboard** — stats cards, Chart.js graphs (gem distribution, industry breakdown, ESP usage, top gems by score), pipeline health indicators, recent activity feed
- **Pipeline Control** — trigger any stage from the browser, run all stages sequentially, live SSE progress streaming, run history with status/duration/item counts. Supports `--retrain` toggle for classification.
- **AI Inspector** — full audit trail of every AI call: rendered prompts, system prompts, raw/parsed responses, model used, duration. Filterable by stage and sender domain. Includes a **strategy prompt library** showing all 7 engagement strategies with gem type mappings.
- **Gem Explorer** — filterable card grid of all gems with score bars, **estimated value/urgency badges**, signal chips, recommended actions, urgency filter dropdown, and a "Generate Draft" button that triggers engagement generation
- **CRUD table views** — browse and search all 16 database tables (messages, threads, metadata, content, entities, classifications, profiles, gems, segments, drafts, pipeline runs, AI audit log)

For detailed documentation on every view and feature, see the [Web Admin Manual](docs/manual.md).

The web admin uses SQLAlchemy against the same SQLite database the CLI uses. Both work independently. Set `DATABASE_URL` in `.env` to switch to PostgreSQL:

```bash
DATABASE_URL=postgresql://user:pass@localhost/gemsieve
```

### Classification overrides

Correct AI classifications that are wrong. Overrides feed back into future runs via the few-shot feedback loop:

```bash
# Override at the sender level (applies to all messages from that domain)
gemsieve override --sender acme.com --field industry --value "Developer Tools"

# Override a specific message (message-scoped, highest priority)
gemsieve override --message abc123 --field sender_intent --value "partnership_pitch"

# View and audit overrides
gemsieve overrides --list
gemsieve overrides --stats           # shows override rate per field

# Re-classify with feedback: appends recent overrides as few-shot corrections
gemsieve classify --retrain
```

Overridable fields: `industry`, `company_size_estimate`, `marketing_sophistication`, `sender_intent`, `product_type`, `product_description`, `target_audience`.

Override scopes:
- **sender** — applies to all messages from that domain
- **message** — applies to a single message, overrides sender-scoped values

When `--retrain` is used, the last 10 overrides are formatted as few-shot correction examples and appended to the classification prompt, improving accuracy over time.

### Exporting data

```bash
gemsieve export --gems                        # all gems with explanations to CSV
gemsieve export --segment hot                 # sender profiles in a segment
gemsieve export --all                         # all sender profiles
gemsieve export --all --format excel          # Excel format
gemsieve export --gems --output my_gems.csv   # custom output path
```

### Database management

```bash
gemsieve db --stats      # row counts for all 16 tables
gemsieve db --reset      # wipe and recreate (destructive!)
gemsieve db --migrate    # apply schema updates
```

## Economic segments

Each sender can belong to multiple segments simultaneously:

| Segment | What it tracks |
|---------|---------------|
| **Spend Map** | Companies you pay — sub-segments: active_subscription, upcoming_renewal, churned_vendor |
| **Partner Map** | Companies with affiliate/reseller programs — sub-segments: referral_program, general |
| **Prospect Map** | Companies you could sell to — sub-segments: hot_lead, warm_prospect, intelligence_value |
| **Dormant Threads** | Stalled conversations with commercial potential |
| **Distribution Map** | Newsletters, podcasts, events — sub-segments: newsletter, event_organizer, community |
| **Procurement Map** | Active buying signals — sub-segments: security_compliance, formal_rfp, evaluation |

Custom segments can be defined in `segments.yaml`:

```yaml
custom_segments:
  - name: "AI-ready small businesses"
    rules:
      company_size: "small"
      industry: ["SaaS", "Agency", "Marketing"]
      marketing_sophistication_avg: {"lt": 5}
    priority: "hot"

  - name: "Partner revenue targets"
    rules:
      has_partner_program: true
      industry: ["SaaS", "Developer Tools"]
    priority: "hot"
```

## Opportunity scoring

Every gem is scored 0-100 based on a configurable formula:

**Base profile score (max 60):**
- Reachability (company size — smaller = easier to reach decision-makers)
- Budget signal (ESP tier indicates marketing spend)
- Industry relevance (matches your target industries)
- Recency (last contact within 30/90 days)
- Known contacts (named people with roles from entity extraction)
- Monetary signals (pricing, contract values detected)

**Gem diversity bonus (max 40):**
- Each unique gem type for a sender adds points
- Dormant warm thread bonus (+8) — someone already wants to talk
- Partner program bonus (+5) — passive revenue potential
- Renewal leverage bonus (+3) — time-sensitive negotiation window

All weights are configurable in `config.yaml` under `scoring.weights`.

## Strategy-specific engagement

Stage 7 uses 7 distinct strategy prompts tailored to each gem type, rather than a single generic prompt:

| Strategy | Gem Types | Approach |
|----------|-----------|----------|
| `audit` | weak_marketing_lead, vendor_upsell | "I Audited Your Funnel" — consultative outreach with specific observations |
| `revival` | dormant_warm_thread, unanswered_ask | Thread revival with context-aware follow-up referencing the original conversation |
| `partner` | partner_program | Partner program application/inquiry with mutual value proposition |
| `renewal_negotiation` | renewal_leverage | Data-driven renewal negotiation citing market alternatives |
| `industry_report` | industry_intel | Content-led engagement invitation using shared industry data |
| `mirror` | co_marketing | Mirror-match style — match the sender's sophistication and tone |
| `distribution_pitch` | distribution_channel | Pitch to get featured in their newsletter/podcast/event |

Each strategy assembles context-specific variables (thread history for revival, renewal dates for negotiation, partner URLs for partner applications) and enforces the configured tone and audience.

The `preferred_strategies` config option filters which strategies are generated. The `max_outreach_per_day` config enforces a daily draft limit. Both filters are bypassed when generating for a specific `--gem` ID.

## ESP fingerprinting

GemSieve identifies 12 email service providers from header analysis:

SendGrid, Mailchimp, HubSpot, Klaviyo, Constant Contact, Amazon SES, ConvertKit, ActiveCampaign, Salesforce Marketing Cloud, Postmark, Mailgun, and custom SMTP.

Rules are defined in `esp_rules.yaml` and can be extended with custom patterns.

## Project structure

```
gemail/
├── pyproject.toml
├── config.example.yaml
├── esp_rules.yaml              # ESP fingerprinting rules
├── segments.yaml               # custom segment definitions
├── docs/
│   ├── spec-1.md               # full specification
│   ├── manual.md               # web admin manual
│   └── views/                  # per-view documentation (19 pages)
├── src/gemsieve/
│   ├── cli.py                  # all CLI commands (incl. `web`)
│   ├── config.py               # YAML config + validated dataclasses
│   ├── database.py             # SQLite connection + schema management
│   ├── schema.sql              # 16 CREATE TABLE statements
│   ├── models.py               # domain dataclasses
│   ├── esp_rules.py            # ESP fingerprint matcher
│   ├── overrides.py            # classification override CRUD
│   ├── export.py               # CSV/Excel export
│   ├── gmail/
│   │   ├── auth.py             # OAuth2 authentication
│   │   ├── client.py           # Gmail API wrapper
│   │   └── sync.py             # full + incremental sync engine
│   ├── stages/
│   │   ├── metadata.py         # Stage 1: header forensics
│   │   ├── content.py          # Stage 2: HTML parsing, offers, CTAs
│   │   ├── entities.py         # Stage 3: spaCy NER + regex
│   │   ├── classify.py         # Stage 4: AI classification
│   │   ├── profile.py          # Stage 5: profiles + gem detection
│   │   ├── segment.py          # Stage 6: segmentation + scoring
│   │   └── engage.py           # Stage 7: engagement generation
│   ├── ai/
│   │   ├── __init__.py         # get_provider() factory
│   │   ├── base.py             # AIProvider protocol
│   │   ├── ollama.py           # Ollama HTTP client
│   │   ├── anthropic_provider.py
│   │   ├── crews.py            # CrewAI multi-agent orchestration
│   │   └── prompts.py          # classification + 7 strategy engagement prompts
│   └── web/                    # Web admin (optional: pip install -e ".[web]")
│       ├── app.py              # FastAPI app factory
│       ├── db.py               # SQLAlchemy engine + session
│       ├── models.py           # SQLAlchemy ORM models (all 16 tables)
│       ├── admin.py            # Starlette-Admin ModelViews
│       ├── api.py              # REST API (pipeline, stats, SSE, AI audit)
│       ├── tasks.py            # TaskManager + LoggingAIProvider
│       ├── views/
│       │   ├── dashboard.py    # Dashboard CustomView
│       │   ├── pipeline.py     # Pipeline Control CustomView
│       │   ├── ai_inspector.py # AI Inspector CustomView
│       │   └── gem_explorer.py # Gem Explorer CustomView
│       ├── templates/
│       │   ├── dashboard.html
│       │   ├── pipeline.html
│       │   ├── ai_inspector.html
│       │   └── gem_explorer.html
│       └── static/
│           └── css/
│               └── custom.css
└── tests/
    ├── conftest.py             # shared fixtures (in-memory DB, sample data)
    ├── test_database.py
    ├── test_config.py
    ├── test_gmail_sync.py
    ├── test_stage_metadata.py
    ├── test_stage_content.py
    ├── test_stage_entities.py
    ├── test_stage_classify.py
    ├── test_stage_profile.py
    ├── test_stage_engage.py
    └── test_cli.py
```

## Development

```bash
# Install with all optional dependencies
pip install -e ".[dev,web]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=gemsieve --cov-report=term-missing

# Run web admin with auto-reload
gemsieve web --reload
```

The test suite uses in-memory SQLite databases and mocks external services (Gmail API, AI providers). Entity extraction tests are automatically skipped on Python 3.14 due to a spaCy/pydantic compatibility issue.

## Architecture notes

- **Database as integration bus** — stages don't import each other. They communicate through the database. This makes every stage independently re-runnable.
- **"Process unprocessed" pattern** — each stage uses a `LEFT JOIN` anti-pattern to find messages not yet in its output table. Running a stage twice is always safe.
- **No ORM for the CLI** — raw SQL with `sqlite3.Row` for dict-like access. Models in `models.py` are for type safety only. The web admin uses SQLAlchemy ORM models against the same database.
- **CLI + Web coexistence** — the CLI uses raw `sqlite3` connections, the web admin uses SQLAlchemy. Both operate on the same database independently. The web layer calls the same stage functions the CLI uses.
- **Pluggable AI** — `AIProvider` protocol with `ollama` and `anthropic` implementations. Model spec format: `provider:model_name`.
- **AI audit trail** — when pipeline stages run from the web admin, a `LoggingAIProvider` wrapper records every AI call (prompt, response, model, duration) to the `ai_audit_log` table for full transparency. Strategy-specific prompts are logged with their strategy name (e.g., `STRATEGY_audit`).
- **Gem detection is rule-based** — deterministic logic, not AI. Every gem explains itself with structured signals and evidence. Reproducible and auditable.
- **Warm signal detection** — dormant thread gems use entity cross-referencing (money signals, decision-makers) and regex-based warm signal scanning (pricing questions, meeting requests, follow-ups) to avoid surfacing low-value threads.
- **Deterministic sophistication scoring** — a 10-point formula based on ESP tier, personalization, UTM tracking, template quality, authentication (SPF/DKIM/DMARC), and unsubscribe presence. Blended 60/40 with AI-provided scores.
- **Classification feedback loop** — `--retrain` appends the last 10 classification overrides as few-shot correction examples to the prompt, improving accuracy over time without model fine-tuning.
- **Content-aware thread tracking** — thread response detection uses question/concluded signal patterns (not just sent/received heuristics) to accurately determine who owes a reply.

## CrewAI multi-agent mode

GemSieve includes an optional CrewAI integration that replaces the single-prompt AI calls with a multi-agent pipeline. This provides:

- **Structured output validation** — Pydantic schemas enforce correct JSON output; invalid responses are automatically retried
- **Specialized agents** — separate analyst (classification) and copywriter (engagement) agents with tailored roles and backstories
- **Task chaining** — classification output flows as context into engagement generation
- **Guardrails** — configurable validation (e.g., reject low-confidence classifications)

### How it works

In standard mode, Stages 4 and 7 make direct LLM calls via the `AIProvider` protocol. In CrewAI mode, they orchestrate through CrewAI's `Agent -> Task -> Crew` pattern:

```
Standard:  classify.py → OllamaProvider.complete() → parse JSON → store
CrewAI:    classify.py → Crew(classifier_agent, task) → Pydantic model → store
```

### Usage

```bash
# Classification with CrewAI agents
gemsieve classify --crew
gemsieve classify --crew --model ollama:mistral-nemo

# Engagement with CrewAI agents
gemsieve generate --crew --gem 42
gemsieve generate --crew --strategy audit --top 10

# Full pipeline with CrewAI for AI stages
gemsieve run --all-stages --crew
```

The `--crew` flag is opt-in. Without it, GemSieve uses the standard direct-call approach (faster, fewer dependencies). CrewAI mode is recommended when you want higher-quality structured outputs and are willing to accept slightly higher latency.

### Agents

| Agent | Role | Used in |
|-------|------|---------|
| **Email Intelligence Analyst** | Classifies senders by industry, intent, sophistication | Stage 4 |
| **B2B Outreach Strategist** | Generates personalized engagement messages | Stage 7 |

### Requirements

CrewAI is an optional dependency:

```bash
pip install -e ".[crew]"
```

## Privacy

- All data stays local by default. No data leaves your machine unless you use a cloud AI provider.
- When using Anthropic, only truncated body text is sent (configurable via `ai.max_body_chars`).
- The system processes emails you received — it does not scrape external systems.
- Engagement drafts are for human review. There is no auto-sending.
