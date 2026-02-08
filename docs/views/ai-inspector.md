# AI Inspector

[Back to Manual](../manual.md)

The AI Inspector provides full transparency into every AI call made by the pipeline. Every time the classify or engage stage calls the AI model, the complete prompt, response, timing, and metadata are recorded and displayed here.

## Filters

At the top of the page, filter the audit log by:

- **Stage** — `classify` or `engage` (or all)
- **Domain** — filter by sender domain to see all AI calls related to a specific sender

Click **Filter** to apply, or **Reset** to clear all filters.

The total entry count and current page are shown on the right.

## Prompt library

A collapsible accordion section shows all prompt templates used by GemSieve. Each section is expandable and shows the template text with variable placeholders highlighted.

### CLASSIFICATION_PROMPT (Stage 4)

Variables filled in per sender:
- `{from_name}` — sender display name
- `{from_address}` — sender email address
- `{subject}` — email subject line
- `{esp_identified}` — detected email service provider
- `{offer_types}` — detected offer types from content parsing
- `{cta_texts}` — call-to-action text extracted from the email
- `{extracted_entities_summary}` — summary of entities found (people, orgs, etc.)
- `{body_clean}` — cleaned email body text (truncated to max_body_chars)

The AI responds with a JSON object containing: industry, company_size_estimate, marketing_sophistication (1-10), sender_intent, product_type, product_description, pain_points_addressed, target_audience, partner_program_detected, renewal_signal_detected, and confidence.

When `--retrain` is used, few-shot correction examples from recent classification overrides are appended to the prompt. These appear as `CORRECTION:` blocks showing what the AI got wrong and what the correct value should be.

### Strategy prompts (Stage 7)

Stage 7 uses 7 distinct strategy-specific prompts instead of a single generic engagement prompt. Each prompt is shown in a collapsible accordion panel with its gem type mappings listed:

| Strategy | Template ID | Gem Types | Extra Variables |
|----------|-------------|-----------|-----------------|
| **audit** | STRATEGY_audit | weak_marketing_lead, vendor_upsell | Observation from offer/CTA analysis |
| **revival** | STRATEGY_revival | dormant_warm_thread, unanswered_ask | `{thread_subject}`, `{dormancy_days}` |
| **partner** | STRATEGY_partner | partner_program | `{partner_urls}` |
| **renewal_negotiation** | STRATEGY_renewal_negotiation | renewal_leverage | `{renewal_dates}`, `{monetary_signals}` |
| **industry_report** | STRATEGY_industry_report | industry_intel | Industry data and trends |
| **mirror** | STRATEGY_mirror | co_marketing | Target audience overlap analysis |
| **distribution_pitch** | STRATEGY_distribution_pitch | distribution_channel | Content opportunity signals |

All strategy prompts share these common variables:
- `{gem_type}`, `{gem_explanation_json}` — gem context
- `{company_name}`, `{contact_name}`, `{contact_role}` — recipient info
- `{industry}`, `{company_size}`, `{esp_used}`, `{sophistication}` — sender profile
- `{product_description}`, `{pain_points}` — product context
- `{user_service_description}`, `{user_tone}`, `{user_audience}` — your positioning from config

The AI responds with a JSON object containing `subject_line` and `body`.

### DEFAULT_ENGAGEMENT_PROMPT (fallback)

Used when a gem type doesn't map to any strategy. Contains generic engagement template variables. This prompt is rarely used since all 10 gem types map to specific strategies.

## Audit log entries

Each entry is displayed as a card showing:

**Header:**
- Stage badge (classify/engage)
- Template badge — identifies which prompt was used: `CLASSIFICATION_PROMPT`, `STRATEGY_audit`, `STRATEGY_revival`, `STRATEGY_partner`, `STRATEGY_renewal_negotiation`, `STRATEGY_industry_report`, `STRATEGY_mirror`, `STRATEGY_distribution_pitch`, or `ENGAGEMENT_PROMPT` (fallback)
- Model badge (e.g., `mistral-large-3:675b-cloud`)
- Sender domain badge
- Entry ID and pipeline run ID
- Duration in milliseconds
- Timestamp

**Collapsible sections** (click to expand):

| Section | What it shows |
|---------|--------------|
| **Rendered Prompt** | The complete prompt text sent to the AI, with all variables filled in. This is the exact input the model received. |
| **System Prompt** | The system/role instruction (e.g., "You are an email intelligence analyst. Respond with JSON only.") |
| **Raw Response** | The AI model's raw output text |
| **Parsed Response** | The structured JSON parsed from the response (shown separately only if different from raw) |

## Pagination

If there are many entries, pagination controls appear at the bottom. Filter parameters are preserved across pages.

## How to use

### Verify a classification

1. Find the sender domain in the [Classifications](classifications.md) view
2. Come to AI Inspector and filter by that domain
3. Expand the **Rendered Prompt** to see what information was given to the AI
4. Expand the **Raw Response** to see the AI's full answer
5. If the classification is wrong, add an [Override](overrides.md)

### Compare AI behavior

1. Filter by stage (e.g., `classify`)
2. Look at duration_ms to identify slow or fast calls
3. Expand prompts for different domains to compare how the same template handles different senders
4. Check model_used to verify which model was active

### Debug a failed classification

1. If a sender has no classification, check here to see if the AI call was made
2. If no entry exists, the stage may not have been run or the sender didn't match the query criteria
3. If an entry exists with a malformed response, the prompt might need more/better input data

## Related views

- [Classifications](classifications.md) — the AI output stored per message
- [Overrides](overrides.md) — correct classifications the AI got wrong
- [Pipeline Runs](pipeline-runs.md) — which pipeline run triggered each AI call
- [AI Audit Log](ai-audit-log.md) — the raw CRUD table view of the same data
