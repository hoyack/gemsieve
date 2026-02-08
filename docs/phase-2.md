# GemSieve Phase 2 — Intelligence Depth & Engagement Precision

## Specification Document

### Origin

This spec was derived from a systematic gap analysis of `spec-1.md` (v0.2) against the implemented codebase. Phase 1 delivered the complete 8-stage pipeline, web admin portal, CrewAI integration, and Ollama Cloud support. Phase 2 closes the remaining gaps between specification and implementation, focusing on three themes:

1. **Smarter gem detection** — content-aware thread analysis, entity cross-referencing, audience overlap detection
2. **Strategy-specific engagement** — replace the generic prompt with per-strategy templates and context assembly
3. **Extraction depth** — richer entity typing, deterministic scoring, footer stripping, metadata fields

### Changelog from Phase 1

- **Closing:** Content-aware `awaiting_response_from` with question/CTA detection in threads
- **Closing:** CO_MARKETING gem detection (was stub returning empty)
- **Closing:** Strategy-specific engagement prompts (8 strategies, each with distinct templates)
- **Closing:** Warm signal detection in dormant threads (pricing, meetings, follow-ups)
- **Closing:** Entity relationship typing (people and org classification)
- **Closing:** Deterministic marketing sophistication scoring
- **Closing:** `classify --retrain` with few-shot examples from overrides
- **Closing:** Missing metadata fields (mail_server, x_mailer, precedence, feedback_id)
- **Closing:** Footer/legal block stripping in content parser
- **Closing:** Gem explanation `estimated_value` and `urgency` fields
- **Adding:** OpenAI provider
- **Adding:** PostgreSQL support for CLI layer

---

## 1. Thread Intelligence — Content-Aware Response Detection

### 1.1 Problem

Currently `awaiting_response_from` is set purely by who sent the last message. If someone sends you a "FYI — our office is closed Friday" email, the system marks it as awaiting your response. The spec requires content analysis to distinguish actual asks from informational messages.

### 1.2 Implementation

Add `_classify_awaiting_response()` to `gmail/sync.py`, called from `_update_threads()`:

```python
QUESTION_SIGNALS = [
    r'\?\s*$',                          # ends with question mark
    r'(?i)\bthoughts\b',               # "thoughts?"
    r'(?i)\binterested\b',             # "interested?"
    r'(?i)\blet me know\b',            # "let me know"
    r'(?i)\bcircle back\b',            # "circle back"
    r'(?i)\bfollow up\b',             # "follow up"
    r'(?i)\bwhat do you think\b',     # "what do you think"
    r'(?i)\bcan you\b',               # "can you..."
    r'(?i)\bcould you\b',             # "could you..."
    r'(?i)\bwould you\b',             # "would you..."
    r'(?i)\bdo you have\b',           # "do you have..."
    r'(?i)\bare you\b.*\?',           # "are you available?"
    r'(?i)\bwhen can\b',              # scheduling
    r'(?i)\bschedule\b.*\bcall\b',    # meeting requests
    r'(?i)\bbook\b.*\btime\b',        # meeting requests
]

CONCLUDED_SIGNALS = [
    r'(?i)^thanks[.!]?\s*$',          # "Thanks."
    r'(?i)\bsounds good\b',           # agreement
    r'(?i)\bgreat[,.]?\s*thanks\b',   # "Great, thanks"
    r'(?i)\bwill do\b',               # acknowledgment
    r'(?i)\bno worries\b',            # closing
    r'(?i)\btalk soon\b',             # closing
    r'(?i)\bsee you\b',              # closing
]

def _classify_awaiting_response(last_message_body: str, is_from_user: bool) -> str:
    """Determine awaiting_response_from based on content analysis.

    Returns: 'user' | 'other' | 'none'
    """
    if not last_message_body:
        return 'other' if is_from_user else 'user'

    # Check for concluded signals first
    last_lines = last_message_body.strip().split('\n')[-3:]
    tail = ' '.join(last_lines)
    for pattern in CONCLUDED_SIGNALS:
        if re.search(pattern, tail):
            return 'none'

    if is_from_user:
        # User sent the last message — check if it contains a question
        for pattern in QUESTION_SIGNALS:
            if re.search(pattern, last_message_body):
                return 'other'  # user asked something, other owes reply
        return 'none'  # user's last message was a statement
    else:
        # Someone else sent the last message
        for pattern in QUESTION_SIGNALS:
            if re.search(pattern, last_message_body):
                return 'user'  # they asked you something
        return 'none'  # informational message, no reply expected
```

### 1.3 Changes

| File | Change |
|------|--------|
| `gmail/sync.py` | Add `_classify_awaiting_response()`, update `_update_threads()` to fetch last message body and pass it to classifier |
| `gmail/sync.py` | `_update_threads()` query: JOIN `messages` to get `body_text` for the last message per thread |

### 1.4 Impact

This directly improves the quality of `DORMANT_WARM_THREAD` and `UNANSWERED_ASK` gem detection by eliminating false positives from informational emails, FYI forwards, and concluded conversations.

---

## 2. Warm Signal Detection in Dormant Threads

### 2.1 Problem

`_detect_dormant_warm_thread()` triggers for any thread where `awaiting_response_from = 'user'` and dormancy >= 14 days. The spec requires checking thread content for warm signals — pricing language, meeting requests, explicit questions — to separate actionable dormant threads from low-value ones.

### 2.2 Implementation

Add warm signal scanning to `stages/profile.py`:

