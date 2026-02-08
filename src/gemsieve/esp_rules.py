"""ESP fingerprint rule loader and matcher."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def load_esp_rules(rules_path: str | Path) -> dict:
    """Load ESP fingerprinting rules from YAML file."""
    path = Path(rules_path)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def match_esp(headers: dict[str, list[str]], sender_domain: str, rules: dict) -> tuple[str | None, str | None]:
    """Match email headers against ESP fingerprint rules.

    Args:
        headers: dict of header_name -> list of values (all lowercase keys)
        sender_domain: the sender's domain
        rules: loaded ESP rules dict

    Returns:
        (esp_name, confidence) or (None, None) if no match
    """
    def get_header_values(name: str) -> list[str]:
        """Get all values for a header name (case-insensitive)."""
        return headers.get(name.lower(), [])

    def get_header_str(name: str) -> str:
        vals = get_header_values(name)
        return " ".join(vals).lower() if vals else ""

    best_match = None
    best_score = 0

    for esp_name, esp_config in rules.items():
        if esp_name == "custom_smtp":
            continue  # Handle as fallback

        signals = esp_config.get("signals", [])
        confidence = esp_config.get("confidence", "low")
        score = 0

        for signal in signals:
            if isinstance(signal, dict):
                for signal_type, signal_value in signal.items():
                    if signal_type == "return_path_contains":
                        return_path = get_header_str("return-path")
                        if signal_value.lower() in return_path:
                            score += 1

                    elif signal_type == "dkim_domain":
                        dkim_sig = get_header_str("dkim-signature")
                        if f"d={signal_value}" in dkim_sig:
                            score += 1

                    elif signal_type == "header_present":
                        if get_header_values(signal_value.lower()):
                            score += 1

                    elif signal_type == "x_mailer_contains":
                        x_mailer = get_header_str("x-mailer")
                        if signal_value.lower() in x_mailer:
                            score += 1

                    elif signal_type == "tracking_domain":
                        # Check received headers and any link references
                        all_headers_str = json.dumps(headers).lower()
                        if signal_value.lower() in all_headers_str:
                            score += 1

        if score > 0 and score > best_score:
            best_match = esp_name
            best_score = score

    if best_match:
        return best_match, rules[best_match].get("confidence", "medium")

    # Check for custom SMTP fallback
    if "custom_smtp" in rules:
        # If DKIM domain matches sender domain, it's likely custom SMTP
        dkim_sig = get_header_str("dkim-signature")
        if f"d={sender_domain}" in dkim_sig:
            return "custom_smtp", "low"

    return None, None
