# Metadata

[Back to Manual](../manual.md)

The Metadata view shows the output of Stage 1 (header forensics). For each message, GemSieve analyzes email headers to identify the sending infrastructure, authentication results, and bulk/transactional markers.

## List view columns

| Column | Description |
|--------|-------------|
| **message_id** | Links to the source message |
| **sender_domain** | Domain extracted from the sender address |
| **esp_identified** | Detected email service provider (SendGrid, Mailchimp, HubSpot, etc.) |
| **esp_confidence** | Confidence level of the ESP detection |
| **spf_result** | SPF authentication result (pass/fail/none) |
| **dmarc_result** | DMARC authentication result |
| **sending_ip** | IP address that sent the email |
| **is_bulk** | Whether the email appears to be bulk/marketing (vs. transactional or personal) |

Additional columns in detail view: dkim_domain, envelope_sender, list_unsubscribe_url, parsed_at.

## Searching

Search by **sender_domain** or **esp_identified**.

## Sorting

Sort by **sender_domain**, **esp_identified**, or **esp_confidence**.

## How to use

### Identify a sender's ESP

1. Search for the sender domain
2. The `esp_identified` column shows which email platform they use
3. Cross-reference with [Dashboard](dashboard.md) ESP chart for overall distribution

### Check email authentication

1. Look at `spf_result` and `dmarc_result` columns
2. `pass` means the sender's domain authentication is properly configured
3. `fail` or `none` indicates potential spoofing risk or poor configuration
4. This data feeds into the `authentication_quality` field on [Profiles](profiles.md)

### Find bulk senders

1. Filter or sort to find rows where `is_bulk` is true
2. Bulk detection is based on headers like `Precedence: bulk`, `List-Unsubscribe`, and ESP-specific markers

## ESP detection

GemSieve identifies 12 email service providers by analyzing message headers:

SendGrid, Mailchimp, HubSpot, Klaviyo, Constant Contact, Amazon SES, ConvertKit, ActiveCampaign, Salesforce Marketing Cloud, Postmark, Mailgun, and custom SMTP.

Detection rules are defined in `esp_rules.yaml` and match against header patterns (e.g., `X-SG-EID` for SendGrid, `X-MC-User` for Mailchimp).

## Related views

- [Messages](messages.md) — the source emails these metadata records parse
- [Temporal](temporal.md) — sender timing patterns (also from Stage 1)
- [Profiles](profiles.md) — aggregated sender profiles that include ESP and authentication data
- [Dashboard](dashboard.md) — ESP distribution chart
