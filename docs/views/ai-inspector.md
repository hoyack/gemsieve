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

A collapsible section shows the two prompt templates used by GemSieve:

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

### ENGAGEMENT_PROMPT (Stage 7)

Variables filled in per gem:
- `{strategy_name}` — engagement strategy (audit, revival, partner, etc.)
- `{gem_type}` — type of commercial opportunity
- `{gem_explanation_json}` — structured explanation of why this gem was detected
- Recipient profile fields: company_name, contact_name, industry, company_size, esp_used, etc.
- User profile fields: your_name, your_service, your_tone

The AI responds with a personalized outreach message.

## Audit log entries

Each entry is displayed as a card showing:

**Header:**
- Stage badge (classify/engage)
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
