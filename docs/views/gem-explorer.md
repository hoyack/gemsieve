# Gem Explorer

[Back to Manual](../manual.md)

The Gem Explorer displays all detected commercial opportunities as a filterable card grid. Each gem card shows the opportunity type, sender, score, signals, and recommended actions.

## Filters

Filter gems using controls at the top:

| Filter | Options |
|--------|---------|
| **Type** | All types, or select one: dormant_warm_thread, unanswered_ask, weak_marketing_lead, partner_program, renewal_leverage, vendor_upsell, distribution_channel, co_marketing, industry_intel, procurement_signal |
| **Status** | All, `new` (not acted on), `acted` (engaged), `dismissed` |
| **Min Score** | Only show gems scoring at or above this threshold (0-100) |
| **Sort** | Score high to low (default), Score low to high, Newest first |

Click **Filter** to apply, **Reset** to clear all filters. The total gem count is shown in the header badge.

## Gem cards

Each gem is displayed as a card containing:

### Header
- **Gem type badge** — the opportunity category (e.g., `dormant_warm_thread`)
- **Status badge** — `new` (blue), `acted` (green), or `dismissed` (gray)
- **ID** — the gem's database identifier

### Body

| Element | Description |
|---------|-------------|
| **Company name** | From the sender profile (falls back to domain if no company name) |
| **Sender domain** | The email domain this gem relates to |
| **Industry** | The AI-classified industry (if available) |
| **Score bar** | Visual 0-100 progress bar. Green (70+), yellow (40-69), gray (below 40) |
| **Summary** | Brief explanation of why this gem was detected |
| **Signal chips** | Pill badges showing the specific signals that triggered this gem (e.g., "user_participated", "days_dormant > 30"). Hover for evidence text. Up to 5 shown. |
| **Actions** | Recommended next steps (e.g., "Reply to the original thread", "Mention your relevant experience"). Up to 3 shown. |

### Footer

- **Generate Draft** button — triggers the engagement stage (Stage 7) for this specific gem. Shows a toast notification with the submitted run ID.
- **Detail** button — links to the full CRUD detail view in the [Gems](gems.md) table, showing all fields including the complete explanation JSON.

## How to use

### Find high-value opportunities

1. Set **Min Score** to 50 or higher
2. Sort by **Score (high to low)**
3. Browse the cards — high-scoring gems have the most commercial signals

### Focus on a specific opportunity type

1. Select a **Type** filter (e.g., `partner_program`)
2. Review the signal chips — they show exactly why each sender was flagged
3. Read the recommended actions for engagement ideas

### Generate outreach

1. Find a promising gem
2. Click **Generate Draft** — this triggers the AI to create a personalized outreach message
3. The toast notification shows the pipeline run ID
4. Go to [Drafts](drafts.md) to see the generated message
5. Review and customize before sending

### Investigate a gem

1. Click **Detail** to see the full gem record, including:
   - Complete explanation JSON with all signals and evidence
   - Source message IDs that triggered detection
   - Thread ID (for dormant thread gems)
   - Complete recommended actions list
2. Cross-reference with [Profiles](profiles.md) by searching for the sender domain
3. Check [AI Inspector](ai-inspector.md) to see the AI classification that informed the gem

## Understanding gem scores

Scores range from 0-100, composed of:

**Base profile score (max 60):**
- Reachability (smaller companies = easier to reach)
- Budget signals (ESP tier indicates marketing spend)
- Industry relevance (matches your target industries from config)
- Recency (last contact within 30/90 days)
- Known contacts (named people found via entity extraction)
- Monetary signals (pricing, contract values detected)

**Gem diversity bonus (max 40):**
- Each unique gem type for a sender adds points
- Dormant warm thread bonus (+8)
- Partner program bonus (+5)
- Renewal leverage bonus (+3)

All weights are configurable in `config.yaml` under `scoring.weights`.

## Related views

- [Gems](gems.md) — raw CRUD table view of all gems
- [Profiles](profiles.md) — sender profiles referenced by gems
- [Drafts](drafts.md) — engagement drafts generated from gems
- [Segments](segments.md) — economic segments assigned to senders
- [Dashboard](dashboard.md) — gem type distribution charts