```python
WARM_SIGNALS = {
    'pricing': [r'(?i)\bpric', r'(?i)\bcost', r'(?i)\bquote', r'(?i)\bbudget',
                r'(?i)\brate[s]?\b', r'(?i)\bfee[s]?\b'],
    'meeting_request': [r'(?i)\bcall\b', r'(?i)\bmeeting\b', r'(?i)\bdemo\b',
                        r'(?i)\bschedule\b', r'(?i)\bcalendly\b', r'(?i)\bbook\b.*\btime\b'],
    'explicit_ask': [r'\?\s*$', r'(?i)\bthoughts\b', r'(?i)\binterested\b',
                     r'(?i)\blet me know\b', r'(?i)\bwhat do you think\b'],
    'follow_up': [r'(?i)\bcircle back\b', r'(?i)\bfollow up\b', r'(?i)\btouching base\b',
                  r'(?i)\bchecking in\b', r'(?i)\bjust wanted to\b'],
    'decision_maker': [r'(?i)\b(?:VP|Director|CEO|CTO|CFO|Head of|Founder)\b'],
    'budget_indicator': [r'(?i)\bteam of \d+', r'(?i)\bevaluating\b',
                         r'(?i)\bshortlist\b', r'(?i)\bPOC\b', r'(?i)\bproof of concept\b'],
}

def _scan_warm_signals(db: sqlite3.Connection, thread_id: str) -> tuple[list[dict], int]:
    """Scan thread messages for warm signals. Returns (signals, score_boost)."""
    messages = db.execute(
        """SELECT m.body_text, pc.body_clean, pc.signature_block
           FROM messages m
           LEFT JOIN parsed_content pc ON m.message_id = pc.message_id
           WHERE m.thread_id = ?""",
        (thread_id,),
    ).fetchall()

    text = ' '.join(
        (m['body_clean'] or m['body_text'] or '') + ' ' + (m['signature_block'] or '')
        for m in messages
    )

    found_signals = []
    score_boost = 0

    for signal_type, patterns in WARM_SIGNALS.items():
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                found_signals.append({
                    'signal': signal_type,
                    'evidence': match.group(0).strip()[:100],
                })
                score_boost += {'pricing': 15, 'meeting_request': 12, 'explicit_ask': 10,
                                'follow_up': 5, 'decision_maker': 8, 'budget_indicator': 12
                                }[signal_type]
                break  # one match per signal type

    return found_signals, min(score_boost, 30)
```

### 2.3 Changes

| File | Change |
|------|--------|
| `stages/profile.py` | Add `WARM_SIGNALS` dict and `_scan_warm_signals()` function |
| `stages/profile.py` | `_detect_dormant_warm_thread()`: call `_scan_warm_signals()`, add signals to explanation, add score_boost. Skip threads with zero warm signals if `require_human_sender` is True. |
| `stages/profile.py` | `_detect_dormant_warm_thread()`: check `require_human_sender` config against thread's sender_intent (skip `transactional`, `re_engagement`, `community` intents) |

### 2.4 Entity Cross-Referencing for Score Boosting

The spec says dormant thread scores should be boosted by entity extraction finding money/dates and decision-maker titles. Add to `_detect_dormant_warm_thread()`:

```python
# Cross-reference entities for this thread's messages
entities = db.execute(
    """SELECT ee.entity_type, ee.entity_value
       FROM extracted_entities ee
       WHERE ee.message_id IN (SELECT message_id FROM messages WHERE thread_id = ?)""",
    (thread_id,),
).fetchall()

for ent in entities:
    if ent['entity_type'] == 'money':
        signals.append({'signal': 'monetary_value', 'evidence': ent['entity_value']})
        score += 10
    elif ent['entity_type'] == 'person' and any(
        t in (ent['entity_value'] or '').lower()
        for t in ('vp', 'director', 'ceo', 'cto', 'head of', 'founder')
    ):
        signals.append({'signal': 'decision_maker', 'evidence': ent['entity_value']})
        score += 8
```

---

## 3. CO_MARKETING Gem Detection

### 3.1 Problem

`_detect_co_marketing()` is a stub that always returns `[]`. The spec describes audience overlap detection.

### 3.2 Implementation

```python
def _detect_co_marketing(
    db: sqlite3.Connection, profile, engagement_config: EngagementConfig | None = None
) -> list[dict]:
    """Detect co-marketing opportunities where audiences overlap."""
    industry = profile['industry'] or ''
    target = profile['target_audience'] or ''
    size = profile['company_size'] or ''

    if not industry or not target:
        return []

    # Skip enterprise companies (unlikely to co-market with you)
    if size == 'enterprise':
        return []

    # Check audience overlap against user's config
    your_audience = ''
    your_industries = []
    if engagement_config:
        your_audience = (engagement_config.your_audience or '').lower()
        # Load target industries from scoring config would be better,
        # but engagement_config.your_audience is the primary signal

    # Heuristic: audience overlap exists if:
    # 1. They target an audience similar to yours (keyword overlap)
    # 2. They're in a complementary (not competing) industry
    # 3. They're not too small (need actual audience) or too large (won't care)

    target_lower = target.lower()
    audience_overlap_keywords = [
        'saas', 'agency', 'agencies', 'startup', 'startups', 'smb',
        'small business', 'marketer', 'marketing', 'developer', 'engineers',
        'ecommerce', 'e-commerce', 'founder', 'founders', 'b2b',
    ]

    overlap_score = 0
    overlap_evidence = []

    for keyword in audience_overlap_keywords:
        if keyword in target_lower and keyword in your_audience:
            overlap_score += 1
            overlap_evidence.append(keyword)

    if overlap_score < 2:
        return []

    # Check they have distribution capability (newsletter, social, content)
    segments = json.loads(profile['economic_segments']) if profile['economic_segments'] else []
    has_distribution = 'distribution_map' in segments
    has_content = profile['total_messages'] and profile['total_messages'] > 5

    if not has_distribution and not has_content:
        return []

    score = 25 + (overlap_score * 5)
    signals = [
        {'signal': 'audience_overlap', 'evidence': f"Shared audience keywords: {', '.join(overlap_evidence[:5])}"},
        {'signal': 'target_audience', 'evidence': f"They target: {target[:100]}"},
    ]

    if has_distribution:
        signals.append({'signal': 'has_distribution', 'evidence': 'Active content/newsletter publisher'})
        score += 10

    return [{
        'gem_type': GemType.CO_MARKETING.value,
        'score': min(score, 100),
        'explanation': {
            'gem_type': 'co_marketing',
            'summary': f"{profile['company_name']} targets a similar audience — co-marketing opportunity.",
            'signals': signals,
            'confidence': 0.6,
        },
        'recommended_actions': [
            'Propose co-branded content or webinar',
            'Suggest audience swap or cross-promotion',
            'Explore joint case study opportunity',
        ],
    }]
```

