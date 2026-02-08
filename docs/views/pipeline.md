# Pipeline Control

[Back to Manual](../manual.md)

The Pipeline Control view lets you trigger any pipeline stage from the browser, monitor progress in real time via Server-Sent Events (SSE), and review the full run history.

## Stage flow

A horizontal flow diagram at the top shows all 7 stages in order, with arrows indicating the data flow. Each stage badge shows its current output row count and is color-coded green (has data) or gray (empty).

The stages in order:

1. **metadata** — Header forensics and ESP fingerprinting
2. **content** — HTML parsing, offer detection, CTA extraction
3. **entities** — Named entity recognition (people, orgs, money, dates)
4. **classify** — AI-powered sender classification
5. **profile** — Sender profile building and gem detection
6. **segment** — Economic segmentation and opportunity scoring
7. **engage** — AI-generated engagement drafts

## Running stages

### Individual stages

Each stage has a card with:

- **Stage description** — what the stage does
- **Output rows** — how many rows exist in the output table
- **Last run** — status badge (completed/running/failed) and item count from the most recent run
- **Run button** — click to trigger the stage

When you click a Run button:
1. The button changes to a spinner
2. The stage is submitted to the background task queue
3. The Live Output panel appears with SSE updates
4. When complete, the button resets and the status updates

### Run All

The **Run All (Stages 1-6)** button in the top-right triggers stages 1 through 6 sequentially. Stage 7 (engage) is excluded because it requires selecting which gems to generate drafts for. Use the [Gem Explorer](gem-explorer.md) to trigger engagement for specific gems.

## Live output

When any stage is running, a dark terminal-style panel appears showing real-time SSE events:

- `[STARTED]` — stage has begun executing
- `[DONE]` — stage completed with item count
- `[FAILED]` — stage failed with error message

The output auto-scrolls. Click **Clear** to reset it.

## Run history

A table at the bottom shows all pipeline runs with:

| Column | Description |
|--------|-------------|
| **ID** | Run identifier |
| **Stage** | Which stage was executed |
| **Status** | pending, running, completed, or failed |
| **Started** | When execution began |
| **Completed** | When execution finished |
| **Items** | Number of items processed |
| **Source** | `web` (triggered from UI) or `cli` (triggered from command line) |
| **Error** | Error message if the run failed |

## Tips

- Stages are idempotent — running a stage twice only processes new/unprocessed items
- If classify or engage fail, check the error message — it's usually an AI provider connectivity issue
- Entity extraction (Stage 3) requires spaCy and may fail on Python 3.14 due to a known compatibility issue
- You can run stages out of order, but downstream stages need upstream data to produce meaningful results
- Multiple stages can run concurrently (the task manager uses a thread pool with 2 workers)

## Related views

- [Dashboard](dashboard.md) — pipeline health overview and charts
- [Pipeline Runs](pipeline-runs.md) — full CRUD view of the pipeline_runs table
- [AI Audit Log](ai-audit-log.md) — see exactly what AI stages sent and received
