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

Additional columns in detail view: entity_normalized, context, relationship (for PERSON entities).

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
| PERSON | "John Smith", "Sarah" | spaCy NER + CC headers |
| ORG | "Acme Corp", "Google" | spaCy NER |
| MONEY | "$5,000", "99/mo" | spaCy + regex |
| DATE | "January 2025", "next Tuesday" | spaCy NER |
| ROLE | "CEO", "VP of Marketing" | Regex patterns |
| PHONE | "+1-555-0100" | Regex patterns |
| URL | "https://example.com" | Regex patterns |
| procurement_signal | "security compliance", "RFP" | Regex patterns |

### Relationship classification

PERSON entities are now classified with a relationship type stored in the `context` field:

| Relationship | Meaning |
|-------------|---------|
| `decision_maker` | Person with a senior title (CEO, VP, Director, etc.) |
| `automated` | Address appears to be automated (noreply, support, etc.) |
| `vendor_contact` | Sender's own address or a role-based contact |
| `peer` | Named person without a senior title |

This classification helps gem detection prioritize threads with decision-maker involvement and filters out automated contacts.

### CC extraction

Person entities are extracted from CC addresses in addition to the email body, enabling detection of stakeholders who are copied on conversations but may not be the primary sender.

### Date normalization

Date entities are normalized with a `renewal:future` tag in `entity_normalized` when the date is in the future, helping identify upcoming renewal windows and deadlines.

### Config toggles

Entity extraction respects these `entity_extraction` config settings:

| Toggle | Default | Effect |
|--------|---------|--------|
| `extract_monetary` | true | Enable/disable monetary entity extraction |
| `extract_dates` | true | Enable/disable date entity extraction |
| `extract_procurement` | true | Enable/disable procurement signal extraction |

Set any toggle to `false` in `config.yaml` to skip that entity type during extraction.

## Related views

- [Messages](messages.md) — source emails that entities were extracted from
- [Classifications](classifications.md) — entity summaries are included in the AI classification prompt
- [Profiles](profiles.md) — known_contacts and monetary_signals are derived from entities
- [AI Inspector](ai-inspector.md) — see how entity summaries appear in classification prompts