### 3.3 Changes

| File | Change |
|------|--------|
| `stages/profile.py` | Replace stub `_detect_co_marketing()` with full implementation |
| `stages/profile.py` | `detect_gems()`: pass `engagement_config` to `_detect_co_marketing()` |
| `stages/profile.py` | `detect_gems()` signature: add `engagement_config: EngagementConfig | None = None` parameter |
| `cli.py` | `gems_cmd()`: pass engagement config to `detect_gems()` |
| `web/tasks.py` | `_execute_stage()` for profile: pass engagement config |

---

## 4. Gem Explanation Enrichment

### 4.1 Problem

Gem explanations lack `estimated_value` and `urgency` fields that the spec defines.

### 4.2 Implementation

Add to every gem detection function's explanation dict:

```python
'estimated_value': 'low' | 'medium' | 'medium-high' | 'high',
'urgency': 'low — ...' | 'medium — ...' | 'high — ...',
```

Value and urgency rules per gem type:

| Gem Type | Estimated Value | Urgency Logic |
|----------|----------------|---------------|
| `dormant_warm_thread` | Based on entity money signals + decision-maker presence. Default `medium`. | `high` if dormancy 14-60 days (reply window closing), `medium` 60-180, `low` 180+ |
| `unanswered_ask` | `medium-high` (someone is waiting) | `high` always (recent ask) |
| `weak_marketing_lead` | Based on company size: small=`medium`, medium=`medium-high` | `low` (evergreen opportunity) |
| `partner_program` | `medium` (passive revenue) | `low` unless partner program has application deadline |
| `renewal_leverage` | Based on monetary signals if available, else `medium` | `high` if renewal date within 30 days, `medium` within 60, `low` otherwise |
| `distribution_channel` | `medium` if active publisher, `low` otherwise | `low` (evergreen) |
| `co_marketing` | `medium` | `low` (evergreen) |
| `vendor_upsell` | `low` (leverage, not direct revenue) | `medium` (time-limited offers) |
| `industry_intel` | `low` (intelligence, not direct revenue) | `low` |
| `procurement_signal` | `high` (active buying signal) | `high` (procurement windows close) |

### 4.3 Changes

| File | Change |
|------|--------|
| `stages/profile.py` | All 10 `_detect_*` functions: add `estimated_value` and `urgency` to explanation dict |

---

## 5. Strategy-Specific Engagement Prompts

### 5.1 Problem

A single `ENGAGEMENT_PROMPT` is used for all 8 strategies. The spec defines distinct template variables, generation rules, and tone guidance per strategy. A "Renewal Negotiation" draft should read completely differently from a "Thread Revival" draft.

### 5.2 Implementation

Replace the single `ENGAGEMENT_PROMPT` with a `STRATEGY_PROMPTS` dict in `ai/prompts.py`:

