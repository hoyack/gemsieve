# GemSieve Web Admin Manual

The GemSieve web admin is a browser-based portal for controlling the pipeline, inspecting data, auditing AI decisions, and exploring commercial opportunities detected in your inbox.

## Getting started

```bash
# Install web dependencies
pip install -e ".[web]"

# Initialize the database
gemsieve db --reset

# Start the web admin
gemsieve web                   # http://localhost:8000/admin
gemsieve web --port 9000       # custom port
gemsieve web --reload          # auto-reload for development
```

Or run directly with uvicorn:

```bash
uvicorn gemsieve.web.app:create_app --factory --host 0.0.0.0 --port 8000
```

The admin UI is available at `http://localhost:8000/admin`. The root URL (`/`) redirects to the admin.

## Navigation

The sidebar contains all available views, organized into sections:

### Custom views (top of sidebar)

These are purpose-built interactive pages:

| View | Icon | Description | Guide |
|------|------|-------------|-------|
| [Dashboard](views/dashboard.md) | Home | Pipeline health, stats cards, charts | Overview of your entire pipeline |
| [Pipeline Control](views/pipeline.md) | Play | Trigger stages, monitor progress, run history | Run and monitor pipeline stages |
| [AI Inspector](views/ai-inspector.md) | Search | Full AI audit trail with prompts and responses | Audit every AI decision |
| [Gem Explorer](views/gem-explorer.md) | Gem | Filterable gem cards with scores and actions | Find and act on opportunities |

### Data table views (sidebar sections)

These are CRUD-style table views for browsing and searching all database tables:

**Ingested data:**

| View | Icon | Stage | Guide |
|------|------|-------|-------|
| [Messages](views/messages.md) | Envelope | Stage 0 | Raw email messages |
| [Threads](views/threads.md) | Comments | Stage 0 | Conversation threads |
| [Attachments](views/attachments.md) | Paperclip | Stage 0 | Email attachments |

**Stage outputs:**

| View | Icon | Stage | Guide |
|------|------|-------|-------|
| [Metadata](views/metadata.md) | Fingerprint | Stage 1 | Header forensics, ESP fingerprints |
| [Temporal](views/temporal.md) | Clock | Stage 1 | Sender timing patterns |
| [Content](views/content.md) | File | Stage 2 | Parsed HTML, offers, CTAs |
| [Entities](views/entities.md) | Tags | Stage 3 | Extracted people, orgs, dates |

**Classification:**

| View | Icon | Stage | Guide |
|------|------|-------|-------|
| [Classifications](views/classifications.md) | Brain | Stage 4 | AI-assigned industry, intent, size |
| [Overrides](views/overrides.md) | Edit | Stage 4 | Manual corrections to AI output |

**Profiles and gems:**

| View | Icon | Stage | Guide |
|------|------|-------|-------|
| [Profiles](views/profiles.md) | Building | Stage 5 | Sender company profiles |
| [Gems](views/gems.md) | Gem | Stage 5 | Detected commercial opportunities |
| [Segments](views/segments.md) | Layer Group | Stage 6 | Economic segmentation |

**Engagement:**

| View | Icon | Stage | Guide |
|------|------|-------|-------|
| [Drafts](views/drafts.md) | Paper Plane | Stage 7 | Generated outreach messages |

**System:**

| View | Icon | Description | Guide |
|------|------|-------------|-------|
| [Pipeline Runs](views/pipeline-runs.md) | Play Circle | Execution history | Track every pipeline run |
| [AI Audit Log](views/ai-audit-log.md) | Search | AI call records | Full prompt/response pairs |

## Typical workflow

### First-time setup

1. Ingest emails via CLI: `gemsieve ingest --query "newer_than:6m"`
2. Open the web admin at `http://localhost:8000/admin`
3. Go to [Pipeline Control](views/pipeline.md) and click **Run All (Stages 1-6)** to process everything
4. Go to [Dashboard](views/dashboard.md) to see stats and charts
5. Go to [Gem Explorer](views/gem-explorer.md) to browse detected opportunities
6. Click **Generate Draft** on promising gems to create outreach messages

### Ongoing use

1. Run `gemsieve ingest --sync` periodically to pull new messages
2. Open [Pipeline Control](views/pipeline.md) and run stages 1-6 to process new data
3. Check [Dashboard](views/dashboard.md) for updated pipeline health
4. Browse [Gem Explorer](views/gem-explorer.md) for new opportunities
5. Use [AI Inspector](views/ai-inspector.md) to audit any AI classification you want to verify
6. Add [Overrides](views/overrides.md) to correct any misclassifications

### Investigating a sender

1. Search for the domain in [Messages](views/messages.md) to see all emails from them
2. Check [Metadata](views/metadata.md) for their ESP and authentication details
3. View [Content](views/content.md) for their marketing content analysis
4. See [Classifications](views/classifications.md) for the AI's assessment
5. Open [Profiles](views/profiles.md) for the aggregated sender profile
6. Check [Gems](views/gems.md) for any opportunities linked to them
7. Use [AI Inspector](views/ai-inspector.md) to see exactly what the AI was given and how it responded

## REST API

The web admin exposes a REST API at `/api/` for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/run/{stage}` | POST | Trigger a pipeline stage (or `all` for stages 1-6) |
| `/api/pipeline/status/{run_id}` | GET | Get run status |
| `/api/pipeline/runs` | GET | List recent pipeline runs |
| `/api/pipeline/stream` | GET | SSE endpoint for live progress updates |
| `/api/stats` | GET | Dashboard statistics (table counts) |
| `/api/stats/gems-by-type` | GET | Gem type distribution |
| `/api/stats/gems-top/{n}` | GET | Top N gems by score |
| `/api/stats/by-industry` | GET | Industry breakdown |
| `/api/stats/by-esp` | GET | ESP distribution |
| `/api/stats/pipeline-activity` | GET | Recent pipeline activity |
| `/api/stages` | GET | Stage info with row counts and last run |
| `/api/gems/{gem_id}/generate` | POST | Trigger engagement for a specific gem |
| `/api/ai-audit` | GET | List AI audit entries (supports `?stage=`, `?limit=`, `?offset=`) |
| `/api/ai-audit/{audit_id}` | GET | Full audit entry with prompt/response |

## Database

The web admin uses SQLAlchemy ORM against the same SQLite database the CLI uses. Both work independently. To switch to PostgreSQL, set `DATABASE_URL` in your `.env`:

```bash
DATABASE_URL=postgresql://user:pass@localhost/gemsieve
```

The default is `sqlite:///gemsieve.db`.
