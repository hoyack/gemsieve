# GemSieve Phase 3 — Gem Detection Overhaul

## Post-Mortem: Why Top Gems Are All Wrong

### The Evidence

Top 10 gems by score, with ground truth:

| Sender | Score | Ground Truth | Should Score |
|--------|-------|-------------|-------------|
| unicorncapital.io | ~870 | Business broker USER HIRED | Near 0 |
| ruskinconsulting.com | ~850 | Marketing agency USER HIRED | Near 0 |
| rosenblattlawfirm.com | ~280 | Law firm USER HIRED | Near 0 |
| stripe.com | ~260 | Payment processor, USER DOESN'T EVEN USE | 0 |
| mail.service.thehartford.com | ~200 | Insurance company soliciting user | Near 0 |
| notification.intuit.com | ~180 | User's accounting software | Near 0 |
| google.com | ~170 | Google (generic) | Near 0 |
| findmyitpartner.com | ~150 | Actual potential gem | 70+ |
| rippling.com | ~140 | User's PEO/payroll vendor | Near 0 |
| herokumanager.com | ~130 | Noise | 0 |

**Result: 1 out of 10 is a real gem. 10% precision. The algorithm is effectively random.**

### Root Cause Analysis

The scoring system has five fundamental flaws that compound into the results above:

---

#### Flaw 1: No Concept of Relationship Direction

The system treats every sender as a potential revenue target. It cannot distinguish:

- **Vendors you pay** (Intuit, Rippling, Stripe) — these are EXPENSES, not opportunities
- **Service providers you hired** (unicorncapital, ruskinconsulting, rosenblattlawfirm) — completed or active engagements where YOU are the customer
- **Companies selling TO you** (thehartford) — inbound sales, not inbound leads
- **Tools you use** (Google, Heroku) — infrastructure, not opportunities
- **Actual prospects** (findmyitpartner) — someone who COULD become a customer or partner

The current gem types (dormant_warm_thread, partner_program, renewal_leverage, etc.) fire indiscriminately on all of these. A dormant thread with your business broker scores the same as a dormant thread with a potential client.

**This is the #1 problem. Everything else is secondary.**

---

#### Flaw 2: Volume and Diversity Reward Existing Vendors

The scoring formula gives a "gem diversity bonus" of up to 40 points when a sender triggers multiple gem types. Vendors you actively use naturally trigger MORE gem types:

- Rippling → renewal_leverage (they bill you) + vendor_upsell (they pitch features) + procurement_signal (contract terms) + dormant_warm_thread (old support threads) + partner_program (they have one)
- That's 5 gem types × 8 points = 40 points diversity bonus PLUS base score

Your actual prospects probably trigger 1 gem type and score 30.

**The diversity bonus systematically promotes noise over signal.**

---

#### Flaw 3: Dormant Warm Thread Is Too Loose

Any thread where `awaiting_response_from = 'user'` and `days_dormant > 14` becomes a gem. This captures:

- Threads where a vendor asked "anything else you need?" and you didn't reply (not a gem)
- Completed engagements where the last message was a final deliverable (not a gem)
- Support threads where you solved the issue but didn't say thanks (not a gem)
- Newsletter reply threads that went stale (not a gem)
- Actual stalled business conversations where someone wanted to BUY from you (the only real gem)

The warm signal detection (pricing language, meeting requests) helps but can't fix the fundamental problem: it doesn't know WHO would be buying from whom.

---

#### Flaw 4: Subdomain Blindness

`mail.service.thehartford.com` and `notification.intuit.com` are parsed as distinct domains rather than being collapsed to `thehartford.com` and `intuit.com`. This means:

- Known vendor/service patterns aren't recognized
- Messages from the same company via different subdomains create separate profiles
- Classification wastes AI calls on obviously-same companies

---

#### Flaw 5: No "Known Entity" Awareness

The system has no concept of well-known companies that are obviously NOT gems:
- Google, Stripe, Intuit, Heroku — these are infrastructure providers, not prospects
- Insurance companies, banks, payroll providers — these are institutional services
- The user's own vendors are the MOST data-rich senders, so they score highest

---

## The Fix: Relationship-Aware Gem Detection

### Core Principle

**A gem is only a gem if the revenue direction points toward the user.**

