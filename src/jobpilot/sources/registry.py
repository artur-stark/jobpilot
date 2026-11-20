from __future__ import annotations

from collections.abc import Iterable

import httpx

from jobpilot.config import SourceConfig
from jobpilot.sources.base import BaseSource
from jobpilot.sources.fake import FakeSource
from jobpilot.sources.feed import FeedSource
from jobpilot.sources.jsonapi import JsonApiSource

SOURCE_KINDS: dict[str, type[BaseSource]] = {
    "feed": FeedSource,
    "jsonapi": JsonApiSource,
    "fake": FakeSource,
}


def build_sources(
    configs: Iterable[SourceConfig],
    client: httpx.Client,
    user_agent: str,
) -> list[BaseSource]:
    sources: list[BaseSource] = []
    for cfg in configs:
        source_cls = SOURCE_KINDS.get(cfg.kind)
        if source_cls is None:
            raise SystemExit(
                f"source {cfg.id}: unknown kind {cfg.kind!r} "
                f"(available: {', '.join(sorted(SOURCE_KINDS))})"
            )
        sources.append(source_cls(cfg, client, user_agent))
    return sources
