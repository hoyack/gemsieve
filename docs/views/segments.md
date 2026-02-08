# Segments

[Back to Manual](../manual.md)

The Segments view shows the economic segmentation output from Stage 6. Each sender can belong to multiple segments simultaneously, representing different types of commercial relationships.

## Columns

| Column | Description |
|--------|-------------|
| **sender_domain** | The sender's domain |
| **segment** | Primary segment category |
| **sub_segment** | More specific classification within the segment |
| **confidence** | Segmentation confidence (0.0 to 1.0) |

Additional column in detail view: assigned_at.

## Searching

Search by **sender_domain**, **segment**, or **sub_segment**.

## Sorting

Sort by **segment** or **confidence**.

## Segment types

| Segment | What it tracks | Sub-segments |
|---------|---------------|--------------|
| **spend_map** | Companies you pay money to | subscriptions, renewals, invoices |
| **partner_map** | Companies with programs you can join | affiliate, reseller, referral |
| **prospect_map** | Companies you could sell to | marketing_gap, relevant_industry, low_sophistication |
| **dormant_threads** | Stalled conversations with potential | user_owes_reply, awaiting_response |
| **distribution_map** | Channels that could amplify you | newsletter, podcast, event, community |
| **procurement_map** | Active buying signals | vendor_evaluation, rfp, budget_allocation |

## How to use

### See a sender's economic role

1. Search for a sender domain
2. View all segments they belong to
3. A sender in both `spend_map` and `partner_map` is a vendor you pay who also has a partnership program

### Find prospect targets

1. Search for segment = `prospect_map`
2. These are senders with marketing weaknesses in industries relevant to you
3. Sub-segments tell you why: `marketing_gap` (low sophistication), `relevant_industry` (matches your target industries)

### Identify vendor relationships

1. Search for segment = `spend_map`
2. These are companies you're paying (detected via renewal signals, subscription emails)
3. Sub-segment `renewals` indicates upcoming negotiation windows

## How segmentation works

Stage 6 assigns segments based on rules applied to sender profiles:

- **Profile data** — industry, company_size, marketing_sophistication, has_partner_program
- **Gem data** — which gem types exist for this sender
- **Thread data** — conversation status (dormant, active, awaiting response)
- **Entity data** — monetary signals, named contacts

Each sender can appear in multiple segments. Confidence reflects how strongly the signals match the segment criteria.

## Related views

- [Profiles](profiles.md) — sender profiles that segments are derived from
- [Gems](gems.md) — gems that inform segment assignment
- [Gem Explorer](gem-explorer.md) — browse gems filtered by segment context