Every sender must be classified by RELATIONSHIP DIRECTION before any gem scoring happens. This is a new Stage 5.5 that sits between profiling and scoring:

```
Profile → Relationship Classification → Gem Detection → Scoring
                    ↓
          Filters out vendors,
          tools, known entities,
          and inbound sales
```

---

### New Concept: Sender Relationship Type

Every sender profile gets a `relationship_type` classification:

```python
class RelationshipType(Enum):
    # Revenue flows FROM user TO sender (user is the customer)
    MY_VENDOR = "my_vendor"               # SaaS/service I pay for
    MY_SERVICE_PROVIDER = "my_service_provider"  # professional service I hired
    MY_INFRASTRUCTURE = "my_infrastructure"      # tools, platforms, hosting

    # Revenue flows FROM sender TO user (opportunity)
    INBOUND_PROSPECT = "inbound_prospect"   # they reached out wanting MY services
    WARM_CONTACT = "warm_contact"           # mutual/warm relationship with biz potential
    POTENTIAL_PARTNER = "potential_partner"  # genuine partnership/affiliate opportunity

    # Neutral / no revenue direction
    SELLING_TO_ME = "selling_to_me"         # cold outreach, trying to sell me something
    INSTITUTIONAL = "institutional"          # banks, insurance, government, legal notices
    COMMUNITY = "community"                 # newsletters, forums, communities
    UNKNOWN = "unknown"                     # can't determine
```

### Relationship Detection Signals

#### MY_VENDOR / MY_SERVICE_PROVIDER / MY_INFRASTRUCTURE

These are senders where the user is the CUSTOMER. Detection:

```python
VENDOR_SIGNALS = {
    'transactional_receipts': {
        # User receives invoices, receipts, payment confirmations
        'patterns': [
            r'(?i)\binvoice\b', r'(?i)\breceipt\b', r'(?i)\bpayment.*confirm',
            r'(?i)\bcharge.*\$', r'(?i)\bbilling.*statement',
            r'(?i)\bsubscription.*renew', r'(?i)\bauto.?renew',
            r'(?i)\byour.*plan', r'(?i)\byour.*account',
        ],
        'weight': 0.4,
    },
    'user_initiated_threads': {
        # User sent the FIRST message in threads with this sender
        # (user reached out to them, not the other way around)
        'check': 'thread_initiation_ratio',  # % of threads user started
        'threshold': 0.5,  # user started >50% of threads = likely user's vendor
        'weight': 0.3,
    },
    'onboarding_language': {
        # Welcome emails, setup guides, "getting started"
        'patterns': [
            r'(?i)\bwelcome to\b', r'(?i)\bgetting started\b',
            r'(?i)\byour.*account.*ready', r'(?i)\bsetup.*guide\b',
            r'(?i)\bactivat.*your\b',
        ],
        'weight': 0.2,
    },
    'support_threads': {
        # User asking for help = user is the customer
        'patterns': [
            r'(?i)\bsupport.*ticket\b', r'(?i)\bcase.*#\d+',
            r'(?i)\bhelp.*request\b', r'(?i)\byour.*request',
        ],
        'weight': 0.1,
    },
}

INFRASTRUCTURE_DOMAINS = {
    # Well-known infrastructure that is never a gem
    'google.com', 'gmail.com', 'github.com', 'gitlab.com',
    'aws.amazon.com', 'heroku.com', 'herokumanager.com',
    'digitalocean.com', 'cloudflare.com', 'vercel.com', 'netlify.com',
    'stripe.com', 'paypal.com', 'braintree.com', 'square.com',
    'twilio.com', 'sendgrid.net', 'mailgun.com',
    'slack.com', 'zoom.us', 'notion.so', 'figma.com',
    'atlassian.com', 'jira.com', 'confluence.com',
    'docker.com', 'npmjs.com', 'pypi.org',
}

INSTITUTIONAL_DOMAINS = {
    # Insurance, banking, government, payroll — institutional services
    'thehartford.com', 'geico.com', 'progressive.com', 'statefarm.com',
    'bankofamerica.com', 'chase.com', 'wellsfargo.com', 'citi.com',
    'adp.com', 'paychex.com', 'gusto.com', 'rippling.com',
    'intuit.com', 'quickbooks.com', 'xero.com', 'freshbooks.com',
    'irs.gov', 'ssa.gov',
}
```

