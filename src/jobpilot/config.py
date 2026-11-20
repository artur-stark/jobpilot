"""Settings and declarative source configuration.

The idea: adding a new RSS feed or JSON API is a YAML edit, not a code change.
Only genuinely new *kinds* of sources (html, browser, hh oauth) need Python.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SourceConfig(BaseModel):
    """One vacancy source as described in config/sources.yml."""

    id: str
    kind: str = "feed"  # feed | hh_rss | jsonapi | fake
    enabled: bool = True
    priority: int = 50
    url: str | None = None
    # field name -> dot path inside the raw item (jsonapi) or entry key (feed)
    mapping: dict[str, str] = Field(default_factory=dict)
    # constant values applied on top of parsed data
    defaults: dict[str, Any] = Field(default_factory=dict)
    # query string parameters for jsonapi sources
    params: dict[str, Any] = Field(default_factory=dict)
    items_path: str | None = None
    tags: list[str] = Field(default_factory=list)


class SourcesFile(BaseModel):
    sources: list[SourceConfig] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBPILOT_",
        env_file=".env",
        extra="ignore",
    )

    # absolute by default: the CLI must work from any working directory
    db_url: str = Field(
        default_factory=lambda: f"sqlite:///{(PROJECT_ROOT / 'data' / 'jobpilot.db').as_posix()}"
    )
    config_dir: Path = PROJECT_ROOT / "config"
    data_dir: Path = PROJECT_ROOT / "data"
    user_agent: str = "jobpilot/0.1 (+https://github.com/artur-stark/jobpilot)"
    http_timeout: float = 20.0
    # two vacancies are considered the same when titles+companies are that close
    fuzzy_threshold: int = 92
    fuzzy_window_days: int = 14

    def load_sources(self, only: list[str] | None = None) -> list[SourceConfig]:
        path = self.config_dir / "sources.yml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sources = SourcesFile(**raw).sources
        selected = [s for s in sources if s.enabled]
        if only:
            wanted = {name.strip() for name in only}
            selected = [s for s in selected if s.id in wanted]
            missing = wanted - {s.id for s in sources}
            if missing:
                raise SystemExit(f"unknown source(s): {', '.join(sorted(missing))}")
        return selected

    def load_yaml(self, name: str) -> dict[str, Any]:
        path = self.config_dir / name
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
