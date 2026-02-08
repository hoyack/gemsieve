# Pipeline Runs

[Back to Manual](../manual.md)

The Pipeline Runs view is a read-only CRUD table showing every pipeline stage execution. This is the raw data behind the [Pipeline Control](pipeline.md) run history and the [Dashboard](dashboard.md) recent activity feed.

## Columns

| Column | Description |
|--------|-------------|
| **id** | Run identifier |
| **stage** | Which stage was executed (metadata, content, entities, classify, profile, segment, engage) |
| **status** | `pending` (queued), `running` (in progress), `completed` (success), `failed` (error) |
| **started_at** | When execution began |
| **completed_at** | When execution finished |
| **items_processed** | Number of items the stage processed |
| **triggered_by** | `web` (from admin UI) or `cli` (from command line) |

Additional columns in detail view: error_message, created_at.

## Searching

Search by **stage** or **status**.

## Sorting

Sort by **stage**, **status**, **started_at**, or **items_processed**. Default sort is by started_at (newest first).

## Read-only

This view is read-only — you cannot create or edit pipeline runs manually. Runs are created automatically when stages are triggered from [Pipeline Control](pipeline.md) or the CLI.

## How to use

### Check run duration

1. Compare started_at and completed_at to see how long each stage took
2. Content parsing typically takes the longest (parsing HTML for thousands of messages)
3. AI stages (classify, engage) depend on model speed — larger models take longer

### Investigate failures

1. Filter by **status** = `failed`
2. Click into the detail view to see the **error_message**
3. Common errors:
   - Entity extraction: "unable to infer type for attribute REGEX" — Python 3.14/spaCy incompatibility
   - Classify/engage: connection errors to the AI provider
   - Database locked: concurrent writes (resolved with busy_timeout)

### Track pipeline runs over time

1. Sort by **started_at** to see chronological order
2. Check **items_processed** to see if reprocessing picked up new items
3. Use [Dashboard](dashboard.md) for a visual overview

## Related views

- [Pipeline Control](pipeline.md) — interactive pipeline triggering and monitoring
- [Dashboard](dashboard.md) — recent activity feed
- [AI Audit Log](ai-audit-log.md) — AI calls linked to specific pipeline runs