#### INBOUND_PROSPECT (the actual gems)

These are the ONLY senders that should score high:

```python
INBOUND_PROSPECT_SIGNALS = {
    'they_reached_out_first': {
        # They initiated the conversation, not the user
        'check': 'thread_initiation_ratio',
        'threshold_inverted': True,  # THEY started >50% of threads
        'weight': 0.3,
    },
    'asking_about_user_services': {
        # Their messages contain questions about what the USER offers
        'patterns': [
            r'(?i)\byour.*(?:service|product|offering|solution|platform)\b',
            r'(?i)\bdo you.*(?:offer|provide|build|handle)\b',
            r'(?i)\bhow much.*(?:cost|charge|price)\b',
            r'(?i)\binterested in.*(?:working|hiring|engaging)\b',
            r'(?i)\blooking for.*(?:someone|help|partner|vendor)\b',
            r'(?i)\bcan you.*(?:help|build|create|do)\b',
        ],
        'weight': 0.4,
    },
    'referral_language': {
        # Someone referred them to the user
        'patterns': [
            r'(?i)\breferred.*(?:by|from)\b',
            r'(?i)\brecommended.*(?:you|your)\b',
            r'(?i)\bintroduction\b',
            r'(?i)\b(?:mutual|common).*(?:contact|connection|friend)\b',
        ],
        'weight': 0.2,
    },
    'small_unknown_company': {
        # Not a known vendor, not institutional, relatively few messages
        'check': 'not_in_known_lists AND total_messages < 20',
        'weight': 0.1,
    },
}
```

#### SELLING_TO_ME

Companies trying to sell the user something (inbound sales, not gems):

```python
SELLING_TO_ME_SIGNALS = {
    'cold_outreach_patterns': {
        'patterns': [
            r'(?i)\bbook.*(?:demo|call|meeting)\b',
            r'(?i)\bschedule.*(?:demo|call)\b',
            r'(?i)\b(?:free|exclusive).*(?:trial|offer|consultation)\b',
            r'(?i)\bunsubscribe\b',  # marketing emails always have this
        ],
        'weight': 0.3,
    },
    'no_user_participation': {
        # User never replied to their threads
        'check': 'user_participated == False in all threads',
        'weight': 0.4,
    },
    'high_volume_one_way': {
        # They send many messages, user replies to none
        'check': 'total_messages > 5 AND user_reply_rate == 0',
        'weight': 0.3,
    },
}
```

---

### Subdomain Collapsing

Before any classification or scoring, normalize sender domains:

```python
def collapse_subdomain(domain: str) -> str:
    """Collapse subdomains to the organizational root domain.

    mail.service.thehartford.com → thehartford.com
    notification.intuit.com → intuit.com
    em.stripe.com → stripe.com
    bounce.google.com → google.com
    """
    import tldextract
    ext = tldextract.extract(domain)
    # Return registered domain (domain + suffix)
    if ext.registered_domain:
        return ext.registered_domain
    return domain  # fallback for unusual TLDs

# Apply at ingestion time:
# parsed_metadata.sender_domain = collapse_subdomain(raw_domain)
# parsed_metadata.sender_subdomain = raw_domain  # preserve original
```

This immediately fixes `mail.service.thehartford.com` → `thehartford.com` and `notification.intuit.com` → `intuit.com`, enabling known-entity matching.

**Add to schema:**

```sql
ALTER TABLE parsed_metadata ADD COLUMN sender_subdomain TEXT;
-- sender_domain becomes the collapsed root domain
-- sender_subdomain preserves the original for forensic use
```

**Dependency:** `tldextract` (add to pyproject.toml)

---

### User Relationship Registry

A new user-maintained table that lets the user explicitly tag senders:

```sql
CREATE TABLE sender_relationships (
    sender_domain TEXT PRIMARY KEY,
    relationship_type TEXT,       -- my_vendor | my_service_provider | inbound_prospect | etc.
    relationship_note TEXT,       -- "my business broker", "payroll provider"
    suppress_gems BOOLEAN DEFAULT FALSE,  -- hard block from gem detection
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'manual'  -- manual | auto_detected | learned
);
```

