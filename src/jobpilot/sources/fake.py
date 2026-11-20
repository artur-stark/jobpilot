"""Deterministic synthetic source for demos, docs and offline tests."""

from __future__ import annotations

from datetime import UTC, datetime

from jobpilot.sources.base import BaseSource, RawVacancy

_DEMO = (
    {
        "external_id": "demo-python-middle",
        "url": "https://demo.local/vacancies/python-middle",
        "title": "Python-разработчик (FastAPI)",
        "company": "Демо-Софт",
        "description": (
            "Разработка REST API на FastAPI, PostgreSQL, Docker. "
            "Middle, офис в Екатеринбурге."
        ),
        "salary_from": 130000,
        "salary_to": 190000,
        "currency": "RUB",
        "city": "Екатеринбург",
        "work_format": "office",
        "experience": "middle",
        "language": "ru",
    },
    {
        "external_id": "demo-js-remote",
        "url": "https://demo.local/vacancies/js-remote",
        "title": "Fullstack разработчик (React + Node)",
        "company": "Remote Labs",
        "description": (
            "Продуктовая команда, полностью удалённо. "
            "TypeScript, React, Node.js, PostgreSQL."
        ),
        "salary_from": 150000,
        "salary_to": 220000,
        "currency": "RUB",
        "city": None,
        "work_format": "remote",
        "experience": "middle",
        "language": "ru",
    },
    {
        "external_id": "demo-embedded",
        "url": "https://demo.local/vacancies/embedded",
        "title": "Инженер-программист (embedded, C/C++)",
        "company": "ПромАвтоматика",
        "description": (
            "Прошивки для контроллеров: C, FreeRTOS, UART/SPI/I2C, отладка. "
            "Python для автотестов."
        ),
        "salary_from": 140000,
        "salary_to": 200000,
        "currency": "RUB",
        "city": "Екатеринбург",
        "work_format": "hybrid",
        "experience": "middle",
        "language": "ru",
    },
    {
        "external_id": "demo-intern",
        "url": "https://demo.local/vacancies/intern",
        "title": "Стажёр Python-разработчик",
        "company": "Демо-Софт",
        "description": "Стажировка 3 месяца, без опыта, оплата 40 000 ₽.",
        "salary_from": 40000,
        "salary_to": None,
        "currency": "RUB",
        "city": "Екатеринбург",
        "work_format": "office",
        "experience": "intern",
        "language": "ru",
    },
)


class FakeSource(BaseSource):
    kind = "fake"

    def fetch(self) -> list[RawVacancy]:
        now = datetime.now(UTC)
        return [
            self.apply_defaults(
                RawVacancy(
                    source=self.id,
                    published_at=now,
                    raw={"demo": True},
                    **item,
                )
            )
            for item in _DEMO
        ]
