"""Generic RSS/Atom adapter.

One class serves every feed: Habr Career, Geekjob, Djinni, Telegram->RSS
bridges and so on. Board-specific quirks are handled by `mapping` overrides
in YAML, so a new feed costs a few lines of config instead of a new module.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

import feedparser

from jobpilot.normalize.extract import (
    canonical_url,
    clean_title,
    extract_refs,
    guess_city,
    guess_company,
    guess_experience,
    guess_language,
    guess_work_format,
    parse_salary,
    strip_html,
)
from jobpilot.sources.base import BaseSource, RawVacancy

_SLUG_ID = re.compile(r"([0-9a-zA-Z_-]{4,})$")


class FeedSource(BaseSource):
    kind = "feed"

    def fetch(self) -> list[RawVacancy]:
        if not self.cfg.url:
            raise ValueError(f"source {self.id}: url is required")
        response = self.client.get(self.cfg.url, headers={"User-Agent": self.user_agent})
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"source {self.id}: feed parse error: {parsed.bozo_exception}")
        return [self.apply_defaults(self._to_raw(entry)) for entry in parsed.entries]

    def _to_raw(self, entry: object) -> RawVacancy:
        link = canonical_url(str(entry.get("link") or ""))
        description = strip_html(self._entry_text(entry))
        title, salary_hint = clean_title(str(entry.get("title") or ""))
        company = strip_html(str(entry.get("author") or "")) or guess_company(title, description)

        if "→" in title and not company:
            left, _, right = title.partition("→")
            if left.strip() and right.strip():
                title, company = left.strip(), right.strip()

        salary_text = "\n".join(part for part in (salary_hint, title, description) if part)
        salary = parse_salary(salary_text) or {}
        combined = f"{title}\n{description}"

        mapping = self.cfg.mapping
        if "title" in mapping:
            title = strip_html(str(entry.get(mapping["title"]) or title))
        if "company" in mapping:
            company = strip_html(str(entry.get(mapping["company"]) or "")) or company

        raw = {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "link": entry.get("link"),
            "author": entry.get("author"),
            "published": entry.get("published"),
            "refs": extract_refs(link, description),
        }

        return RawVacancy(
            source=self.id,
            external_id=self._external_id(entry, link),
            url=link,
            title=title or "(без названия)",
            company=company,
            description=description,
            salary_from=salary.get("from"),
            salary_to=salary.get("to"),
            currency=salary.get("currency"),
            city=guess_city(combined),
            work_format=guess_work_format(combined),
            experience=guess_experience(combined),
            language=guess_language(combined),
            published_at=self._published(entry),
            raw=raw,
        )

    @staticmethod
    def _entry_text(entry: object) -> str:
        summary = entry.get("summary")
        if summary:
            return str(summary)
        content = entry.get("content") or []
        if content:
            return str(content[0].get("value", ""))
        return str(entry.get("description") or "")

    @staticmethod
    def _external_id(entry: object, link: str) -> str:
        for key in ("id", "guid", "link"):
            value = entry.get(key)
            if value:
                return str(value)
        match = _SLUG_ID.search(urlsplit(link).path)
        if match:
            return match.group(1)
        return hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _published(entry: object) -> datetime | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        return None