CLI:
```bash
# Manually tag relationships
gemsieve relationship --sender unicorncapital.io --type my_service_provider --note "business broker"
gemsieve relationship --sender rippling.com --type my_vendor --note "PEO/payroll"
gemsieve relationship --sender stripe.com --suppress  # never score this

# Auto-detect relationships from signals
gemsieve relationships --auto-detect

# List all
gemsieve relationships --list
gemsieve relationships --list --type my_vendor

# Bulk import from a file
gemsieve relationships --import relationships.yaml
```

Web admin: Add a "Relationships" CRUD view + a "Tag Relationship" button on sender profiles.

**The auto-detect command runs the relationship detection signals above and proposes classifications, which the user confirms or rejects.** This creates a feedback loop: the first run surfaces likely vendors, the user confirms, and future runs exclude them automatically.

---

### Revised Gem Detection Pipeline

```
BEFORE (current):
  Profile → Detect all gem types → Score → Rank

AFTER (proposed):
  Profile → Classify Relationship → Filter → Detect gems → Context-aware Score → Rank
                                       ↓
                              Suppress: my_vendor,
                              my_service_provider,
                              my_infrastructure,
                              institutional,
                              selling_to_me (for most gem types)
```

#### Gem Type Eligibility by Relationship Type

Not every gem type should fire for every relationship type:

| Gem Type | my_vendor | my_service_provider | infrastructure | selling_to_me | inbound_prospect | warm_contact | potential_partner | community |
|----------|-----------|--------------------|----|---|---|---|---|---|
| dormant_warm_thread | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| unanswered_ask | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| weak_marketing_lead | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| partner_program | ✅* | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| renewal_leverage | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| vendor_upsell | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| distribution_channel | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| co_marketing | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| industry_intel | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| procurement_signal | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |

`✅*` = partner_program for my_vendor is valid (you already use their product, joining their partner program makes sense) but should score lower than for a warm_contact.

**Key change:** `dormant_warm_thread` — the highest-volume gem type — is now BLOCKED for vendors, service providers, infrastructure, and cold outreach senders. This single filter would have eliminated 7 of the 10 false positives in the screenshot.

#### vendor_upsell Elimination

`vendor_upsell` is removed entirely. The rationale:

- "A vendor is pitching you upgrades" is NOT a revenue opportunity for the user
- It was designed as "they value your business" signal, but in practice it just means "they want more of your money"
- Any legitimate signal from vendor_upsell (negotiation leverage) is already captured by `renewal_leverage`

---

### Revised Scoring Formula

The scoring formula needs three major changes:

1. **Relationship multiplier** — relationship type gates the maximum possible score
2. **Reduced diversity bonus** — diversity bonus capped lower and only counts eligible gem types
3. **Inbound signal boost** — new scoring dimension that rewards evidence of inbound interest

```python
# Relationship type caps the maximum achievable score
RELATIONSHIP_SCORE_CAP = {
    'inbound_prospect': 100,    # full score potential
    'warm_contact': 90,
    'potential_partner': 80,
    'community': 50,            # distribution/intel value only
    'unknown': 60,              # benefit of the doubt, but capped
    'selling_to_me': 20,        # only intel value
    'my_vendor': 25,            # only renewal/partner value
    'my_service_provider': 15,  # almost never a gem
    'my_infrastructure': 5,     # effectively suppressed
    'institutional': 5,         # effectively suppressed
}

def opportunity_score(
    profile: SenderProfile,
    gems: list[Gem],
    relationship: RelationshipType,
) -> float:
    score = 0.0

    # Hard suppression
    if relationship.suppress_gems:
        return 0

    cap = RELATIONSHIP_SCORE_CAP[relationship.relationship_type]

    # --- Inbound Signal Score (max 30, NEW) ---

    # Thread initiation: did THEY reach out to you?
    if profile.thread_initiation_ratio is not None:
        they_initiated = 1.0 - profile.thread_initiation_ratio
        score += they_initiated * 15  # 0-15 points

    # User engagement: do you actually reply to them?
    if profile.user_reply_rate is not None and profile.user_reply_rate > 0:
        score += min(profile.user_reply_rate * 15, 15)  # 0-15 points

    # --- Base Profile Score (max 40, reduced from 60) ---

    # Reachability
    if profile.company_size == "small":
        score += 10
    elif profile.company_size == "medium":
        score += 7
    else:
        score += 2

    # Relevance
    if profile.industry in TARGET_INDUSTRIES:
        score += 8
    else:
        score += 2

    # Recency
    days_since_last = (now() - profile.last_contact).days
    if days_since_last <= 30:
        score += 8
    elif days_since_last <= 90:
        score += 4

    # Known contacts with roles
    if profile.known_contacts and any(c.get("role") for c in profile.known_contacts):
        score += 7

    # Monetary signals (only for inbound_prospect / warm_contact)
    if relationship.relationship_type in ('inbound_prospect', 'warm_contact'):
        if profile.monetary_signals:
            score += 7

    # --- Gem Bonus (max 30, reduced from 40) ---

    # Only count gems that passed the eligibility filter
    gem_types_present = set(g.gem_type for g in gems)

    # Diversity bonus reduced and capped at 3 types
    score += min(len(gem_types_present) * 5, 15)

    # Specific gem bonuses (only the high-signal ones)
    if "dormant_warm_thread" in gem_types_present:
        score += 10  # this now only fires for actual prospects
    if "partner_program" in gem_types_present:
        score += 3
    if "procurement_signal" in gem_types_present:
        score += 7   # active buying signal = real opportunity

    # Apply relationship cap
    return min(score, cap)
```

