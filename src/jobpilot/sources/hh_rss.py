"""hh.ru search RSS adapter.

hh.ru exposes every search as an RSS feed (20 newest postings per query), so
vacancies can be collected without an application, access token or moderation,
unlike ``api.hh.ru`` which answers 403 to anonymous requests.

The feed body is a short summary with labelled fields, so company/city/salary
are recovered from those labels instead of the API's structured JSON.
"""

from __future__ import annotations

import re

from jobpilot.normalize.extract import parse_labeled_block, parse_ru_date, parse_salary
from jobpilot.sources.base import RawVacancy
from jobpilot.sources.feed import FeedSource

LABELS = {
    "company": "Вакансия компании",
    "created": "Создана",
    "city": "Регион",
    "salary": "Предполагаемый уровень месячного дохода",
}

_VACANCY_ID = re.compile(r"/vacancy/(\d+)")


class HhRssSource(FeedSource):
    kind = "hh_rss"

    def _to_raw(self, entry: object) -> RawVacancy:
        vacancy = super()._to_raw(entry)
        fields = parse_labeled_block(vacancy.description, LABELS)

        if fields.get("company"):
            vacancy.company = fields["company"]
        if fields.get("city"):
            vacancy.city = fields["city"]

        salary = parse_salary(fields.get("salary", ""))
        if salary:
            vacancy.salary_from = salary["from"]
            vacancy.salary_to = salary["to"]
            vacancy.currency = salary["currency"]

        if vacancy.published_at is None and fields.get("created"):
            vacancy.published_at = parse_ru_date(fields["created"])

        match = _VACANCY_ID.search(vacancy.url)
        if match:
            vacancy.external_id = match.group(1)

        return vacancy
