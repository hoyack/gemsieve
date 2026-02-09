"""Known entity loading and matching for relationship detection."""

from __future__ import annotations

from pathlib import Path

import yaml

from gemsieve.stages.metadata import collapse_subdomain


def load_known_entities(path: str | None = None) -> dict[str, list[str]]:
    """Load known entity suppression lists from YAML file.

    Returns a dict mapping category -> list of domains.
    Gracefully returns empty dict if file not found.
    """
    if path is None:
        path = "known_entities.yaml"

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

    # Normalize: ensure all values are lists of strings
    result: dict[str, list[str]] = {}
    for category, domains in data.items():
        if isinstance(domains, list):
            result[category] = [str(d) for d in domains]
        else:
            result[category] = []

    return result


def is_known_entity(domain: str, known_entities: dict[str, list[str]]) -> str | None:
    """Check if a domain matches any known entity category.

    Uses collapse_subdomain() internally for subdomain-aware matching.

    Returns the category name if matched, None otherwise.
    """
    if not domain or not known_entities:
        return None

    collapsed = collapse_subdomain(domain)

    for category, domains in known_entities.items():
        if collapsed in domains or domain in domains:
            return category

    return None
