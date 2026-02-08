# Classifications

[Back to Manual](../manual.md)

The Classifications view shows the output of Stage 4 (AI classification). Each row represents one message classified by the AI model, containing the sender's industry, intent, size, marketing sophistication, and more.

## List view columns

| Column | Description |
|--------|-------------|
| **message_id** | The classified message |
| **industry** | Detected industry (SaaS, E-commerce, Agency, Healthcare, etc.) |
| **company_size_estimate** | small, medium, or enterprise |
| **marketing_sophistication** | 1-10 rating of how polished their marketing is |
| **sender_intent** | Why they sent the email (newsletter, cold_outreach, nurture_sequence, etc.) |
| **product_type** | What they sell (SaaS subscription, Professional service, Course, etc.) |
| **ai_confidence** | How confident the AI is in its classification (0.0 to 1.0) |
| **model_used** | Which AI model produced this classification |
| **has_override** | Whether a human override has been applied |
| **partner_program_detected** | Whether the sender appears to have a partner/affiliate program |
| **renewal_signal_detected** | Whether renewal or subscription signals were found |

Additional columns in detail view: product_description, target_audience, classified_at.

## Searching

Search by **industry**, **sender_intent**, or **product_type**.

## Sorting

Sort by **industry**, **marketing_sophistication**, **ai_confidence**, or **company_size_estimate**. Default sort is by ai_confidence (highest first).

## How to use

### Review AI accuracy

1. Sort by **ai_confidence** (ascending) to find the least confident classifications
2. Check if the industry and intent make sense for the sender
3. If wrong, add an [Override](overrides.md) via the CLI: `gemsieve override --sender domain.com --field industry --value "Correct Industry"`

### Find specific industries

1. Search for an industry name (e.g., "SaaS")
2. See all messages classified under that industry
3. Cross-reference with [Profiles](profiles.md) to see aggregated per-sender profiles

### Identify partnership opportunities

1. Filter for rows where **partner_program_detected** is true
2. These senders have affiliate, reseller, or partner programs
3. They will also appear as `partner_program` gems in [Gem Explorer](gem-explorer.md)

### Check classification consistency

1. Search for a specific sender domain across all their messages
2. All messages from the same domain should have the same classification (they're classified per-domain, not per-message)
3. If `has_override` is true, a human correction was applied (sender-scoped or message-scoped)

### Improve classification accuracy over time

1. When you find wrong classifications, add overrides via the CLI or [Overrides](overrides.md) view
2. Run `gemsieve classify --retrain` or enable the **Retrain** toggle in [Pipeline Control](pipeline.md)
3. The `--retrain` flag appends the last 10 overrides as few-shot correction examples to the classification prompt
4. Over time, the AI learns from your corrections without needing model fine-tuning
5. Message-scoped overrides take priority over sender-scoped overrides

## Sender intent values

| Intent | Description |
|--------|-------------|
| `human_1to1` | Personal, individual email |
| `cold_outreach` | Unsolicited sales pitch |
| `nurture_sequence` | Part of an automated drip campaign |
| `newsletter` | Regular content newsletter |
| `transactional` | Order confirmation, receipt, notification |
| `promotional` | Sale, discount, or special offer |
| `event_invitation` | Webinar, conference, meetup invite |
| `partnership_pitch` | Collaboration or partnership proposal |
| `re_engagement` | Win-back or re-activation campaign |
| `procurement` | Purchasing, vendor evaluation |
| `recruiting` | Job-related outreach |
| `community` | Community updates, forum notifications |

## Related views

- [AI Inspector](ai-inspector.md) — see the exact prompt and response for any classification
- [Overrides](overrides.md) — correct wrong classifications
- [Profiles](profiles.md) — classifications are aggregated into sender profiles
- [Content](content.md) — content data that fed into the classification prompt
- [Dashboard](dashboard.md) — industry breakdown chart
