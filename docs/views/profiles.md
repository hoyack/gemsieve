# Profiles

[Back to Manual](../manual.md)

The Profiles view shows sender profiles built by Stage 5. Each row represents one sender domain and aggregates data from all previous stages into a comprehensive company profile.

## List view columns

| Column | Description |
|--------|-------------|
| **sender_domain** | The email domain (primary key) |
| **company_name** | Detected company name |
| **industry** | Industry from AI classification |
| **company_size** | small, medium, or enterprise |
| **marketing_sophistication_avg** | Average marketing sophistication across all messages (1-10) |
| **esp_used** | Which email service provider they use |
| **total_messages** | How many emails received from this domain |
| **has_partner_program** | Whether a partner/affiliate program was detected |
| **has_personalization** | Whether they use email personalization |
| **product_type** | What they sell |

Additional columns in detail view: product_description, primary_email, first_contact, last_contact, avg_frequency_days, authentication_quality, profiled_at.

## Searching

Search by **company_name**, **sender_domain**, or **industry**.

## Sorting

Sort by **company_name**, **industry**, **marketing_sophistication_avg**, or **total_messages**. Default sort is by total_messages (highest first).

## How to use

### Research a sender

1. Search for the sender domain or company name
2. Click the row to see the full detail view
3. The profile shows everything GemSieve knows: industry, size, ESP, products, contacts, frequency, authentication quality

### Find high-volume senders

1. Sort by **total_messages** (descending)
2. High-volume senders are your most active relationships
3. Check marketing_sophistication_avg — senders with low sophistication and high volume are potential leads

### Identify partnership targets

1. Filter for rows where **has_partner_program** is true
2. These companies have affiliate, reseller, or referral programs
3. Cross-reference with [Gems](gems.md) for scored partnership opportunities

### Find senders with weak marketing

1. Sort by **marketing_sophistication_avg** (ascending)
2. Low-sophistication senders in relevant industries are potential clients for marketing services
3. These appear as `weak_marketing_lead` gems in [Gem Explorer](gem-explorer.md)

## Profile fields (detail view)

| Field | Source | Description |
|-------|--------|-------------|
| company_name | AI classification | Detected company name |
| primary_email | Messages | Most common sender address |
| reply_to_email | Messages | Reply-to address if different |
| industry | AI classification | Industry category |
| company_size | AI classification | small/medium/enterprise |
| marketing_sophistication_avg | AI classification | Average across all messages |
| esp_used | Stage 1 metadata | Email service provider |
| product_type | AI classification | What they sell |
| product_description | AI classification | One-sentence description |
| known_contacts | Stage 3 entities | Named people with roles |
| total_messages | Aggregated | Message count from this domain |
| first_contact / last_contact | Messages | Date range of relationship |
| avg_frequency_days | Stage 1 temporal | How often they email |
| has_partner_program | AI classification | Partner program detected |
| has_personalization | Stage 2 content | Uses personalization tokens |
| monetary_signals | Stage 3 entities | Pricing and contract values |
| authentication_quality | Stage 1 metadata | SPF/DKIM/DMARC results |

## Related views

- [Classifications](classifications.md) — AI data that feeds into profiles
- [Metadata](metadata.md) — ESP and authentication data per message
- [Temporal](temporal.md) — sender timing patterns
- [Gems](gems.md) — commercial opportunities linked to profiles
- [Segments](segments.md) — economic segments assigned to profiles
- [Gem Explorer](gem-explorer.md) — rich card view with profile data