```python
STRATEGY_PROMPTS = {
    'audit': """You are generating an "I Audited Your Funnel" outreach message.

STRATEGY: Consultative audit — highlight specific observations from their emails.
GEM TYPE: {gem_type}
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry} | Size: {company_size}
  ESP: {esp_used} | Marketing Score: {sophistication}/10
  Specific observation: {observation}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write a short email (under 150 words) that:
1. Opens with a SPECIFIC observation about THEIR marketing (e.g., "your last 5 emails all used identical CTAs")
2. Demonstrates expertise by explaining WHY this matters (lost conversions, missed segmentation, etc.)
3. Positions your service as the fix, without being salesy
4. Ends with a low-friction CTA ("worth a 10-minute look?")
5. Addresses {contact_name} by name if available

Sound like a peer who noticed something, not a vendor pitching. Be blunt and specific.

Respond in JSON:
{{
  "subject_line": "email subject — reference their specific issue",
  "body": "the email body text"
}}""",

    'revival': """You are generating a thread revival message for a dormant conversation.

STRATEGY: Re-engage a stalled conversation with context-aware follow-up.
GEM TYPE: {gem_type}
ORIGINAL THREAD SUBJECT: {thread_subject}
DORMANCY: {dormancy_days} days since last activity
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Contact: {contact_name}, {contact_role}
  Company: {company_name}
  Original topic context: {observation}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Rules:
- NEVER open with "sorry for the delay" — it's weak
- Acknowledge the gap briefly ("Circling back on this" or "This got buried"), then add value
- Reference the SPECIFIC thing discussed, proving you remember the context
- Provide something NEW (an insight, an update, a relevant offer) that justifies re-engagement
- If THEY asked you something: be substantive, bring an answer or something to the table
- If it was a mutual discussion: add a new angle or development
- Keep it under 100 words — revival messages should be light

Respond in JSON:
{{
  "subject_line": "Re: {thread_subject}",
  "body": "the email body text"
}}""",

    'partner': """You are generating a partner program application or outreach message.

STRATEGY: Apply to or inquire about a vendor's partner/affiliate program.
GEM TYPE: {gem_type}
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Vendor: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Partner program URLs: {partner_urls}

MY SERVICES: {user_service_description}
MY AUDIENCE: {user_audience}
MY TONE: {user_preferred_tone}

Write a partner program inquiry (under 150 words) that:
1. Establishes you as an existing user/follower of their product (if true)
2. Describes YOUR audience and why it's relevant to them
3. Quantifies or estimates your referral potential
4. Asks about commission structure or next steps
5. Frames it as mutual benefit, not you asking for a favor

Respond in JSON:
{{
  "subject_line": "Partnership inquiry — [your company/name]",
  "body": "the email body text"
}}""",

    'renewal_negotiation': """You are generating a renewal negotiation email.

STRATEGY: Negotiate an upcoming SaaS renewal with data-driven leverage.
GEM TYPE: {gem_type}
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Vendor: {company_name}
  Contact: {contact_name}, {contact_role}
  Renewal dates: {renewal_dates}
  Monetary signals: {monetary_signals}

MY TONE: {user_preferred_tone}

Write a negotiation email (under 200 words) that:
1. Acknowledges the relationship positively but briefly
2. References the upcoming renewal specifically
3. Makes a concrete ask: multi-year discount, feature upgrade, usage-based pricing, or competitive match
4. Mentions (without threatening) that you're evaluating alternatives
5. Proposes a call to discuss terms
6. Is firm but collegial — you're a valued customer, not a supplicant

Respond in JSON:
{{
  "subject_line": "Upcoming renewal — let's discuss terms",
  "body": "the email body text"
}}""",

    'industry_report': """You are generating a content-led engagement message.

STRATEGY: Invite the sender to be featured in an industry intelligence report.
GEM TYPE: {gem_type}
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Their product: {product_description}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write an invitation email (under 150 words) that:
1. References a specific industry report or analysis you're publishing
2. Explains why THEIR company is relevant to the report (specific data point or positioning)
3. Offers to feature them (named or anonymized, their choice)
4. Positions this as exposure/credibility for them, not a favor to you
5. CTA: "Would you be open to a 10-minute data check?" or similar

Respond in JSON:
{{
  "subject_line": "Featuring {company_name} in our {industry} report",
  "body": "the email body text"
}}""",

    'mirror': """You are generating a mirror-match engagement message.

STRATEGY: Match the sender's own style and channel preferences.
GEM TYPE: {gem_type}
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry} | Size: {company_size}
  Their ESP: {esp_used}
  Their marketing score: {sophistication}/10
  Their pain points: {pain_points}
  Their product: {product_description}
  Their CTAs style: {observation}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Rules for mirror matching:
- If their marketing score is low (1-4): send plain text, founder-style, casual
- If their marketing score is mid (5-7): send clean, professional, moderate length
- If their marketing score is high (8-10): send polished, include a specific data point or case study reference
- Reference the SAME pain points they address, reframed for YOUR service
- Mirror their approximate email length and tone
- Include social proof if they use social proof in their own emails
- Under 150 words

Respond in JSON:
{{
  "subject_line": "email subject matching their style",
  "body": "the email body text"
}}""",

    'distribution_pitch': """You are generating a pitch to get featured in a newsletter, podcast, or event.

STRATEGY: Pitch to a distribution channel that could amplify your reach.
GEM TYPE: {gem_type}
GEM SIGNALS: {gem_explanation_json}

RECIPIENT:
  Publication/Channel: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Their audience: {target_audience}

MY SERVICES: {user_service_description}
MY AUDIENCE: {user_audience}
MY TONE: {user_preferred_tone}

Write a pitch email (under 150 words) that:
1. References a SPECIFIC recent topic they covered that you can riff on
2. Proposes a unique angle or data you can contribute (not generic "I'd love to be on your show")
3. Explains why their audience specifically would care about your perspective
4. Suggests a format: guest post, interview, data contribution, or sponsorship
5. Is peer-to-peer, not fan-to-creator

Respond in JSON:
{{
  "subject_line": "Content pitch — [your angle in 5 words]",
  "body": "the email body text"
}}""",
}

# Fallback for unmapped strategies
DEFAULT_ENGAGEMENT_PROMPT = ENGAGEMENT_PROMPT  # keep existing as fallback
```

### 5.3 Additional Context Assembly

Each strategy needs specific context variables. Add a `_build_strategy_context()` function to `stages/engage.py`:

```python
def _build_strategy_context(
    strategy: str, gem: dict, profile: dict, engagement_config: EngagementConfig
) -> dict:
    """Build strategy-specific context variables for the prompt."""
    base = {
        'strategy_name': strategy,
        'gem_type': gem['gem_type'],
        'gem_explanation_json': gem['explanation'],
        'company_name': profile['company_name'] or profile['sender_domain'],
        'contact_name': '',
        'contact_role': '',
        'industry': profile['industry'] or 'Unknown',
        'company_size': profile['company_size'] or 'Unknown',
        'esp_used': profile['esp_used'] or 'Unknown',
        'sophistication': profile['marketing_sophistication_avg'] or 0,
        'product_description': profile['product_description'] or 'Unknown',
        'pain_points': profile['pain_points'] or '[]',
        'observation': '',
        'user_service_description': engagement_config.your_service,
        'user_preferred_tone': engagement_config.your_tone,
        'user_audience': engagement_config.your_audience or '',
    }

    # Extract contact from known_contacts
    contacts = json.loads(profile['known_contacts']) if profile['known_contacts'] else []
    if contacts:
        c = contacts[0]
        base['contact_name'] = c.get('name', '')
        base['contact_role'] = c.get('role', '')

    # Strategy-specific additions
    if strategy == 'revival':
        explanation = json.loads(gem['explanation']) if isinstance(gem['explanation'], str) else gem['explanation']
        base['thread_subject'] = explanation.get('summary', '')[:100]
        base['dormancy_days'] = ''
        for sig in explanation.get('signals', []):
            if sig.get('signal') == 'dormancy_duration':
                base['dormancy_days'] = sig.get('value', '')

    elif strategy == 'renewal_negotiation':
        base['renewal_dates'] = profile['renewal_dates'] or '[]'
        base['monetary_signals'] = profile['monetary_signals'] or '[]'

    elif strategy == 'partner':
        base['partner_urls'] = profile['partner_program_urls'] or '[]'

    elif strategy == 'distribution_pitch':
        base['target_audience'] = profile['target_audience'] or 'their audience'

    # Build observation from most distinctive signal
    offer_dist = json.loads(profile['offer_type_distribution']) if profile['offer_type_distribution'] else {}
    ctas = json.loads(profile['cta_texts_all']) if profile['cta_texts_all'] else []
    if ctas:
        base['observation'] = f"CTAs used: {', '.join(ctas[:3])}"
    elif offer_dist:
        top_offers = sorted(offer_dist.items(), key=lambda x: x[1], reverse=True)[:3]
        base['observation'] = f"Email types: {', '.join(k for k, v in top_offers)}"

    return base
```

