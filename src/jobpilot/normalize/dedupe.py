"""Two-stage dedupe: exact fingerprint, then fuzzy title/company match.

The same job usually arrives from several boards with slightly different text,
so exact hashing alone is not enough. Fuzzy stage is limited to a recent
window; the exact stage is cheap and always runs first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta

from rapidfuzz import fuzz
from sqlmodel import Session, select

from jobpilot.db.models import Vacancy, VacancyCluster, VacancyFingerprint, utcnow
from jobpilot.normalize.extract import canonical_url
from jobpilot.normalize.fingerprint import make_fingerprint, match_key
from jobpilot.sources.base import RawVacancy

FUZZY_CANDIDATES_LIMIT = 800


@dataclass(slots=True)
class InsertResult:
    vacancy: Vacancy
    inserted: bool
    cluster_id: int
    merged: bool = False


def insert_vacancy(
    session: Session,
    raw: RawVacancy,
    priority: int = 50,
    *,
    fuzzy_threshold: int = 92,
    fuzzy_window_days: int = 14,
) -> InsertResult:
    existing = session.exec(
        select(Vacancy).where(
            Vacancy.source == raw.source, Vacancy.external_id == raw.external_id
        )
    ).first()
    if existing is not None:
        _refresh(existing, raw)
        session.add(existing)
        return InsertResult(
            vacancy=existing, inserted=False, cluster_id=existing.cluster_id or 0
        )

    fingerprint = make_fingerprint(raw.company, raw.title, raw.description)
    cluster = _cluster_by_fingerprint(session, fingerprint)
    merged = cluster is not None

    if cluster is None:
        candidate = _fuzzy_candidate(session, raw, fuzzy_threshold, fuzzy_window_days)
        if candidate is not None and candidate.cluster_id is not None:
            cluster = session.get(VacancyCluster, candidate.cluster_id)
            merged = cluster is not None

    if cluster is None:
        cluster = VacancyCluster(fingerprint=fingerprint)
        session.add(cluster)
        session.flush()

    _remember_fingerprint(session, fingerprint, cluster)

    vacancy = Vacancy(
        source=raw.source,
        external_id=raw.external_id,
        url=canonical_url(raw.url),
        title=raw.title,
        company=raw.company,
        description=raw.description,
        salary_from=raw.salary_from,
        salary_to=raw.salary_to,
        currency=raw.currency,
        city=raw.city,
        work_format=raw.work_format,
        experience=raw.experience,
        language=raw.language,
        published_at=raw.published_at,
        fingerprint=fingerprint,
        source_priority=priority,
        cluster_id=cluster.id,
        raw=_dump_raw(raw.raw),
    )
    session.add(vacancy)
    session.flush()

    _recompute_primary(session, cluster)
    return InsertResult(vacancy=vacancy, inserted=True, cluster_id=cluster.id or 0, merged=merged)


def _cluster_by_fingerprint(session: Session, fingerprint: str) -> VacancyCluster | None:
    link = session.get(VacancyFingerprint, fingerprint)
    if link is None:
        return None
    return session.get(VacancyCluster, link.cluster_id)


def _remember_fingerprint(session: Session, fingerprint: str, cluster: VacancyCluster) -> None:
    if session.get(VacancyFingerprint, fingerprint) is None:
        session.add(VacancyFingerprint(fingerprint=fingerprint, cluster_id=cluster.id or 0))
        session.flush()


def _fuzzy_candidate(
    session: Session,
    raw: RawVacancy,
    threshold: int,
    window_days: int,
) -> Vacancy | None:
    if not raw.title:
        return None
    cutoff = utcnow() - timedelta(days=window_days)
    recent = session.exec(
        select(Vacancy)
        .where(Vacancy.fetched_at >= cutoff)
        .order_by(Vacancy.id.desc())
        .limit(FUZZY_CANDIDATES_LIMIT)
    ).all()

    key = match_key(raw.company, raw.title)
    if not key:
        return None

    best: tuple[float, Vacancy] | None = None
    for candidate in recent:
        if candidate.cluster_id is None:
            continue
        # never merge different seniority levels of the same role
        if raw.experience and candidate.experience and raw.experience != candidate.experience:
            continue
        score = fuzz.token_set_ratio(key, match_key(candidate.company, candidate.title))
        if score >= threshold and (best is None or score > best[0]):
            best = (score, candidate)
    return best[1] if best else None


def _recompute_primary(session: Session, cluster: VacancyCluster) -> None:
    members = session.exec(
        select(Vacancy).where(Vacancy.cluster_id == cluster.id)
    ).all()
    if not members:
        return
    best = min(members, key=lambda item: (item.source_priority, item.id or 0))
    if cluster.primary_id != best.id:
        cluster.primary_id = best.id
        session.add(cluster)
        session.flush()


def _refresh(vacancy: Vacancy, raw: RawVacancy) -> None:
    """Same source+id seen again: refresh mutable fields only."""
    vacancy.url = canonical_url(raw.url) or vacancy.url
    vacancy.title = raw.title or vacancy.title
    vacancy.description = raw.description or vacancy.description
    vacancy.company = raw.company or vacancy.company
    vacancy.salary_from = raw.salary_from or vacancy.salary_from
    vacancy.salary_to = raw.salary_to or vacancy.salary_to
    vacancy.currency = raw.currency or vacancy.currency
    vacancy.city = raw.city or vacancy.city
    vacancy.work_format = raw.work_format or vacancy.work_format
    vacancy.experience = raw.experience or vacancy.experience
    vacancy.published_at = raw.published_at or vacancy.published_at
    vacancy.fetched_at = utcnow()


def _dump_raw(raw: dict) -> str | None:
    if not raw:
        return None
    return json.dumps(raw, ensure_ascii=False, default=str)[:20000]
