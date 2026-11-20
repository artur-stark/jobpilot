"""Generic JSON API adapter driven by dot-path mapping.

Covers sources that expose open JSON (Trudvsem, RemoteOK, Himalayas, ...) and
later the ATS boards (Greenhouse/Lever/Ashby). Mapping example:

    kind: jsonapi
    url: https://opendata.trudvsem.ru/api/v1/vacancies
    items_path: results.vacancies
    mapping:
      external_id: vacancy.id
      title: vacancy.job-name
      company: vacancy.company.name
      description: vacancy.duty
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from jobpilot.normalize.extract import (
    canonical_url,
    clean_title,
    guess_city,
    guess_experience,
    guess_language,
    guess_work_format,
    parse_salary,
    strip_html,
)
from jobpilot.sources.base import BaseSource, RawVacancy


def get_path(data: Any, path: str | None) -> Any:
    """Resolve 'a.b.0.c' against nested dicts/lists without raising."""
    if not path:
        return data
    current: Any = data
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(" ", "").replace("\u00a0", "")))
    except (TypeError, ValueError):
        return None


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class JsonApiSource(BaseSource):
    kind = "jsonapi"

    def fetch(self) -> list[RawVacancy]:
        if not self.cfg.url:
            raise ValueError(f"source {self.id}: url is required")
        response = self.client.get(
            self.cfg.url,
            params=self.cfg.params or None,
            headers={"User-Agent": self.user_agent},
        )
        response.raise_for_status()
        payload = response.json()
        items = get_path(payload, self.cfg.items_path)
        if not isinstance(items, list):
            raise ValueError(f"source {self.id}: items_path does not point to a list")
        return [self.apply_defaults(self._to_raw(item)) for item in items]

    def _to_raw(self, item: Any) -> RawVacancy:
        def field(name: str, default: Any = None) -> Any:
            value = get_path(item, self.cfg.mapping.get(name))
            return default if value in (None, "") else value

        description = strip_html(str(field("description", "")))
        title = clean_title(str(field("title", "")))[0]
        url = canonical_url(str(field("url", "")))
        salary = parse_salary(f"{field('title', '')}\n{description}") or {}
        combined = f"{title}\n{description}"

        return RawVacancy(
            source=self.id,
            external_id=str(field("external_id", url) or url),
            url=url,
            title=title or "(без названия)",
            company=strip_html(str(field("company", ""))) or None,
            description=description,
            salary_from=_as_int(field("salary_from")) or salary.get("from"),
            salary_to=_as_int(field("salary_to")) or salary.get("to"),
            currency=field("currency") or salary.get("currency"),
            city=str(field("city")) or guess_city(combined),
            work_format=str(field("work_format")) or guess_work_format(combined),
            experience=str(field("experience")) or guess_experience(combined),
            language=guess_language(combined),
            published_at=_as_datetime(field("published_at")),
            raw={"item": item},
        )
