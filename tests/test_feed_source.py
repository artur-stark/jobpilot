from __future__ import annotations

from pathlib import Path

import httpx

from jobpilot.config import SourceConfig
from jobpilot.sources.feed import FeedSource

FIXTURE = Path(__file__).parent / "fixtures" / "habr_feed.xml"


def make_source() -> FeedSource:
    body = FIXTURE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "career.habr.com"
        return httpx.Response(
            200, content=body, headers={"content-type": "application/rss+xml"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = SourceConfig(
        id="habr_python",
        kind="feed",
        priority=20,
        url="https://career.habr.com/vacancies/rss?q=python&remote=true",
    )
    return FeedSource(cfg, client, "jobpilot-test/1.0")


def test_feed_returns_all_items() -> None:
    assert len(make_source().fetch()) == 2


def test_feed_extracts_internship_fields() -> None:
    first = make_source().fetch()[0]
    assert first.source == "habr_python"
    assert first.external_id == "1000170506"
    assert first.title == "Стажировка Python разработчик (FastAPI)"
    assert first.company == "Pulsea"
    assert (first.salary_from, first.salary_to, first.currency) == (40000, 60000, "RUB")
    assert first.work_format == "remote"
    assert first.experience == "intern"
    assert first.language == "ru"
    assert first.published_at is not None
    assert first.published_at.tzinfo is not None
    assert first.raw["refs"] == ["habr:1000170506"]


def test_feed_extracts_middle_fields_and_cleans_url() -> None:
    second = make_source().fetch()[1]
    assert second.title == "Python-разработчик"
    assert second.url == "https://career.habr.com/vacancies/1000170001"
    assert second.salary_from == 150000
    assert second.salary_to is None
    assert second.city == "Екатеринбург"
    assert second.experience == "middle"
    assert "utm_source" not in second.url


def test_feed_sets_user_agent() -> None:
    seen: dict[str, str] = {}
    body = FIXTURE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = SourceConfig(id="habr", kind="feed", url="https://career.habr.com/vacancies/rss")
    FeedSource(cfg, client, "jobpilot-test/2.0").fetch()
    assert seen["ua"] == "jobpilot-test/2.0"
