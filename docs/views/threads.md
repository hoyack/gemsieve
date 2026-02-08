# Threads

[Back to Manual](../manual.md)

The Threads view shows conversation threads, aggregated from individual messages. Thread metadata is computed during ingestion and updated whenever new messages are added.

## List view columns

| Column | Description |
|--------|-------------|
| **thread_id** | Gmail's unique thread identifier |
| **subject** | Cleaned subject line (Re:/Fwd: prefixes stripped) |
| **message_count** | Number of messages in the thread |
| **last_sender** | Who sent the most recent message |
| **days_dormant** | Days since the last message in this thread |
| **awaiting_response_from** | `user` (they're waiting on you) or `other` (you're waiting on them) |
| **last_message_date** | When the most recent message was sent |

Additional columns in detail view: first_message_date, user_participated, participant_count.

## Searching

Search by **subject** or **last_sender**.

## Sorting

Sort by **days_dormant**, **message_count**, or **last_message_date**. Default sort is by last_message_date (newest first).

## How to use

### Find stalled conversations

1. Sort by **days_dormant** (descending) to find the oldest unanswered threads
2. Look at **awaiting_response_from** — threads showing `user` are waiting on your reply
3. Cross-reference with [Gems](gems.md) — dormant threads with commercial potential appear as `dormant_warm_thread` gems

### Identify active conversations

1. Sort by **last_message_date** (newest first)
2. Filter for threads where `user_participated` is true
3. Check message_count to see conversation depth

### Understand thread dynamics

1. Click into a thread detail view
2. Note the participant_count — how many people are involved
3. Check user_last_replied to see when you last responded
4. Go to [Messages](messages.md) and search by thread_id to see all individual messages

## Computed fields

These fields are calculated by `SyncEngine._update_threads()` after ingestion:

- **participant_count** — unique sender addresses across all messages in the thread
- **days_dormant** — `(now - last_message_date)` in days
- **awaiting_response_from** — `other` if the last message was sent by you, `user` if it was sent by someone else
- **user_participated** — true if any message in the thread has `is_sent = true`

## Related views

- [Messages](messages.md) — individual messages within threads
- [Gems](gems.md) — dormant_warm_thread and unanswered_ask gems reference threads
- [Gem Explorer](gem-explorer.md) — browse thread-related gems with scores
