"""Source contract.

Everything downstream (dedupe, scoring, letters) works with `RawVacancy`
only, so adding a source never touches the rest of the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx

from jobpilot.config import SourceConfig


@dataclass(slots=True)
class RawVacancy:
    source: str
    external_id: str
    url: str
    title: str
    company: str | None = None
    description: str = ""
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None
    city: str | None = None
    work_format: str | None = None
    experience: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class Source(Protocol):
    cfg: SourceConfig

    def fetch(self) -> list[RawVacancy]: ...


class BaseSource:
    kind = "base"

    def __init__(self, cfg: SourceConfig, client: httpx.Client, user_agent: str) -> None:
        self.cfg = cfg
        self.client = client
        self.user_agent = user_agent

    @property
    def id(self) -> str:
        return self.cfg.id

    @property
    def priority(self) -> int:
        return self.cfg.priority

    def fetch(self) -> list[RawVacancy]:
        raise NotImplementedError

    def apply_defaults(self, vacancy: RawVacancy) -> RawVacancy:
        for key, value in self.cfg.defaults.items():
            current = getattr(vacancy, key, None)
            if current is None or current == "":
                setattr(vacancy, key, value)
        return vacancy