### 5.4 Changes

| File | Change |
|------|--------|
| `ai/prompts.py` | Add `STRATEGY_PROMPTS` dict with 7 strategy-specific prompts. Keep `ENGAGEMENT_PROMPT` as `DEFAULT_ENGAGEMENT_PROMPT` fallback. |
| `stages/engage.py` | Add `_build_strategy_context()` for per-strategy context assembly |
| `stages/engage.py` | `generate_engagement()`: look up strategy in `STRATEGY_PROMPTS`, fall back to default |
| `stages/engage.py` | Pass `thread_subject`, `dormancy_days`, `renewal_dates`, `monetary_signals`, `partner_urls`, `target_audience`, `user_audience` as additional template variables |

---

## 6. Entity Extraction Refinements

### 6.1 Relationship Type Classification

Add relationship typing for person and organization entities.

**Person relationship types:**

```python
def _classify_person_relationship(role: str, source: str, from_address: str) -> str:
    """Classify a person's relationship type based on available signals."""
    role_lower = (role or '').lower()

    if any(t in role_lower for t in ('vp', 'director', 'ceo', 'cto', 'cfo',
                                      'head of', 'founder', 'president', 'chief')):
        return 'decision_maker'

    if source == 'header' and role_lower == '':
        return 'automated'  # likely system-generated email

    if any(t in role_lower for t in ('account', 'sales', 'representative',
                                      'manager', 'support', 'success')):
        return 'vendor_contact'

    return 'peer'
```

**Organization relationship types:**

```python
def _classify_org_relationship(org_name: str, sender_domain: str, profile_segments: list) -> str:
    """Classify organization relationship based on available context."""
    if 'spend_map' in profile_segments:
        return 'vendor'
    if 'partner_map' in profile_segments:
        return 'partner'
    if 'prospect_map' in profile_segments:
        return 'prospect'
    return 'unknown'
```

### 6.2 Date `is_future` Flag

Add future-date detection to the date regex extractors:

```python
def _is_future_date(date_str: str) -> bool:
    """Attempt to parse a date string and check if it's in the future."""
    from dateutil import parser as dateparser
    try:
        parsed = dateparser.parse(date_str, fuzzy=True)
        return parsed > datetime.now() if parsed else False
    except (ValueError, OverflowError):
        return False
```

Store `is_future` in the `context` field or `entity_normalized` field as metadata (no schema change needed — encode as `"renewal:future"` or `"expiration:past"` in `entity_normalized`).

### 6.3 CC/BCC Extraction

Add CC/BCC address parsing as person entities:

```python
def _extract_cc_entities(message) -> list[dict]:
    """Extract person entities from CC addresses."""
    entities = []
    cc = json.loads(message['cc_addresses']) if message['cc_addresses'] else []
    for addr in cc:
        if isinstance(addr, str) and '@' in addr:
            entities.append({
                'entity_type': 'person',
                'entity_value': addr,
                'entity_normalized': addr.split('@')[0].replace('.', ' ').title(),
                'context': 'CC recipient — organizational structure signal',
                'confidence': 0.6,
                'source': 'header',
            })
    return entities
```

### 6.4 Config Toggle Enforcement

Make `extract_monetary`, `extract_dates`, `extract_procurement` booleans actually control their respective extractors in `extract_entities()`.

### 6.5 Changes

| File | Change |
|------|--------|
| `stages/entities.py` | Add `_classify_person_relationship()` and `_classify_org_relationship()` |
| `stages/entities.py` | Add `_is_future_date()`, tag date entities with future/past in `entity_normalized` |
| `stages/entities.py` | Add `_extract_cc_entities()`, called from main extraction loop |
| `stages/entities.py` | Check `config.entity_extraction.extract_monetary` etc. before running respective extractors |
| `pyproject.toml` | Add `python-dateutil` dependency (likely already installed as transitive dep) |

---

## 7. Deterministic Marketing Sophistication Score

### 7.1 Problem

Spec section 7.2.3 defines a specific 10-point formula. Currently this is delegated entirely to the AI, which produces inconsistent scores across runs.

### 7.2 Implementation

Add `compute_sophistication_score()` to `stages/metadata.py` or a new `stages/scoring.py`:

```python
def compute_sophistication_score(
    esp: str, has_personalization: bool, has_utm: bool,
    template_complexity: int, spf: str, dkim: str, dmarc: str,
    has_unsubscribe: bool, unique_campaign_count: int
) -> int:
    """Compute deterministic marketing sophistication score (1-10).

    Based on spec section 7.2.3:
    - ESP tier: 1-3 points
    - Personalization depth: 0-2 points
    - UTM parameter usage: 0-1 point
    - Template quality: 0-1 point
    - Segmentation signals: 0-1 point
    - Authentication (SPF + DKIM + DMARC): 0-1 point
    - Unsubscribe quality: 0-1 point
    """
    score = 0

    # ESP tier (1-3 points)
    tier3_esps = {'hubspot', 'salesforce', 'klaviyo', 'activecampaign'}
    tier2_esps = {'sendgrid', 'mailchimp', 'constant_contact', 'convertkit', 'postmark'}
    tier1_esps = {'amazon_ses', 'mailgun', 'custom_smtp', ''}

    esp_lower = (esp or '').lower().replace(' ', '_')
    if esp_lower in tier3_esps:
        score += 3
    elif esp_lower in tier2_esps:
        score += 2
    else:
        score += 1

    # Personalization depth (0-2 points)
    if has_personalization:
        score += 2
    # Note: could differentiate basic (1pt) vs dynamic content blocks (2pts)
    # but current content parser doesn't distinguish depth

    # UTM parameter usage (0-1 point)
    if has_utm:
        score += 1

    # Template quality (0-1 point)
    if template_complexity and template_complexity >= 40:
        score += 1

    # Segmentation signals (0-1 point)
    if unique_campaign_count and unique_campaign_count >= 3:
        score += 1

    # Authentication (0-1 point)
    auth_passing = sum(1 for r in [spf, dmarc] if r == 'pass') + (1 if dkim else 0)
    if auth_passing >= 3:
        score += 1

    # Unsubscribe quality (0-1 point)
    if has_unsubscribe:
        score += 1

    return max(1, min(score, 10))
```

