from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from jobpilot.config import SourceConfig
from jobpilot.sources.hh_rss import HhRssSource

FIXTURE = Path(__file__).parent / "fixtures" / "hh_feed.xml"
URL = "https://hh.ru/search/vacancy/rss?text=python&area=3&professional_role=96"


def make_source(**defaults: Any) -> HhRssSource:
    body = FIXTURE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.ru"
        return httpx.Response(200, content=body, headers={"content-type": "application/rss+xml"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = SourceConfig(
        id="hh_ekb_python",
        kind="hh_rss",
        priority=15,
        url=URL,
        defaults=defaults,
    )
    return HhRssSource(cfg, client, "jobpilot-test/1.0")


def test_hh_rss_returns_all_items() -> None:
    assert len(make_source().fetch()) == 3


def test_hh_rss_parses_company_city_and_missing_salary() -> None:
    first = make_source().fetch()[0]
    assert first.source == "hh_ekb_python"
    assert first.external_id == "138785694"
    assert first.title == "QA Python engineer (Стажер)"
    assert first.company == "Центр финансовых технологий"
    assert first.city == "Екатеринбург"
    assert (first.salary_from, first.salary_to, first.currency) == (None, None, None)
    assert first.experience == "intern"
    assert first.work_format is None
    assert first.raw["refs"] == ["hh:138785694"]


def test_hh_rss_parses_salary_from_label() -> None:
    second = make_source().fetch()[1]
    assert second.external_id == "139536195"
    assert second.company == "Алабуга. Менеджмент"
    assert (second.salary_from, second.salary_to, second.currency) == (127500, None, "RUB")


def test_hh_rss_parses_upper_bound_and_unescapes_company() -> None:
    third = make_source().fetch()[2]
    assert third.company == "ООО «Ромашка & Ко»"
    assert third.city == "Москва"
    assert (third.salary_from, third.salary_to, third.currency) == (None, 250000, "RUB")


def test_hh_rss_published_at_from_pubdate() -> None:
    first = make_source().fetch()[0]
    assert first.published_at == datetime(2026, 11, 18, 7, 40, 46, 192000, tzinfo=UTC)


def test_hh_rss_falls_back_to_created_label() -> None:
    third = make_source().fetch()[2]
    assert third.published_at == datetime(2026, 11, 17, tzinfo=UTC)


def test_hh_rss_applies_work_format_default_for_remote_queries() -> None:
    vacancies = make_source(work_format="remote").fetch()
    assert [v.work_format for v in vacancies] == ["remote", "remote", "remote"]


def test_hh_rss_kind_is_registered() -> None:
    from jobpilot.sources.registry import SOURCE_KINDS

    assert SOURCE_KINDS["hh_rss"] is HhRssSource
