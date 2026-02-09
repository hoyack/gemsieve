"""Tests for known entity loading and matching."""

from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from gemsieve.known_entities import is_known_entity, load_known_entities


class TestLoadKnownEntities:
    def test_load_from_file(self, tmp_path):
        data = {
            "infrastructure": ["google.com", "stripe.com"],
            "institutional": ["intuit.com"],
        }
        f = tmp_path / "entities.yaml"
        f.write_text(yaml.dump(data))

        result = load_known_entities(str(f))
        assert "infrastructure" in result
        assert "google.com" in result["infrastructure"]
        assert "stripe.com" in result["infrastructure"]
        assert "intuit.com" in result["institutional"]

    def test_missing_file_returns_empty(self):
        result = load_known_entities("/nonexistent/path/entities.yaml")
        assert result == {}

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")

        result = load_known_entities(str(f))
        assert result == {}


class TestIsKnownEntity:
    @pytest.fixture
    def entities(self):
        return {
            "infrastructure": ["google.com", "stripe.com"],
            "institutional": ["intuit.com", "rippling.com"],
            "marketing_platforms": ["hubspot.com"],
        }

    def test_direct_match(self, entities):
        assert is_known_entity("stripe.com", entities) == "infrastructure"

    def test_subdomain_match(self, entities):
        """notification.intuit.com should match intuit.com via collapse_subdomain."""
        assert is_known_entity("notification.intuit.com", entities) == "institutional"

    def test_nested_subdomain_match(self, entities):
        assert is_known_entity("mail.service.google.com", entities) == "infrastructure"

    def test_unknown_domain(self, entities):
        assert is_known_entity("randomstartup.io", entities) is None

    def test_empty_domain(self, entities):
        assert is_known_entity("", entities) is None

    def test_empty_entities(self):
        assert is_known_entity("google.com", {}) is None