### 7.3 Integration

This score is computed during **profile building** (Stage 5) as a deterministic baseline. The AI classification's `marketing_sophistication` becomes a second opinion. The profile stores the deterministic score. If the two differ by more than 3 points, flag for review.

### 7.4 Changes

| File | Change |
|------|--------|
| `stages/profile.py` | Add `compute_sophistication_score()` |
| `stages/profile.py` | `_build_single_profile()`: compute deterministic score from aggregated metadata+content, use as `marketing_sophistication_avg` instead of (or blended with) AI average |

---

## 8. Classification Feedback Loop

### 8.1 `classify --retrain`

Add a `--retrain` flag to the classify command that incorporates override history as few-shot examples in the prompt.

```python
def _build_few_shot_examples(db: sqlite3.Connection) -> str:
    """Build few-shot examples from classification overrides."""
    overrides = db.execute(
        """SELECT co.sender_domain, co.field_name, co.corrected_value,
                  ac.industry, ac.sender_intent, ac.company_size_estimate
           FROM classification_overrides co
           JOIN ai_classification ac ON co.message_id = ac.message_id
           ORDER BY co.created_at DESC
           LIMIT 10"""
    ).fetchall()

    if not overrides:
        return ''

    examples = '\n\nFEW-SHOT CORRECTION EXAMPLES (learn from these past corrections):\n'
    for ov in overrides:
        examples += f'- {ov["sender_domain"]}: {ov["field_name"]} was "{getattr(ov, ov["field_name"], "?")}" → corrected to "{ov["corrected_value"]}"\n'

    return examples
```

Append this to `CLASSIFICATION_PROMPT` when `--retrain` is active.

### 8.2 Message-Scoped Override Application

`_get_sender_overrides()` currently only queries sender-scoped overrides. Add message-scoped override lookup:

```python
# In classify.py, after getting sender overrides:
msg_overrides = db.execute(
    """SELECT field_name, corrected_value FROM classification_overrides
       WHERE message_id = ? AND override_scope = 'message'""",
    (message_id,),
).fetchall()
for ov in msg_overrides:
    result[ov['field_name']] = ov['corrected_value']
    result['has_override'] = True
```

### 8.3 Changes

| File | Change |
|------|--------|
| `stages/classify.py` | Add `_build_few_shot_examples()`, append to prompt when `retrain=True` |
| `stages/classify.py` | `classify_messages()`: add `retrain: bool = False` parameter |
| `stages/classify.py` | Add message-scoped override application alongside sender-scoped |
| `cli.py` | Add `--retrain` flag to classify command |

---

## 9. Content Parser — Footer Stripping

### 9.1 Problem

Footer/legal blocks remain in `body_clean`, polluting downstream analysis with boilerplate.

### 9.2 Implementation

Add `_strip_footer()` to `stages/content.py`:

```python
FOOTER_PATTERNS = [
    r'(?i)you(?:\'re| are) receiving this (?:email|message) because',
    r'(?i)to (?:stop receiving|unsubscribe|opt[- ]?out)',
    r'(?i)manage (?:your )?(?:email )?preferences',
    r'(?i)view (?:this email )?in (?:your )?browser',
    r'(?i)(?:copyright|©)\s*\d{4}',
    r'(?i)all rights reserved',
    r'(?i)privacy policy',
    r'(?i)terms (?:of (?:service|use)|and conditions)',
    r'(?i)this email was sent (?:to|by)',
    r'(?i)if you no longer (?:wish|want)',
    r'(?i)powered by (?:mailchimp|sendgrid|hubspot|klaviyo|constant contact)',
]

def _strip_footer(text: str) -> tuple[str, str]:
    """Strip footer/legal blocks from text. Returns (clean_text, footer_text)."""
    lines = text.split('\n')
    footer_start = len(lines)

    # Scan from bottom up for footer markers
    for i in range(len(lines) - 1, max(len(lines) - 20, -1), -1):
        line = lines[i].strip()
        if not line:
            continue
        for pattern in FOOTER_PATTERNS:
            if re.search(pattern, line):
                footer_start = i
                break

    if footer_start < len(lines):
        return '\n'.join(lines[:footer_start]).rstrip(), '\n'.join(lines[footer_start:])
    return text, ''
```

### 9.3 Changes

| File | Change |
|------|--------|
| `stages/content.py` | Add `FOOTER_PATTERNS` and `_strip_footer()` |
| `stages/content.py` | `_parse_single_message()`: call `_strip_footer()` on `body_clean` after signature stripping, before other extraction |

---

## 10. Metadata Extraction — Missing Fields

### 10.1 Fields to Add

| Field | Source | Storage |
|-------|--------|---------|
| `x_mailer` | `X-Mailer` header | New column in `parsed_metadata` |
| `mail_server` | Outermost `Received` header hostname | New column in `parsed_metadata` |
| `precedence` | `Precedence` header value | New column in `parsed_metadata` |
| `feedback_id` | `X-Feedback-ID` or `Feedback-ID` header | New column in `parsed_metadata` |

### 10.2 Schema Change

```sql
ALTER TABLE parsed_metadata ADD COLUMN x_mailer TEXT;
ALTER TABLE parsed_metadata ADD COLUMN mail_server TEXT;
ALTER TABLE parsed_metadata ADD COLUMN precedence TEXT;
ALTER TABLE parsed_metadata ADD COLUMN feedback_id TEXT;
```

Also update `schema.sql` with the new columns for fresh installs. Add to `db --migrate`.

### 10.3 Extraction