#### New Profile Fields Required

Two new fields on `sender_profiles` to power the inbound signal score:

```sql
ALTER TABLE sender_profiles ADD COLUMN thread_initiation_ratio REAL;
-- % of threads with this sender where the USER sent the first message
-- 1.0 = user always initiates (likely user's vendor)
-- 0.0 = they always initiate (likely inbound prospect or seller)

ALTER TABLE sender_profiles ADD COLUMN user_reply_rate REAL;
-- % of threads where the user participated (replied at least once)
-- High reply rate + they initiated = strong warm relationship
-- Low reply rate + they initiated = probably spam/cold outreach
```

Computed during Stage 5 (profiling):

```python
def _compute_thread_metrics(db, sender_domain):
    """Compute who initiates conversations and user engagement rate."""
    threads = db.execute("""
        SELECT t.thread_id, t.user_participated,
               (SELECT m.is_sent FROM messages m
                WHERE m.thread_id = t.thread_id
                ORDER BY m.date ASC LIMIT 1) as user_started
        FROM threads t
        JOIN messages m2 ON t.thread_id = m2.thread_id
        JOIN parsed_metadata pm ON m2.message_id = pm.message_id
        WHERE pm.sender_domain = ?
        GROUP BY t.thread_id
    """, (sender_domain,)).fetchall()

    if not threads:
        return None, None

    user_started = sum(1 for t in threads if t['user_started'])
    user_participated = sum(1 for t in threads if t['user_participated'])

    initiation_ratio = user_started / len(threads)
    reply_rate = user_participated / len(threads)

    return initiation_ratio, reply_rate
```

---

### Known Entity Suppression List

A configurable file (`known_entities.yaml`) that ships with sensible defaults and can be extended:

```yaml
# known_entities.yaml
# Senders that are categorically NOT gems

infrastructure:
  # Cloud/hosting
  - google.com
  - amazonaws.com
  - heroku.com
  - herokumanager.com
  - digitalocean.com
  - cloudflare.com
  - vercel.com
  - netlify.com
  - render.com
  - railway.app
  # Version control
  - github.com
  - gitlab.com
  - bitbucket.org
  # Payment processing
  - stripe.com
  - paypal.com
  - braintree.com
  - square.com
  # Communication
  - slack.com
  - zoom.us
  - discord.com
  # Dev tools
  - docker.com
  - npmjs.com
  - pypi.org
  - sentry.io
  - datadog.com

institutional:
  # Insurance
  - thehartford.com
  - geico.com
  - progressive.com
  - statefarm.com
  - allstate.com
  - libertymutual.com
  # Banking
  - bankofamerica.com
  - chase.com
  - wellsfargo.com
  - citi.com
  - capitalone.com
  # Payroll / HR
  - adp.com
  - paychex.com
  - gusto.com
  - rippling.com
  - justworks.com
  - trinet.com
  # Accounting
  - intuit.com
  - quickbooks.com
  - xero.com
  - freshbooks.com
  # Government
  - irs.gov
  - ssa.gov

marketing_platforms:
  # These are YOUR tools, not opportunities
  - mailchimp.com
  - hubspot.com
  - salesforce.com
  - activecampaign.com
  - klaviyo.com
  - constantcontact.com
  - convertkit.com
  - sendgrid.com
  - postmarkapp.com

# User can add their own
user_suppressed: []
```

