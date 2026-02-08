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

ENGAGEMENT_PROMPT = """You are generating a personalized engagement message.

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