```python
def _extract_x_mailer(headers: dict) -> str | None:
    return headers.get('x-mailer', None)

def _extract_mail_server(headers: dict) -> str | None:
    received = headers.get('received', '')
    # Extract hostname from "from mail-server.example.com (...)"
    match = re.search(r'from\s+([\w.-]+\.\w+)', received)
    return match.group(1) if match else None

def _extract_precedence(headers: dict) -> str | None:
    return headers.get('precedence', None)

def _extract_feedback_id(headers: dict) -> str | None:
    return headers.get('x-feedback-id', headers.get('feedback-id', None))
```

### 10.4 Changes

| File | Change |
|------|--------|
| `schema.sql` | Add 4 columns to `parsed_metadata` |
| `database.py` | Add migration for existing DBs (ALTER TABLE) |
| `stages/metadata.py` | Add 4 extraction functions, include in INSERT |
| `web/models.py` | Add 4 columns to `ParsedMetadata` SQLAlchemy model |

---

## 11. OpenAI Provider

### 11.1 Implementation

Add `ai/openai_provider.py`:

```python
"""OpenAI AI provider using the openai SDK."""
from gemsieve.ai.base import AIProvider

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str | None = None):
        import openai
        self.client = openai.OpenAI(api_key=api_key)  # reads OPENAI_API_KEY env var

    def complete(self, prompt: str, model: str, system: str = '',
                 response_format: dict | None = None) -> str:
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})

        kwargs = {'model': model, 'messages': messages, 'temperature': 0.3}
        if response_format:
            kwargs['response_format'] = {'type': 'json_object'}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
```

### 11.2 Changes

| File | Change |
|------|--------|
| `ai/openai_provider.py` | New file |
| `ai/__init__.py` | Add `openai:` prefix handling in `get_provider()` |
| `pyproject.toml` | Add `openai>=1.0` to optional deps `[openai]` |
| `config.py` | Document `OPENAI_API_KEY` env var |

Usage: `gemsieve classify --model openai:gpt-4o`

---

## 12. PostgreSQL CLI Support

### 12.1 Problem

The raw SQL layer in `database.py` only supports SQLite. PostgreSQL only works through the web admin's SQLAlchemy layer.

### 12.2 Implementation

Wrap the database layer to detect `DATABASE_URL` and use psycopg for PostgreSQL:

```python
def get_db(config=None) -> Connection:
    """Get a database connection. Supports SQLite and PostgreSQL via DATABASE_URL."""
    database_url = os.environ.get('DATABASE_URL', '')

    if database_url.startswith('postgresql'):
        import psycopg
        conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
        return conn

    # Existing SQLite path
    db_path = _get_db_path(config)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

### 12.3 SQL Compatibility

The main incompatibility between SQLite and PostgreSQL in the codebase:
- `INSERT OR REPLACE` → `INSERT ... ON CONFLICT DO UPDATE`
- `AUTOINCREMENT` → `SERIAL` / `GENERATED ALWAYS AS IDENTITY`
- `JSON` type → `JSONB`
- `?` parameter markers → `%s`
- `PRAGMA` statements → no-op for PostgreSQL

Strategy: Create `schema_pg.sql` with PostgreSQL DDL. Add a `_is_postgres()` helper. For the parameter marker difference, use a thin wrapper or conditional SQL generation in the few places that differ.

### 12.4 Changes

| File | Change |
|------|--------|
| `database.py` | Add PostgreSQL connection path in `get_db()` |
| `schema_pg.sql` | New file: PostgreSQL-compatible DDL |
| `database.py` | `init_db()`: detect backend and use appropriate schema file |
| `pyproject.toml` | Add `psycopg[binary]>=3.1` to optional deps `[postgres]` |

### 12.5 Scope Note

Full PostgreSQL support across all stages requires auditing every SQL statement for compatibility. This is a significant effort. Phase 2 delivers the connection layer and schema; individual stage SQL compatibility can be addressed incrementally.

---

## 13. Segmentation Refinements

### 13.1 Sub-Segment Improvements

Replace hardcoded sub-segments with actual classification logic:

**Distribution sub-segments:**
```python
def _classify_distribution_subsegment(db, profile) -> list[tuple[str, float]]:
    offer_dist = json.loads(profile['offer_type_distribution']) if profile['offer_type_distribution'] else {}
    sub = []
    if 'newsletter' in offer_dist:
        sub.append(('newsletter', 0.8))
    if 'event' in offer_dist or 'webinar' in offer_dist:
        sub.append(('event', 0.7))
    # Check for podcast/community signals in content
    if 'community' in offer_dist:
        sub.append(('community', 0.6))
    return sub or [('newsletter', 0.5)]
```

**Procurement sub-segments:**
```python
def _classify_procurement_subsegment(db, profile) -> list[tuple[str, float]]:
    domain = profile['sender_domain']
    entities = db.execute(
        """SELECT entity_normalized FROM extracted_entities ee
           JOIN parsed_metadata pm ON ee.message_id = pm.message_id
           WHERE pm.sender_domain = ? AND ee.entity_type = 'procurement_signal'""",
        (domain,),
    ).fetchall()

    keywords = [e['entity_normalized'] for e in entities]
    if any('security' in k or 'SOC' in k or 'compliance' in k for k in keywords):
        return [('security_review', 0.8)]
    if any('RFP' in k or 'proposal' in k or 'evaluation' in k for k in keywords):
        return [('vendor_evaluation', 0.8)]
    return [('evaluation', 0.5)]
```

**Spend map — churned vendor detection:**
```python
# In _classify_spend_subsegment:
if renewal_dates:
    return [('upcoming_renewal', 0.8)]
last_contact = profile['last_contact']
if last_contact:
    days_since = (datetime.now(timezone.utc) - datetime.fromisoformat(last_contact)).days
    if days_since > 180:
        return [('churned_vendor', 0.6)]
