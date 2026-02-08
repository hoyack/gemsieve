# Messages

[Back to Manual](../manual.md)

The Messages view shows all raw emails ingested from Gmail. This is the foundation table — every other stage processes data from here.

## List view columns

| Column | Description |
|--------|-------------|
| **message_id** | Gmail's unique message identifier |
| **thread_id** | Gmail thread this message belongs to |
| **from_name** | Sender's display name |
| **from_address** | Sender's email address |
| **subject** | Email subject line |
| **date** | When the email was sent |
| **is_sent** | Whether you sent this message (outbound) |

Additional columns visible in the detail view: snippet, labels, size_estimate, ingested_at.

## Searching

Search by **from_address**, **subject**, or **from_name**. Type in the search box and press Enter.

Examples:
- Search `acme.com` to find all emails from that domain
- Search `invoice` to find invoices by subject
- Search `John` to find emails from senders named John

## Sorting

Click column headers to sort by **date**, **from_address**, or **subject**. Default sort is by date (newest first).

## How to use

### Find all emails from a sender

1. Search for the sender's domain or email address
2. Results show all messages from that address
3. Click any row to see the full detail view with snippet, labels, and raw headers

### Check what was ingested

1. Sort by date (newest first) to see the most recent messages
2. Check the total count in the header to verify ingestion completeness
3. Look at the `is_sent` column to distinguish inbound vs. outbound messages

### Follow a conversation

1. Find a message of interest
2. Note its `thread_id`
3. Go to [Threads](threads.md) and search for that thread ID
4. Or search Messages for the same thread_id to see all messages in the conversation

## Data source

Messages are populated by Stage 0 (ingestion) via `gemsieve ingest`. Fields come from Gmail's API message format, parsed by `GmailClient.parse_message()`.

## Related views

- [Threads](threads.md) — conversation-level view grouping messages
- [Attachments](attachments.md) — files attached to messages
- [Metadata](metadata.md) — header forensics for each message
- [Content](content.md) — parsed HTML content for each message
- [Classifications](classifications.md) — AI classification per message
