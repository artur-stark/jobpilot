"""Database models.

Two-level storage:
  * Vacancy      - one posting as seen in one source (source + external_id unique)
  * VacancyCluster - postings that describe the same job; keeps one `primary_id`

The feed shows only cluster primaries, so a vacancy reposted on three boards
is displayed once.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Vacancy(SQLModel, table=True):
    __tablename__ = "vacancy"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_vacancy_source_external"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    external_id: str
    url: str
    title: str
    company: str | None = None
    description: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))

    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None

    city: str | None = Field(default=None, index=True)
    work_format: str | None = None  # remote | hybrid | office | unknown
    experience: str | None = Field(default=None, index=True)  # intern..lead
    language: str | None = None  # ru | en | uk

    published_at: datetime | None = Field(default=None, index=True)
    fetched_at: datetime = Field(default_factory=utcnow)

    fingerprint: str = Field(index=True)
    source_priority: int = 50
    cluster_id: int | None = Field(default=None, foreign_key="vacancycluster.id", index=True)
    raw: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    @property
    def salary_label(self) -> str:
        if not self.salary_from and not self.salary_to:
            return "-"
        currency = self.currency or ""
        if self.salary_from and self.salary_to:
            return f"{self.salary_from:,} - {self.salary_to:,} {currency}".replace(",", " ")
        if self.salary_from:
            return f"от {self.salary_from:,} {currency}".replace(",", " ")
        return f"до {self.salary_to:,} {currency}".replace(",", " ")


class VacancyCluster(SQLModel, table=True):
    __tablename__ = "vacancycluster"

    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True, unique=True)
    primary_id: int | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class VacancyFingerprint(SQLModel, table=True):
    """Fingerprint -> cluster index.

    A cluster owns one canonical fingerprint, but fuzzy merges can add more
    variants; this table keeps all of them so later exact matches still land
    in the right cluster.
    """

    __tablename__ = "vacancyfingerprint"

    fingerprint: str = Field(primary_key=True)
    cluster_id: int = Field(foreign_key="vacancycluster.id", index=True)



class SourceRun(SQLModel, table=True):
    __tablename__ = "sourcerun"

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: int = 0
    message: str | None = None