At ingestion/profiling time:
```python
def is_known_non_gem(domain: str, known_entities: dict) -> str | None:
    """Check if domain is a known non-gem. Returns category or None."""
    collapsed = collapse_subdomain(domain)
    for category, domains in known_entities.items():
        if collapsed in domains:
            return category
    return None
```

---

### Dormant Warm Thread: Tightened Detection

The biggest single improvement. Current detection is too permissive. New rules:

```python
def _detect_dormant_warm_thread_v2(db, thread, profile, relationship):
    """Detect dormant warm threads. V2: relationship-aware, stricter signals."""

    # GATE 1: Relationship must be eligible
    if relationship.relationship_type not in (
        'inbound_prospect', 'warm_contact', 'potential_partner', 'unknown'
    ):
        return []

    # GATE 2: Basic dormancy check (unchanged)
    if thread['awaiting_response_from'] != 'user':
        return []
    if thread['days_dormant'] < config.dormant_thread.min_dormancy_days:
        return []

    # GATE 3: User must have participated in this thread at some point
    # (filters out one-way vendor emails / newsletters)
    if not thread['user_participated']:
        return []

    # GATE 4: Thread must have genuine back-and-forth
    # (filters out "they sent 3 emails, I never replied")
    if thread['message_count'] < 2:
        return []

    # GATE 5: The OTHER party must have sent a substantive message
    # (not just auto-replies, receipts, or confirmations)
    # Use warm signal detection from Phase 2
    signals, score_boost = _scan_warm_signals(db, thread['thread_id'])
    if not signals:
        return []  # no warm signals = not a gem

    # GATE 6: Check that the thread isn't a completed engagement
    completed_signals = _scan_completion_signals(db, thread['thread_id'])
    if completed_signals:
        return []

    # Only threads that pass ALL 6 gates become gems
    # ...rest of gem creation logic...


COMPLETION_SIGNALS = [
    r'(?i)\bfinal.*(?:deliverable|version|report|invoice)\b',
    r'(?i)\bproject.*(?:complete|finished|wrapped|closed)\b',
    r'(?i)\bthank.*(?:for everything|for your work|for the help)\b',
    r'(?i)\bgreat working with you\b',
    r'(?i)\bcontract.*(?:ended|expired|terminated|concluded)\b',
    r'(?i)\bengagement.*(?:complete|concluded|wrapped)\b',
    r'(?i)\bclosing.*(?:out|this|the project)\b',
    r'(?i)\ball set\b.*\bthanks\b',
]

def _scan_completion_signals(db, thread_id):
    """Detect signals that a thread represents a completed engagement."""
    # Check last 3 messages in thread for completion language
    messages = db.execute("""
        SELECT COALESCE(pc.body_clean, m.body_text, '') as text
        FROM messages m
        LEFT JOIN parsed_content pc ON m.message_id = pc.message_id
        WHERE m.thread_id = ?
        ORDER BY m.date DESC LIMIT 3
    """, (thread_id,)).fetchall()

    text = ' '.join(m['text'] for m in messages)
    found = []
    for pattern in COMPLETION_SIGNALS:
        match = re.search(pattern, text)
        if match:
            found.append(match.group(0).strip()[:100])
    return found
```

---

### Implementation Plan

#### Database Changes

```sql
-- New table: sender relationships
CREATE TABLE sender_relationships (
    sender_domain TEXT PRIMARY KEY,
    relationship_type TEXT NOT NULL,
    relationship_note TEXT,
    suppress_gems BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'manual'
);

-- New columns on sender_profiles
ALTER TABLE sender_profiles ADD COLUMN thread_initiation_ratio REAL;
ALTER TABLE sender_profiles ADD COLUMN user_reply_rate REAL;

-- New column on parsed_metadata for original subdomain
ALTER TABLE parsed_metadata ADD COLUMN sender_subdomain TEXT;
```

#### New/Modified Files

