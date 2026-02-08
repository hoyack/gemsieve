# Entities

[Back to Manual](../manual.md)

The Entities view shows the output of Stage 3 (entity extraction). GemSieve uses spaCy NLP and regex patterns to identify people, organizations, monetary values, dates, and other named entities from email text.

## List view columns

| Column | Description |
|--------|-------------|
| **id** | Auto-incremented identifier |
| **message_id** | The source message |
| **entity_type** | Category: PERSON, ORG, MONEY, DATE, ROLE, URL, PHONE, etc. |
| **entity_value** | The raw extracted text (e.g., "John Smith", "$5,000/mo") |
| **confidence** | Extraction confidence (0.0 to 1.0) |
| **source** | Detection method: `spacy` (NLP model) or `regex` (pattern matching) |

Additional columns in detail view: entity_normalized, context.

## Searching

Search by **entity_value** or **entity_type**.

## Sorting

Sort by **entity_type** or **confidence**. Default sort is by confidence (highest first).

## How to use

### Find named contacts

1. Filter by **entity_type** = `PERSON`
2. These are people mentioned by name in emails
3. Cross-reference with [Profiles](profiles.md) where they appear in `known_contacts`
4. Known contacts boost gem scores (contacts make outreach easier)

### Find monetary signals

1. Filter by **entity_type** = `MONEY`
2. See pricing, contract values, and budget mentions extracted from emails
3. These feed into the scoring formula as `monetary_signals`

### Check extraction quality

1. Sort by **confidence** (ascending) to find low-confidence extractions
2. Check the **source** column — `spacy` uses the NLP model, `regex` uses pattern matching
3. Look at the **context** field in detail view to see the surrounding text

## Requirements

Entity extraction requires spaCy:

```bash
python -m spacy download en_core_web_sm    # fast, good enough for most use
python -m spacy download en_core_web_trf   # transformer-based, higher accuracy
```

**Note:** Stage 3 may fail on Python 3.14 due to a known spaCy/pydantic v1 compatibility issue. This does not affect other stages — the pipeline can skip entity extraction and still produce classifications, profiles, and gems.

## Entity types

| Type | Examples | Source |
|------|----------|--------|
| PERSON | "John Smith", "Sarah" | spaCy NER |
| ORG | "Acme Corp", "Google" | spaCy NER |
| MONEY | "$5,000", "99/mo" | spaCy + regex |
| DATE | "January 2025", "next Tuesday" | spaCy NER |
| ROLE | "CEO", "VP of Marketing" | Regex patterns |
| PHONE | "+1-555-0100" | Regex patterns |
| URL | "https://example.com" | Regex patterns |

## Related views

- [Messages](messages.md) — source emails that entities were extracted from
- [Classifications](classifications.md) — entity summaries are included in the AI classification prompt
- [Profiles](profiles.md) — known_contacts and monetary_signals are derived from entities
- [AI Inspector](ai-inspector.md) — see how entity summaries appear in classification prompts
