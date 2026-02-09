"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class GmailConfig:
    credentials_file: str = "credentials.json"
    token_file: str = "token.json"
    default_query: str = "newer_than:1y"


@dataclass
class StorageConfig:
    backend: str = "sqlite"
    sqlite_path: str = "gemsieve.db"


@dataclass
class AIConfig:
    provider: str = "ollama"
    model: str = "mistral-nemo"
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""
    batch_size: int = 10
    max_body_chars: int = 2000

    def to_provider_dict(self) -> dict:
        """Return a dict suitable for passing to get_provider()."""
        return {
            "ollama_base_url": self.ollama_base_url,
            "ollama_api_key": self.ollama_api_key,
        }


@dataclass
class EntityConfig:
    backend: str = "spacy"
    spacy_model: str = "en_core_web_sm"
    extract_monetary: bool = True
    extract_dates: bool = True
    extract_procurement: bool = True


@dataclass
class ScoringWeights:
    # Inbound signal (max 30)
    inbound_initiation: int = 15
    inbound_engagement: int = 15
    # Base profile (max 40)
    reachability: int = 10
    relevance: int = 8
    recency: int = 8
    known_contacts: int = 7
    monetary_signals: int = 7
    # Gem bonus (max 30)
    gem_diversity_per_type: int = 5
    gem_diversity_cap: int = 15
    dormant_thread_bonus: int = 10
    partner_bonus: int = 3
    procurement_bonus: int = 7


@dataclass
class RelationshipScoreCaps:
    inbound_prospect: int = 100
    warm_contact: int = 90
    potential_partner: int = 80
    community: int = 50
    unknown: int = 60
    selling_to_me: int = 20
    my_vendor: int = 25
    my_service_provider: int = 15
    my_infrastructure: int = 5
    institutional: int = 5


@dataclass
class DormantThreadConfig:
    min_dormancy_days: int = 14
    max_dormancy_days: int = 365
    require_human_sender: bool = True


@dataclass
class ScoringConfig:
    target_industries: list[str] = field(default_factory=lambda: [
        "SaaS", "Agency", "E-commerce", "Marketing", "Developer Tools",
    ])
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    dormant_thread: DormantThreadConfig = field(default_factory=DormantThreadConfig)
    relationship_caps: RelationshipScoreCaps = field(default_factory=RelationshipScoreCaps)


@dataclass
class EngagementConfig:
    your_name: str = ""
    your_service: str = ""
    your_tone: str = "direct, technical, peer-to-peer"
    your_audience: str = ""
    preferred_strategies: list[str] = field(default_factory=lambda: [
        "audit", "mirror", "revival", "partner",
    ])
    max_outreach_per_day: int = 20


@dataclass
class Config:
    gmail: GmailConfig = field(default_factory=GmailConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    entity_extraction: EntityConfig = field(default_factory=EntityConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    esp_fingerprints_file: str = "esp_rules.yaml"
    custom_segments_file: str = "segments.yaml"
    known_entities_file: str = "known_entities.yaml"


def _merge_dict(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_config(data: dict) -> Config:
    """Convert a raw dict to a Config dataclass, handling nested structures."""
    from dacite import from_dict

    return from_dict(data_class=Config, data=data)


def _find_config_file() -> Path | None:
    """Search for config file in standard locations."""
    # 1. Environment variable
    env_path = os.environ.get("GEMSIEVE_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2. Current directory
    local = Path("config.yaml")
    if local.exists():
        return local

    # 3. XDG config dir
    xdg = Path.home() / ".config" / "gemsieve" / "config.yaml"
    if xdg.exists():
        return xdg

    return None


def _load_dotenv() -> None:
    """Load .env file from current directory if it exists."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Don't overwrite already-set env vars
        if key not in os.environ:
            os.environ[key] = value


def _apply_env_overrides(config: Config) -> Config:
    """Override config values from environment variables.

    Supports:
        ollama_host     -> config.ai.ollama_base_url
        ollama_api_key  -> config.ai.ollama_api_key
        model_name      -> config.ai.model
    """
    if os.environ.get("ollama_host"):
        config.ai.ollama_base_url = os.environ["ollama_host"]
    if os.environ.get("ollama_api_key"):
        config.ai.ollama_api_key = os.environ["ollama_api_key"]
    if os.environ.get("model_name"):
        config.ai.model = os.environ["model_name"]
    return config


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from YAML file, merging with defaults.

    Also loads .env file and applies environment variable overrides.
    """
    _load_dotenv()

    if path is not None:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        config_path = _find_config_file()

    if config_path is None:
        config = Config()
    else:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        config = _dict_to_config(raw)

    return _apply_env_overrides(config)
