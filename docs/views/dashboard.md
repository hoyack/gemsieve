# Dashboard

[Back to Manual](../manual.md)

The Dashboard provides a high-level overview of your entire GemSieve pipeline at a glance.

## Stats cards

Six summary cards across the top show current totals:

| Card | What it shows |
|------|--------------|
| **Messages** | Total emails ingested from Gmail |
| **Profiles** | Sender profiles built (one per domain) |
| **Gems** | Commercial opportunities detected |
| **Classified** | Messages with AI classifications |
| **Drafts** | Engagement drafts generated |
| **Pipeline Runs** | Total pipeline executions |

## Pipeline health

A horizontal flow diagram shows each pipeline stage with its current row count. Stages are color-coded:

- **Green** (has data) — stage has been run and produced output
- **Gray** (empty) — stage has not been run yet or produced no output

This lets you quickly see which stages need to be run. For example, if Metadata shows 19,742 rows but Classify shows 0, you know classification hasn't been run yet.

## Charts

Four interactive Chart.js graphs appear below the stats:

| Chart | Type | What it shows |
|-------|------|--------------|
| **Gem Type Distribution** | Doughnut | Breakdown of gems by type (dormant threads, partner programs, etc.) |
| **Top Gems by Score** | Horizontal bar | The 10 highest-scoring gems with sender domains, estimated value, and urgency |
| **Industry Breakdown** | Pie | Distribution of classified senders by industry |
| **Messages by ESP** | Bar | How many messages were sent via each email service provider |

Charts are populated from the [REST API](../manual.md#rest-api) and update each time you visit the page.

## Recent pipeline activity

A table at the bottom shows the 10 most recent [Pipeline Runs](pipeline-runs.md) with:

- Run ID, stage name, status badge (completed/running/failed)
- Start and completion timestamps
- Number of items processed

Click through to [Pipeline Control](pipeline.md) to trigger new runs or see the full history.

## Related views

- [Pipeline Control](pipeline.md) — trigger and monitor pipeline stages
- [Gem Explorer](gem-explorer.md) — browse gems shown in the charts
- [Profiles](profiles.md) — sender profiles counted in stats
- [Classifications](classifications.md) — AI classifications counted in stats
