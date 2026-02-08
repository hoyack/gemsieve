# Overrides

[Back to Manual](../manual.md)

The Overrides view shows human corrections applied to AI classifications. When the AI gets a classification wrong, you can override specific fields. Overrides are applied automatically on subsequent classification runs.

## Columns

| Column | Description |
|--------|-------------|
| **id** | Override identifier |
| **sender_domain** | The domain this override applies to |
| **message_id** | Specific message (for message-scoped overrides) |
| **field_name** | Which classification field was corrected |
| **original_value** | What the AI originally assigned |
| **corrected_value** | The human-corrected value |
| **override_scope** | `sender` (applies to all messages from this domain) or `message` (single message only) |
| **created_at** | When the override was created |

## Searching

Search by **sender_domain** or **field_name**.

## Sorting

Sort by **created_at** or **field_name**. Default sort is by created_at (newest first).

## Creating overrides

Overrides are currently created via the CLI:

```bash
# Override at the sender level (all messages from this domain)
gemsieve override --sender acme.com --field industry --value "Developer Tools"

# Override a specific message
gemsieve override --message abc123 --field sender_intent --value "partnership_pitch"
```

## Overridable fields

| Field | Example values |
|-------|---------------|
| `industry` | SaaS, E-commerce, Agency, Healthcare, Education, etc. |
| `company_size_estimate` | small, medium, enterprise |
| `marketing_sophistication` | 1-10 |
| `sender_intent` | newsletter, cold_outreach, partnership_pitch, etc. |
| `product_type` | SaaS subscription, Professional service, Course, etc. |
| `product_description` | Free text description |
| `target_audience` | Free text description |

## How overrides work

1. When you create an override, it's stored in the `classification_overrides` table
2. The next time Stage 4 (classify) runs, it checks for overrides matching each sender domain
3. Override values replace the AI's output for those fields
4. The `has_override` flag is set to true on the classification record
5. Sender-scoped overrides apply to all messages from that domain; message-scoped overrides apply to one message only

## Related views

- [Classifications](classifications.md) — the AI output that overrides correct
- [AI Inspector](ai-inspector.md) — see the AI's original reasoning to understand why it was wrong
- [Profiles](profiles.md) — profiles reflect overridden classifications
