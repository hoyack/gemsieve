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
| **marketing_sophistication_avg** | Blended marketing sophistication score (1-10): 60% deterministic formula + 40% AI average |
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
| marketing_sophistication_avg | Deterministic + AI | 60% deterministic formula (ESP tier, personalization, UTM, auth, etc.) blended with 40% AI average |
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
| warm_signals | Stage 5 profiling | Warm signals detected in threads (pricing questions, meeting requests, follow-ups) |
| offer_type_distribution | Stage 2 content | Distribution of offer types across sender's messages |
| renewal_dates | Stage 3 entities | Future renewal/deadline dates detected |
| partner_program_urls | Stage 3 entities | URLs to partner program pages |
| economic_segments | Stage 5 profiling | Assigned economic segments |

### Deterministic sophistication scoring

The `marketing_sophistication_avg` field uses a 10-point deterministic formula blended with AI scores:

| Factor | Points | Source |
|--------|--------|--------|
| ESP tier | 1-3 | Enterprise ESP = 3, mid-tier = 2, basic = 1 |
| Personalization | 0-2 | Personalization tokens detected in emails |
| UTM tracking | 0-1 | UTM campaign parameters in links |
| Template quality | 0-1 | Template complexity score from content parsing |
| Segmentation signals | 0-1 | Evidence of list segmentation |
| Email authentication | 0-1 | SPF + DKIM + DMARC all passing |
| Unsubscribe presence | 0-1 | Proper unsubscribe link/header |

The deterministic score is weighted 60% and the AI-provided sophistication score is weighted 40%, producing a more stable and reproducible rating.

## Related views

- [Classifications](classifications.md) — AI data that feeds into profiles
- [Metadata](metadata.md) — ESP and authentication data per message
- [Temporal](temporal.md) — sender timing patterns
- [Gems](gems.md) — commercial opportunities linked to profiles
- [Segments](segments.md) — economic segments assigned to profiles
- [Gem Explorer](gem-explorer.md) — rich card view with profile data