| File | Change | Effort |
|------|--------|--------|
| `stages/relationships.py` | **NEW** — Relationship detection engine | Medium |
| `stages/profile.py` | Add `_compute_thread_metrics()`, store on profiles | Small |
| `stages/profile.py` | All `_detect_*` functions: accept relationship, check eligibility matrix | Medium |
| `stages/profile.py` | `_detect_dormant_warm_thread()`: implement v2 with 6 gates | Medium |
| `stages/profile.py` | Remove `vendor_upsell` detection entirely | Small |
| `stages/segment.py` | Scoring formula rewrite with relationship multiplier | Medium |
| `stages/metadata.py` | Subdomain collapsing via tldextract | Small |
| `cli.py` | Add `relationship` command group | Small |
| `models.py` | Add `RelationshipType` enum, `SenderRelationship` dataclass | Small |
| `schema.sql` | New table + altered columns | Small |
| `config.py` | Add `known_entities_file` config | Small |
| `known_entities.yaml` | **NEW** — default suppression list | Small |
| `web/models.py` | Add SenderRelationship ORM model | Small |
| `web/admin.py` | Add Relationships view | Small |
| `database.py` | Migration for new table + columns | Small |
| `pyproject.toml` | Add `tldextract` dependency | Trivial |

#### CLI Additions

```bash
# Relationship management
gemsieve relationship --sender unicorncapital.io --type my_service_provider --note "business broker"
gemsieve relationship --sender stripe.com --suppress
gemsieve relationships --list
gemsieve relationships --list --type my_vendor
gemsieve relationships --auto-detect          # propose relationships from signals
gemsieve relationships --auto-detect --apply  # auto-apply high-confidence detections
gemsieve relationships --import relationships.yaml

# Updated pipeline
gemsieve run --all-stages   # now includes relationship detection before gem scoring
```

#### Migration Path

For existing databases:
1. Run `gemsieve db --migrate` to add new table and columns
2. Run `gemsieve relationships --auto-detect` to bootstrap relationship classifications
3. User reviews and corrects proposed relationships
4. Re-run `gemsieve profile` and `gemsieve gems` — results should dramatically improve

---

### Expected Impact on the Screenshot Results

After Phase 3, the same inbox should produce:

| Sender | Before | After | Reason |
|--------|--------|-------|--------|
| unicorncapital.io | #1 (~870) | Suppressed (0) | auto-detect: my_service_provider (user initiated threads, onboarding language) |
| ruskinconsulting.com | #2 (~850) | Suppressed (0) | auto-detect: my_service_provider (user initiated, high engagement) |
| rosenblattlawfirm.com | #3 (~280) | Suppressed (0) | auto-detect: my_service_provider (user initiated) |
| stripe.com | #4 (~260) | Suppressed (0) | known_entities.yaml: infrastructure |
| mail.service.thehartford.com | #5 (~200) | Suppressed (0) | known_entities.yaml: institutional (after subdomain collapse to thehartford.com) |
| notification.intuit.com | #6 (~180) | Suppressed (0) | known_entities.yaml: institutional (after subdomain collapse to intuit.com) |
| google.com | #7 (~170) | Suppressed (0) | known_entities.yaml: infrastructure |
| findmyitpartner.com | #8 (~150) | Top 3 (~75) | inbound_prospect or unknown, passes all gates |
| rippling.com | #9 (~140) | Suppressed (0) | known_entities.yaml: institutional |
| herokumanager.com | #10 (~130) | Suppressed (0) | known_entities.yaml: infrastructure |

**Predicted precision improvement: 10% → 80%+ (findmyitpartner.com and other previously-buried real prospects surface to the top)**

---

### Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Top-10 gem precision (% actually actionable) | 10% | >70% |
| Known vendor false positive rate | ~70% of top gems | <5% |
| Infrastructure/institutional noise | ~30% of top gems | 0% |
| Real inbound prospects in top 10 | 1 | 5+ |
| Dormant warm thread false positive rate | ~80% | <20% |
| User relationship tagging effort (first run) | N/A | <10 min for top 50 senders |
| Auto-detect relationship accuracy | N/A | >75% for vendor classification |

---

### Dependencies

| Package | Purpose |
|---------|---------|
| `tldextract` | Subdomain collapsing (registered domain extraction) |

No other new dependencies required.