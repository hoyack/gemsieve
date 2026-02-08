# Temporal

[Back to Manual](../manual.md)

The Temporal view shows sender timing patterns, computed during Stage 1 (metadata extraction). Each row represents one sender domain and summarizes their emailing behavior over time.

## Columns

| Column | Description |
|--------|-------------|
| **sender_domain** | The sending domain |
| **first_seen** | Date of the earliest message from this domain |
| **last_seen** | Date of the most recent message from this domain |
| **total_messages** | Total number of messages received from this domain |
| **avg_frequency_days** | Average days between messages (lower = more frequent) |
| **most_common_send_hour** | Hour of day (0-23) when this sender most often sends |
| **most_common_send_day** | Day of week (0=Monday, 6=Sunday) when this sender most often sends |

## Searching

Search by **sender_domain**.

## Sorting

Sort by **total_messages**, **avg_frequency_days**, or **last_seen**.

## How to use

### Find your most frequent senders

1. Sort by **total_messages** (descending)
2. High-volume senders are likely newsletters or marketing platforms
3. Cross-reference with [Metadata](metadata.md) to see if they're flagged as bulk

### Identify sender patterns

1. Check **avg_frequency_days** — daily senders will show ~1.0, weekly ~7.0, monthly ~30.0
2. Look at **most_common_send_hour** to see when they typically send (useful for engagement timing)
3. Check **most_common_send_day** to identify weekly patterns

### Find dormant senders

1. Sort by **last_seen** (oldest first)
2. Senders who stopped emailing might indicate a lapsed relationship
3. Cross-reference with [Gems](gems.md) to see if dormant thread gems were detected

## Related views

- [Metadata](metadata.md) — per-message header analysis (also from Stage 1)
- [Profiles](profiles.md) — sender profiles include temporal data (avg_frequency_days, first_contact, last_contact)
