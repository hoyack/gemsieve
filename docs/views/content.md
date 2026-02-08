# Content

[Back to Manual](../manual.md)

The Content view shows the output of Stage 2 (content parsing). For each message, GemSieve parses the HTML body to extract marketing signals, links, offers, and content structure metrics.

## List view columns

| Column | Description |
|--------|-------------|
| **message_id** | Links to the source message |
| **primary_headline** | The main headline detected in the email |
| **link_count** | Total number of links in the email |
| **tracking_pixel_count** | Number of 1x1 tracking pixels detected |
| **offer_types** | Types of offers detected (discount, free_trial, webinar, etc.) |
| **cta_texts** | Call-to-action button/link texts (e.g., "Buy Now", "Sign Up Free") |
| **has_personalization** | Whether the email uses personalization tokens |
| **template_complexity_score** | How complex the HTML template is (higher = more sophisticated) |

Additional columns in detail view: image_count, has_physical_address.

## Searching

Search by **primary_headline**.

## Sorting

Sort by **link_count**, **tracking_pixel_count**, or **template_complexity_score**.

## How to use

### Assess marketing sophistication

1. Sort by **template_complexity_score** (descending) to find the most polished marketing emails
2. High tracking_pixel_count indicates advanced email analytics
3. Personalization tokens suggest automated marketing platforms
4. This data feeds into the `marketing_sophistication` score in [Classifications](classifications.md)

### Find promotional content

1. Check the **offer_types** column for detected offers (discount, free_trial, demo, webinar, etc.)
2. Look at **cta_texts** to see what actions senders are asking recipients to take
3. High link_count often indicates newsletters or promotional blasts

### Identify simple vs. complex senders

1. **template_complexity_score** near 0 = plain text or simple HTML
2. Scores of 5+ indicate designed templates with images, columns, and styling
3. Cross-reference with [Metadata](metadata.md) ESP data — senders using enterprise ESPs typically have higher complexity

## What gets extracted

Stage 2 processes the HTML body of each email:

- **body_clean** — HTML stripped to readable text
- **signature_block** — email signature separated from body
- **cta_texts** — text from buttons and prominent links
- **offer_types** — categorized offers (discount, free_trial, webinar, case_study, etc.)
- **link analysis** — total count, unique domains, UTM campaigns, link intents
- **tracking pixels** — 1x1 invisible images used for open tracking
- **physical_address** — postal address detection (CAN-SPAM compliance indicator)
- **social_links** — links to social media profiles

## Related views

- [Messages](messages.md) — source emails with raw HTML body
- [Metadata](metadata.md) — header-level analysis for the same messages
- [Classifications](classifications.md) — AI classification uses content data as input
- [Profiles](profiles.md) — aggregated content signals per sender domain
