from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, select

from jobpilot.db import Vacancy, VacancyCluster, init_db, make_engine
from jobpilot.normalize.dedupe import insert_vacancy
from jobpilot.sources.base import RawVacancy


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        yield session


def raw(
    source: str,
    external_id: str,
    title: str,
    company: str,
    description: str,
    experience: str | None = None,
) -> RawVacancy:
    return RawVacancy(
        source=source,
        external_id=external_id,
        url=f"https://example.org/{source}/{external_id}",
        title=title,
        company=company,
        description=description,
        experience=experience,
    )


def test_same_posting_from_two_boards_shares_cluster(session: Session) -> None:
    geekjob = insert_vacancy(
        session,
        raw("geekjob", "g1", "Python-разработчик", "Уралкод", "FastAPI, PostgreSQL, офис"),
        priority=30,
    )
    session.commit()
    habr = insert_vacancy(
        session,
        raw("habr_python", "h1", "Python-разработчик", "Уралкод", "FastAPI, PostgreSQL, офис"),
        priority=20,
    )
    session.commit()

    assert geekjob.cluster_id == habr.cluster_id
    assert len(session.exec(select(VacancyCluster)).all()) == 1
    assert len(session.exec(select(Vacancy)).all()) == 2

    cluster = session.get(VacancyCluster, habr.cluster_id)
    assert cluster is not None
    assert cluster.primary_id == habr.vacancy.id


def test_fuzzy_merge_on_close_titles(session: Session) -> None:
    first = insert_vacancy(
        session,
        raw("habr_python", "h2", "Python-разработчик (FastAPI)", "Уралкод", "Разработка сервисов"),
        priority=20,
    )
    session.commit()
    second = insert_vacancy(
        session,
        raw("geekjob", "g2", "Python разработчик FastAPI", "Уралкод", "Другие задачи и текст"),
        priority=30,
    )
    session.commit()

    assert second.cluster_id == first.cluster_id
    assert second.merged is True
    assert len(session.exec(select(VacancyCluster)).all()) == 1


def test_different_seniority_is_not_merged(session: Session) -> None:
    insert_vacancy(
        session,
        raw(
            "habr",
            "h3",
            "Python-разработчик",
            "Уралкод",
            "сервисы на FastAPI",
            experience="middle",
        ),
        priority=20,
    )
    session.commit()
    junior = insert_vacancy(
        session,
        raw(
            "habr",
            "h4",
            "Python-разработчик",
            "Уралкод",
            "поддержка legacy-кода",
            experience="junior",
        ),
        priority=20,
    )
    session.commit()

    assert junior.merged is False
    assert len(session.exec(select(VacancyCluster)).all()) == 2


def test_same_source_item_is_refreshed(session: Session) -> None:
    first = insert_vacancy(
        session, raw("habr", "h5", "Python-разработчик", "Уралкод", "текст"), priority=20
    )
    session.commit()
    again = insert_vacancy(
        session, raw("habr", "h5", "Python-разработчик (обновлено)", "Уралкод", "новый текст"),
        priority=20,
    )
    session.commit()

    assert again.inserted is False
    assert again.cluster_id == first.cluster_id
    assert again.vacancy.title == "Python-разработчик (обновлено)"
    assert len(session.exec(select(Vacancy)).all()) == 1


def test_primary_upgrades_when_better_source_arrives(session: Session) -> None:
    weak = insert_vacancy(
        session, raw("geekjob", "g6", "QA automation engineer", "ТестЛаб", "pytest, playwright"),
        priority=30,
    )
    session.commit()
    assert session.get(VacancyCluster, weak.cluster_id).primary_id == weak.vacancy.id

    strong = insert_vacancy(
        session, raw("habr", "h6", "QA automation engineer", "ТестЛаб", "pytest, playwright"),
        priority=20,
    )
    session.commit()

    cluster = session.get(VacancyCluster, strong.cluster_id)
    assert cluster is not None
    assert cluster.primary_id == strong.vacancy.id


def test_duplicate_url_is_canonicalised(session: Session) -> None:
    item = insert_vacancy(
        session,
        RawVacancy(
            source="habr",
            external_id="h7",
            url="https://career.habr.com/vacancies/1?utm_source=rss",
            title="Разработчик",
            description="текст",
        ),
        priority=20,
    )
    session.commit()
    assert item.vacancy.url == "https://career.habr.com/vacancies/1"