return [('active_subscription', 0.7)]
```

### 13.2 Changes

| File | Change |
|------|--------|
| `stages/segment.py` | Replace hardcoded sub-segment classifiers with logic-based implementations |
| `stages/segment.py` | Add churned vendor detection to spend sub-segments |

---

## 14. Distribution Channel Detection Enhancement

### 14.1 Problem

Currently only checks segment membership and message volume. Should check for guest content opportunities.

### 14.2 Implementation

```python
DISTRIBUTION_CONTENT_SIGNALS = [
    r'(?i)\bguest post\b',
    r'(?i)\bguest author\b',
    r'(?i)\bcontribute\b.*\barticle\b',
    r'(?i)\bspeaker\b.*\bapplication\b',
    r'(?i)\bcall for\b.*\b(?:speakers|papers|submissions)\b',
    r'(?i)\bsubmit your\b.*\bstory\b',
    r'(?i)\bpodcast\b.*\binterview\b',
    r'(?i)\bsponsorship\b.*\b(?:opportunities|packages)\b',
]

def _detect_distribution_channel(db, profile) -> list[dict]:
    # ... existing segment check ...

    # Check message content for distribution signals
    domain = profile['sender_domain']
    content_rows = db.execute(
        """SELECT pc.body_clean FROM parsed_content pc
           JOIN parsed_metadata pm ON pc.message_id = pm.message_id
           WHERE pm.sender_domain = ? AND pc.body_clean IS NOT NULL
           LIMIT 20""",
        (domain,),
    ).fetchall()

    content_text = ' '.join(r['body_clean'] for r in content_rows)
    content_signals = []
    for pattern in DISTRIBUTION_CONTENT_SIGNALS:
        match = re.search(pattern, content_text)
        if match:
            content_signals.append(match.group(0).strip()[:80])

    if content_signals:
        signals.append({'signal': 'content_opportunity', 'evidence': ', '.join(content_signals[:3])})
        score += 15
```

### 14.3 Changes

| File | Change |
|------|--------|
| `stages/profile.py` | Add `DISTRIBUTION_CONTENT_SIGNALS`, scan content in `_detect_distribution_channel()` |

---

## 15. `max_outreach_per_day` and `preferred_strategies` Enforcement

### 15.1 Problem

Config fields exist but are never checked.

### 15.2 Implementation

In `generate_engagement()`:

```python
# At the start of generate_engagement():
if engagement_config and engagement_config.preferred_strategies:
    gems = [g for g in gems if GEM_STRATEGY_MAP.get(g['gem_type']) in engagement_config.preferred_strategies]

# Before generating each draft:
today_count = db.execute(
    "SELECT COUNT(*) as c FROM engagement_drafts WHERE date(generated_at) = date('now')"
).fetchone()['c']
if engagement_config and today_count >= engagement_config.max_outreach_per_day:
    break  # daily limit reached
```

### 15.3 Changes

| File | Change |
|------|--------|
| `stages/engage.py` | Filter gems by `preferred_strategies`, enforce `max_outreach_per_day` |

---

## Implementation Order

| Priority | Section | Effort | Impact |
|----------|---------|--------|--------|
| **P0** | 1. Thread intelligence (content-aware response detection) | Medium | High — fixes false positives in two gem types |
| **P0** | 2. Warm signal detection in dormant threads | Medium | High — dramatically improves top gem type quality |
| **P0** | 5. Strategy-specific engagement prompts | Large | High — the entire point of engagement generation |
| **P1** | 3. CO_MARKETING gem detection | Small | Medium — activates a dead gem type |
| **P1** | 4. Gem explanation enrichment (estimated_value, urgency) | Small | Medium — better prioritization in UI |
| **P1** | 7. Deterministic sophistication score | Medium | Medium — consistent scoring across runs |
| **P1** | 9. Footer stripping | Small | Medium — cleaner downstream analysis |
| **P1** | 14. Distribution channel detection enhancement | Small | Medium — better distribution gem quality |
| **P1** | 15. Config enforcement (max_outreach, preferred_strategies) | Small | Small — respects user config |
| **P2** | 6. Entity extraction refinements | Medium | Medium — richer entity data |
| **P2** | 8. Classification feedback loop (--retrain) | Medium | Medium — improves accuracy over time |
| **P2** | 10. Metadata missing fields | Small | Small — completeness |
| **P2** | 13. Segmentation refinements | Small | Small — richer sub-segments |
| **P3** | 11. OpenAI provider | Small | Small — additional provider option |
| **P3** | 12. PostgreSQL CLI support | Large | Small — most users use SQLite |

---

## Success Criteria

| Metric | Target |
|--------|--------|
| `awaiting_response_from = 'none'` threads | >30% of non-user-participating threads correctly classified as concluded |
| Dormant warm thread false positive reduction | >50% fewer gems for FYI/concluded threads |
| CO_MARKETING gems detected | >0 (currently always 0) |
| Engagement draft quality (subjective) | Strategy-specific prompts produce distinctly different drafts per strategy |
| Deterministic sophistication score | Correlates within 2 points of AI score for >70% of senders |
| Override-trained classifications | Measurable accuracy improvement on re-classify after overrides |
| Footer stripping | >80% of marketing email footers removed from body_clean |

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `gmail/sync.py` | Content-aware `awaiting_response_from` |
| `stages/metadata.py` | 4 new header fields |
| `stages/content.py` | Footer stripping |
| `stages/entities.py` | Relationship types, `is_future` dates, CC extraction, config toggles |
| `stages/classify.py` | `--retrain` flag, message-scoped overrides, few-shot examples |
| `stages/profile.py` | Warm signals, co_marketing, entity cross-ref, estimated_value/urgency, deterministic sophistication |
| `stages/segment.py` | Richer sub-segment classifiers |
| `stages/engage.py` | Strategy-specific prompt selection, context assembly, config enforcement |
| `ai/prompts.py` | 7 strategy-specific prompts |
| `ai/openai_provider.py` | New file |
| `ai/__init__.py` | OpenAI provider registration |
| `cli.py` | `--retrain` flag |
| `schema.sql` | 4 new columns on `parsed_metadata` |
| `database.py` | PostgreSQL connection, migration |
| `schema_pg.sql` | New file |
| `web/models.py` | 4 new columns on ParsedMetadata model |
| `pyproject.toml` | New optional deps: `openai`, `psycopg`, `python-dateutil` |
