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
| **spend_map** | Companies you pay money to | `active_subscription`, `upcoming_renewal`, `churned_vendor` |
| **partner_map** | Companies with programs you can join | `referral_program`, `general` |
| **prospect_map** | Companies you could sell to | `hot_lead` (soph <= 3), `warm_prospect` (soph 4-5), `intelligence_value` (soph 6+) |
| **dormant_threads** | Stalled conversations with potential | `unanswered` |
| **distribution_map** | Channels that could amplify you | `newsletter`, `event_organizer`, `community` |
| **procurement_map** | Active buying signals | `security_compliance`, `formal_rfp`, `evaluation` |

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
- **Entity data** — monetary signals, named contacts, procurement signals

Each sender can appear in multiple segments. Confidence reflects how strongly the signals match the segment criteria.

### Sub-segment classification details

**Spend Map** sub-segments use intelligent classification:
- `churned_vendor` — last contact was more than 180 days ago (detected from `last_contact` on the profile)
- `upcoming_renewal` — future renewal dates exist in the sender's entity data
- `active_subscription` — recent contact with no upcoming renewals

**Distribution Map** sub-segments are classified from the sender's `offer_type_distribution` profile field:
- `newsletter` — sender has newsletter or digest offer types
- `event_organizer` — sender has event_invitation, webinar, or event offer types
- `community` — sender has community or forum offer types

**Procurement Map** sub-segments query the `extracted_entities` table for procurement signals:
- `security_compliance` — mentions of security, compliance, SOC, GDPR, HIPAA
- `formal_rfp` — mentions of RFP, RFQ, bid, request for proposal
- `evaluation` — mentions of evaluation, trial, POC, proof of concept, pilot

## Related views

- [Profiles](profiles.md) — sender profiles that segments are derived from
- [Gems](gems.md) — gems that inform segment assignment
- [Gem Explorer](gem-explorer.md) — browse gems filtered by segment context
