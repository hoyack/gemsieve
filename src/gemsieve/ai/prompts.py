"""All prompt templates for AI classification and engagement generation."""

CLASSIFICATION_PROMPT = """You are analyzing an email to build an intelligence profile on the sender.

SENDER: {from_name} <{from_address}>
SUBJECT: {subject}
ESP: {esp_identified}
INTENT SIGNALS: {offer_types}, CTAs: {cta_texts}
ENTITIES FOUND: {extracted_entities_summary}
BODY (first 2000 chars):
{body_clean}

Classify this sender. Respond in JSON only:
{{
  "industry": "one of: SaaS, E-commerce, Agency, Financial Services, Healthcare, Education, Real Estate, Media, Food & Beverage, Travel, Nonprofit, Developer Tools, Marketing, HR, Crypto, Local Business, Other",
  "company_size_estimate": "small | medium | enterprise",
  "marketing_sophistication": 1-10,
  "sender_intent": "one of: human_1to1, cold_outreach, nurture_sequence, newsletter, transactional, promotional, event_invitation, partnership_pitch, re_engagement, procurement, recruiting, community",
  "product_type": "one of: Physical product, Digital product, SaaS subscription, Professional service, Course, Event tickets, Membership, Free tool, Marketplace listing",
  "product_description": "one sentence describing what they sell or offer",
  "pain_points_addressed": ["list of problems their product solves"],
  "target_audience": "who they are selling to",
  "partner_program_detected": true or false,
  "renewal_signal_detected": true or false,
  "confidence": 0.0 to 1.0
}}"""

DEFAULT_ENGAGEMENT_PROMPT = """You are generating a personalized engagement message.

STRATEGY: {strategy_name}
GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Size: {company_size}
  ESP: {esp_used}
  Marketing Score: {sophistication}/10
  They sell: {product_description}
  Their pain points: {pain_points}
  Specific observation: {observation}
  Relationship context: {relationship_summary}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write a short engagement message (under 150 words) that:
1. Opens with a specific, non-generic hook referencing real context from the gem
2. Demonstrates insight they'd find valuable (not just flattery)
3. Connects to the specific opportunity this gem represents
4. Ends with a low-friction CTA appropriate to the gem type
5. Addresses {contact_name} by name if available

Do not be sycophantic. Be direct and specific. Sound like a peer, not a vendor.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}"""

# Backward compat alias
ENGAGEMENT_PROMPT = DEFAULT_ENGAGEMENT_PROMPT


STRATEGY_PROMPTS = {
    "audit": """You are writing an "I Audited Your Funnel" consultative outreach email.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Size: {company_size}
  ESP: {esp_used}
  Marketing Score: {sophistication}/10
  They sell: {product_description}
  Their pain points: {pain_points}
  Specific observation: {observation}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}
MY AUDIENCE: {user_audience}

Write a short (under 150 words) consultative outreach email that:
1. Opens by referencing a specific, real gap you found in their marketing (low sophistication score, missing UTM, weak CTA, etc.)
2. Provides ONE concrete, actionable insight they can use immediately — not generic advice
3. Positions you as a peer who noticed something, not a vendor pitching
4. Ends with a low-friction CTA: "Happy to share the full audit notes if helpful"
5. Addresses {contact_name} by name if available

Tone: helpful expert, not salesy. Be specific about what you observed.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",

    "revival": """You are writing a thread revival follow-up email.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

THREAD CONTEXT:
  Subject: {thread_subject}
  Dormancy: {dormancy_days} days since last activity

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Relationship context: {relationship_summary}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write a short (under 120 words) thread revival email that:
1. References the original thread naturally — don't say "I noticed we lost touch"
2. Adds NEW value: a relevant insight, resource, or development since you last spoke
3. Acknowledges the time gap without apologizing excessively
4. Ends with a specific, easy-to-answer question (not "let's catch up")
5. Addresses {contact_name} by name if available

Tone: warm but professional. Sound like you just thought of them, not like a CRM triggered this.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",

    "partner": """You are writing a partner program application or inquiry email.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Partner URLs: {partner_urls}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}
MY AUDIENCE: {user_audience}

Write a short (under 150 words) partner program inquiry email that:
1. References their specific partner/affiliate program by name if possible
2. Explains concretely how YOUR audience overlaps with theirs
3. Quantifies your reach if possible (audience size, engagement metrics)
4. Proposes a specific collaboration format (referral, integration, co-content)
5. Addresses {contact_name} by name if available

Tone: business-like and specific. Show you've done your homework on their program.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",

    "renewal_negotiation": """You are writing a data-driven renewal negotiation email.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RENEWAL CONTEXT:
  Renewal dates: {renewal_dates}
  Monetary signals: {monetary_signals}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Relationship context: {relationship_summary}

MY TONE: {user_preferred_tone}

Write a short (under 120 words) renewal negotiation email that:
1. References the upcoming renewal date specifically
2. Cites concrete usage data or value received (from gem explanation)
3. Requests a meeting to discuss terms — frame as mutual review, not adversarial
4. Mentions you've been evaluating alternatives (without naming them)
5. Addresses {contact_name} or "the account team" appropriately

Tone: respectful but firm. You're a valued customer exploring options, not threatening to leave.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",

    "industry_report": """You are writing a content-led engagement invitation email.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  They sell: {product_description}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write a short (under 130 words) engagement email that:
1. References a specific trend or data point relevant to their industry
2. Mentions a piece of content you're creating (report, analysis, case study)
3. Invites them to contribute a perspective or be featured
4. Explains the mutual benefit: their expertise + your distribution
5. Addresses {contact_name} by name if available

Tone: collaborative. You're building something valuable and they can be part of it.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",

    "mirror": """You are writing a mirror-match style-matching email.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Size: {company_size}
  ESP: {esp_used}
  Marketing Score: {sophistication}/10
  Their CTAs: {observation}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}

Write a short (under 130 words) engagement email that:
1. Mirrors their communication style — match their level of formality and directness
2. References something SPECIFIC from their emails you've received (an offer, a CTA, a campaign)
3. Proposes a value exchange: something you can offer in return for what you want
4. Keeps the CTA proportional to the relationship stage
5. Addresses {contact_name} by name if available

Tone: match theirs. If they're casual, be casual. If formal, be formal.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",

    "distribution_pitch": """You are writing a pitch to get featured in a newsletter, podcast, or event.

GEM TYPE: {gem_type}
GEM EXPLANATION: {gem_explanation_json}

RECIPIENT PROFILE:
  Company: {company_name}
  Contact: {contact_name}, {contact_role}
  Industry: {industry}
  Target audience: {target_audience}

MY SERVICES: {user_service_description}
MY TONE: {user_preferred_tone}
MY AUDIENCE: {user_audience}

Write a short (under 150 words) pitch email that:
1. References their specific publication/newsletter/podcast by name
2. Proposes a concrete topic or angle relevant to their audience
3. Explains why YOUR perspective adds unique value to their content
4. Offers social proof (expertise, audience overlap, previous features)
5. Makes the ask specific: guest post, interview, sponsorship, speaking slot
6. Addresses {contact_name} by name if available

Tone: professional and specific. You're pitching, not begging.

Respond in JSON:
{{
  "subject_line": "email subject",
  "body": "the email body text"
}}""",
}
