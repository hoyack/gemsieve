"""Stage 2: HTML parsing, signature stripping, offer/CTA extraction."""

from __future__ import annotations

import json
import re
import sqlite3
from urllib.parse import parse_qs, urlparse


def parse_content(db: sqlite3.Connection) -> int:
    """Parse body content for all unprocessed messages.

    Returns count of messages processed.
    """
    rows = db.execute(
        """SELECT m.message_id, m.body_html, m.body_text
           FROM messages m
           LEFT JOIN parsed_content pc ON m.message_id = pc.message_id
           WHERE pc.message_id IS NULL"""
    ).fetchall()

    processed = 0
    for row in rows:
        result = _parse_single_message(row["body_html"], row["body_text"])

        db.execute(
            """INSERT OR REPLACE INTO parsed_content
               (message_id, body_clean, signature_block, primary_headline,
                cta_texts, offer_types, has_personalization, personalization_tokens,
                link_count, tracking_pixel_count, unique_link_domains, link_intents,
                utm_campaigns, has_physical_address, physical_address_text,
                social_links, image_count, template_complexity_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["message_id"],
                result["body_clean"],
                result["signature_block"],
                result["primary_headline"],
                json.dumps(result["cta_texts"]),
                json.dumps(result["offer_types"]),
                result["has_personalization"],
                json.dumps(result["personalization_tokens"]),
                result["link_count"],
                result["tracking_pixel_count"],
                json.dumps(result["unique_link_domains"]),
                json.dumps(result["link_intents"]),
                json.dumps(result["utm_campaigns"]),
                result["has_physical_address"],
                result["physical_address_text"],
                json.dumps(result["social_links"]),
                result["image_count"],
                result["template_complexity_score"],
            ),
        )
        processed += 1

    db.commit()
    return processed


def _parse_single_message(body_html: str | None, body_text: str | None) -> dict:
    """Parse a single message body, returning structured content data."""
    from bs4 import BeautifulSoup

    result = {
        "body_clean": "",
        "signature_block": None,
        "primary_headline": None,
        "cta_texts": [],
        "offer_types": [],
        "has_personalization": False,
        "personalization_tokens": [],
        "link_count": 0,
        "tracking_pixel_count": 0,
        "unique_link_domains": [],
        "link_intents": {},
        "utm_campaigns": [],
        "has_physical_address": False,
        "physical_address_text": None,
        "social_links": {},
        "image_count": 0,
        "template_complexity_score": 0,
    }

    if not body_html and not body_text:
        return result

    # Parse HTML if available
    if body_html:
        soup = BeautifulSoup(body_html, "lxml")

        # Remove script/style tags
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()

        # Count images and detect tracking pixels
        images = soup.find_all("img")
        result["image_count"] = len(images)
        tracking_pixels = 0
        for img in images:
            width = img.get("width", "")
            height = img.get("height", "")
            if str(width) in ("1", "0") or str(height) in ("1", "0"):
                tracking_pixels += 1
                img.decompose()
        result["tracking_pixel_count"] = tracking_pixels

        # Extract links
        links = soup.find_all("a", href=True)
        all_urls = [a["href"] for a in links if a["href"].startswith(("http", "https"))]
        result["link_count"] = len(all_urls)

        # Unique link domains
        link_domains = set()
        for url in all_urls:
            try:
                domain = urlparse(url).netloc
                if domain:
                    link_domains.add(domain)
            except Exception:
                pass
        result["unique_link_domains"] = sorted(link_domains)

        # UTM campaign extraction
        utm_data = []
        for url in all_urls:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                utm = {}
                for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content"):
                    if key in params:
                        utm[key] = params[key][0]
                if utm:
                    utm_data.append(utm)
            except Exception:
                pass
        result["utm_campaigns"] = utm_data

        # Link intent classification
        link_intents: dict[str, list[str]] = {}
        intent_signals = {
            "pricing_page": ["pricing", "plans", "packages", "/pricing", "cost"],
            "demo_booking": ["demo", "book-a-call", "calendly", "schedule"],
            "partner_program": ["partner", "affiliate", "referral", "reseller", "/partners"],
            "marketplace_listing": ["marketplace", "app-store", "integrations", "/apps"],
            "job_posting": ["careers", "jobs", "hiring", "we-re-hiring", "/jobs"],
            "case_study": ["case-study", "customer-story", "success-story"],
            "free_tool": ["free-tool", "calculator", "generator", "template"],
        }
        for url in all_urls:
            url_lower = url.lower()
            for intent, signals in intent_signals.items():
                if any(s in url_lower for s in signals):
                    link_intents.setdefault(intent, []).append(url)
        result["link_intents"] = link_intents

        # Extract CTA texts (buttons and prominent links)
        cta_texts = []
        for a in links:
            # Look for button-like styling or classes
            classes = " ".join(a.get("class", []))
            style = a.get("style", "")
            text = a.get_text(strip=True)
            if not text:
                continue
            is_cta = (
                "button" in classes.lower()
                or "btn" in classes.lower()
                or "cta" in classes.lower()
                or "background-color" in style
                or "background:" in style
            )
            if is_cta and len(text) < 80:
                cta_texts.append(text)
        # Also look for actual <button> tags
        for btn in soup.find_all("button"):
            text = btn.get_text(strip=True)
            if text and len(text) < 80:
                cta_texts.append(text)
        result["cta_texts"] = list(dict.fromkeys(cta_texts))  # dedupe preserving order

        # Extract primary headline
        for tag in ("h1", "h2"):
            heading = soup.find(tag)
            if heading:
                result["primary_headline"] = heading.get_text(strip=True)
                break

        # Social links
        social_patterns = {
            "twitter": r"(?:twitter\.com|x\.com)/",
            "linkedin": r"linkedin\.com/",
            "facebook": r"facebook\.com/",
            "instagram": r"instagram\.com/",
            "youtube": r"youtube\.com/",
        }
        for url in all_urls:
            for platform, pattern in social_patterns.items():
                if platform not in result["social_links"] and re.search(pattern, url):
                    result["social_links"][platform] = url

        # Template complexity score
        score = 0
        tables = soup.find_all("table")
        score += min(len(tables) * 5, 25)
        # Inline styles
        styled = soup.find_all(style=True)
        score += min(len(styled) * 2, 20)
        # Media queries in style tags (already removed but check original)
        if body_html and "@media" in body_html:
            score += 15
        # Images
        score += min(result["image_count"] * 3, 15)
        # Links
        score += min(result["link_count"] * 2, 15)
        # Personalization tokens
        score += 10 if result["has_personalization"] else 0
        result["template_complexity_score"] = min(score, 100)

        # Detect personalization tokens
        personalization_patterns = [
            r"%%[A-Z_]+%%",        # ESP tokens
            r"\{\{[^}]+\}\}",       # Handlebars
            r"\*\|[A-Z_]+\|\*",    # Mailchimp merge tags
        ]
        tokens = []
        html_str = str(soup)
        for pattern in personalization_patterns:
            matches = re.findall(pattern, html_str)
            tokens.extend(matches)
        if tokens:
            result["has_personalization"] = True
            result["personalization_tokens"] = list(set(tokens))

        # Extract full text for body_clean
        full_text = soup.get_text(separator="\n")
    else:
        full_text = body_text or ""

    # Strip signatures and quotes from text
    body_clean, signature_block = _strip_signature_and_quotes(full_text)
    result["body_clean"] = body_clean.strip()
    result["signature_block"] = signature_block

    # Detect offers via regex
    result["offer_types"] = _detect_offers(result["body_clean"])

    # Detect physical address
    address_match = re.search(
        r"\d{1,5}\s+[\w\s]+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Way|Court|Ct)"
        r"[,.\s]+[\w\s]+[,.\s]+[A-Z]{2}\s+\d{5}",
        result["body_clean"],
    )
    if address_match:
        result["has_physical_address"] = True
        result["physical_address_text"] = address_match.group(0).strip()

    return result


def _strip_signature_and_quotes(text: str) -> tuple[str, str | None]:
    """Strip quoted replies and signatures from email text.

    Returns (clean_body, signature_block).
    """
    lines = text.split("\n")
    clean_lines = []
    signature_block = None
    sig_start = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect quoted reply markers
        if re.match(r"^On\s+.+wrote:\s*$", stripped):
            # Everything after this is quoted reply
            break

        if stripped.startswith(">"):
            continue

        # Detect Gmail quote div (text extraction would show content after marker)
        if "gmail_quote" in stripped:
            break

        # Detect signature delimiters
        if stripped in ("--", "-- ", "—"):
            sig_start = i
            break

        # Heuristic: common sign-off phrases
        if re.match(
            r"^(Best regards|Kind regards|Regards|Thanks|Thank you|Cheers|Sincerely|"
            r"Best|Warm regards|All the best|Sent from my iPhone|Sent from my iPad|"
            r"Get Outlook for),?\s*$",
            stripped,
            re.IGNORECASE,
        ):
            sig_start = i
            break

        clean_lines.append(line)

    if sig_start is not None:
        sig_lines = lines[sig_start:]
        signature_block = "\n".join(sig_lines).strip()

    return "\n".join(clean_lines), signature_block


# Offer detection patterns from spec section 5.3
OFFER_PATTERNS: dict[str, list[str]] = {
    "discount": [r"\d+%\s*off", r"\$\d+\s*off", r"save\s+\$?\d+", r"coupon", r"promo code"],
    "free_trial": [r"free trial", r"try free", r"start free", r"\d+[- ]day trial"],
    "webinar": [r"webinar", r"live demo", r"register now", r"join us live"],
    "product_launch": [r"just launched", r"introducing", r"now available", r"new release", r"announcing"],
    "urgency": [r"limited time", r"expires", r"last chance", r"ends tonight", r"only \d+ left"],
    "social_proof": [r"trusted by", r"join \d+", r"\d+ customers", r"as seen in", r"rated \d"],
    "event": [r"conference", r"summit", r"meetup", r"workshop"],
    "newsletter": [r"this week in", r"weekly digest", r"roundup", r"top stories"],
    "renewal": [
        r"renewal", r"subscription renew", r"upcoming charge", r"plan expires",
        r"auto-renew", r"billing cycle", r"annual renewal",
    ],
    "partnership": [
        r"partner program", r"affiliate", r"referral program", r"reseller",
        r"become a partner", r"earn commission", r"revenue share",
    ],
    "procurement": [
        r"security review", r"vendor assessment", r"SOC 2", r"compliance",
        r"data processing agreement", r"DPA", r"MSA", r"terms of service update",
    ],
}


def _detect_offers(text: str) -> list[str]:
    """Detect offer types in text using regex patterns."""
    detected = []
    text_lower = text.lower()
    for offer_type, patterns in OFFER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                detected.append(offer_type)
                break
    return detected
