"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import yaml

from gemsieve.config import Config, load_config


def test_default_config():
    """Default config has sensible defaults."""
    config = Config()
    assert config.gmail.credentials_file == "credentials.json"
    assert config.storage.sqlite_path == "gemsieve.db"
    assert config.ai.provider == "ollama"
    assert config.ai.batch_size == 10
    assert "SaaS" in config.scoring.target_industries


def test_load_missing_config_uses_defaults():
    """Loading with no config file returns defaults."""
    config = load_config()
    assert isinstance(config, Config)
    assert config.gmail.default_query == "newer_than:1y"


def test_load_config_from_yaml(monkeypatch, tmp_path):
    """Loading from a YAML file merges with defaults."""
    # Isolate from .env overrides
    monkeypatch.delenv("model_name", raising=False)
    monkeypatch.delenv("ollama_host", raising=False)
    monkeypatch.delenv("ollama_api_key", raising=False)
    monkeypatch.chdir(tmp_path)

    data = {
        "gmail": {"default_query": "newer_than:30d"},
        "ai": {"model": "llama3"},
    }

    config_file = tmp_path / "test_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(data, f)

    config = load_config(str(config_file))

    assert config.gmail.default_query == "newer_than:30d"
    assert config.ai.model == "llama3"
    # Defaults still work
    assert config.storage.sqlite_path == "gemsieve.db"


def test_scoring_config_defaults():
    """Scoring config has correct default weights."""
    config = Config()
    assert config.scoring.weights.reachability == 10
    assert config.scoring.weights.gem_diversity_cap == 15
    assert config.scoring.weights.inbound_initiation == 15
    assert config.scoring.dormant_thread.min_dormancy_days == 14
    assert config.scoring.relationship_caps.my_vendor == 25
