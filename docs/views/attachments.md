# Attachments

[Back to Manual](../manual.md)

The Attachments view lists all file attachments found in ingested messages.

## Columns

| Column | Description |
|--------|-------------|
| **id** | Auto-incremented identifier |
| **message_id** | The message this attachment belongs to |
| **filename** | Original filename |
| **mime_type** | MIME type (e.g., `application/pdf`, `image/png`) |
| **size_bytes** | File size in bytes |

## Searching

Search by **filename** or **mime_type**.

## How to use

- Search for `.pdf` to find PDF attachments
- Search for `image/` to find all image attachments
- Click a row to see the full detail, then use the message_id to find the parent message in [Messages](messages.md)
- Attachment content is not downloaded — only metadata is stored

## Related views

- [Messages](messages.md) — the messages these attachments belong to
