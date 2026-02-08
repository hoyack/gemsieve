# AI Audit Log

[Back to Manual](../manual.md)

The AI Audit Log is a read-only CRUD table showing every AI model call made by the pipeline. For a richer viewing experience with collapsible prompts and responses, use the [AI Inspector](ai-inspector.md) instead.

## List view columns

| Column | Description |
|--------|-------------|
| **id** | Audit entry identifier |
| **pipeline_run_id** | Which pipeline run triggered this call |
| **stage** | `classify` or `engage` |
| **sender_domain** | The sender being processed |
| **model_used** | AI model name (e.g., `mistral-large-3:675b-cloud`) |
| **duration_ms** | How long the AI call took in milliseconds |

Additional columns in detail view: prompt_template, prompt_rendered, system_prompt, response_raw, response_parsed, created_at.

## Searching

Search by **sender_domain**, **stage**, or **model_used**.

## Sorting

Sort by **stage**, **duration_ms**, or **created_at**. Default sort is by created_at (newest first).

## Read-only

This view is read-only. Entries are created automatically by the `LoggingAIProvider` wrapper when classify or engage stages run from the web admin.

## Detail view fields

Click any row to see the complete record:

| Field | Description |
|-------|-------------|
| **prompt_template** | Template name (CLASSIFICATION_PROMPT or ENGAGEMENT_PROMPT) |
| **prompt_rendered** | The complete prompt text with all variables filled in |
| **system_prompt** | The system/role instruction sent to the model |
| **response_raw** | The model's raw text output |
| **response_parsed** | The parsed JSON result extracted from the response |
| **duration_ms** | Call duration in milliseconds |

## How to use

### Find slow AI calls

1. Sort by **duration_ms** (descending)
2. Calls over 10,000ms may indicate model capacity issues or network latency
3. Compare across stages — engage calls are typically longer than classify

### Audit a specific sender

1. Search by **sender_domain**
2. See all AI calls ever made for this sender
3. Click into detail to read the full prompt and response

### Track AI usage

1. Check the total count to see how many AI calls have been made
2. Filter by **model_used** to see which model was active
3. Cross-reference with [Pipeline Runs](pipeline-runs.md) to see which pipeline run triggered each call

## How audit logging works

When classify or engage stages run from the web admin, the TaskManager wraps the AI provider with a `LoggingAIProvider`. This interceptor:

1. Captures the prompt, system prompt, and model name before the call
2. Forwards the call to the real AI provider
3. Records the response and measures duration
4. Inserts a row into `ai_audit_log`

This happens transparently — the stage code is unmodified. Logging only occurs for web-triggered runs, not CLI runs.

## Related views

- [AI Inspector](ai-inspector.md) — rich viewer with collapsible prompt/response sections
- [Classifications](classifications.md) — the classification output from these AI calls
- [Drafts](drafts.md) — the engagement drafts from these AI calls
- [Pipeline Runs](pipeline-runs.md) — the pipeline runs that triggered these calls
