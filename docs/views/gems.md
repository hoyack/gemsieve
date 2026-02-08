# Gems

[Back to Manual](../manual.md)

The Gems view is the CRUD table view for all detected commercial opportunities. For a richer card-based experience with filtering, use the [Gem Explorer](gem-explorer.md) instead.

## List view columns

| Column | Description |
|--------|-------------|
| **id** | Gem identifier |
| **gem_type** | Type of opportunity (see table below) |
| **sender_domain** | The sender this gem relates to |
| **score** | Opportunity score (0-100) |
| **status** | `new`, `acted`, or `dismissed` |
| **created_at** | When the gem was detected |

Additional columns in detail view: thread_id, explanation (JSON), recommended_actions (JSON), acted_at.

## Searching

Search by **gem_type** or **sender_domain**.

## Sorting

Sort by **score**, **gem_type**, **status**, or **created_at**. Default sort is by score (highest first).

## Gem types

| Type | What it detects |
|------|----------------|
| `dormant_warm_thread` | Stalled conversations where you owe a reply |
| `unanswered_ask` | Recent messages awaiting your response |
| `weak_marketing_lead` | Senders with marketing gaps you can fill |
| `partner_program` | Vendors with affiliate/reseller programs |
| `renewal_leverage` | Upcoming SaaS renewals (negotiation windows) |
| `vendor_upsell` | Vendors pitching upgrades (they value your business) |
| `distribution_channel` | Newsletters/podcasts/events that could amplify you |
| `co_marketing` | Senders whose audience overlaps with yours |
| `industry_intel` | Senders providing useful market intelligence |
| `procurement_signal` | Active buying or vendor evaluation signals |

## Detail view

Click any gem row to see the full record, including:

- **explanation** — JSON object with structured signals and evidence for why this gem was detected. Each signal has a name and supporting evidence text.
- **recommended_actions** — JSON array of suggested next steps (e.g., "Reply to the original thread mentioning your relevant experience")
- **source_message_ids** — which messages triggered this gem's detection
- **thread_id** — for thread-related gems, links to the conversation

## How to use

### Find the best opportunities

1. Sort by **score** (descending)
2. Focus on gems scoring 50+ first
3. Check the gem_type to understand the opportunity category
4. Click into detail to read the explanation and recommended actions

### Track your engagement

1. Filter by **status** = `new` to see unacted opportunities
2. After engaging with a sender, update the status to `acted`
3. Filter by **status** = `acted` to review your outreach history

### Generate outreach

Use the [Gem Explorer](gem-explorer.md) for one-click draft generation, or trigger engagement via CLI:

```bash
gemsieve generate --gem 42
```

## Related views

- [Gem Explorer](gem-explorer.md) — rich card-based gem browser with Generate Draft buttons
- [Profiles](profiles.md) — sender profiles linked to gems
- [Segments](segments.md) — economic segments assigned to gem senders
- [Drafts](drafts.md) — engagement drafts generated from gems
- [Dashboard](dashboard.md) — gem type distribution chart
