from __future__ import annotations

import hashlib
import re

_STRIP = re.compile(r"[^0-9a-zа-яё]+")


def canonical_text(value: str | None) -> str:
    """Aggressive normalisation: 'Python-разработчик' == 'python разработчик'."""
    return _STRIP.sub(" ", (value or "").lower()).strip()


def make_fingerprint(
    company: str | None,
    title: str,
    description: str,
    description_chars: int = 1500,
) -> str:
    """Stable hash of company+title+body prefix, used to detect the same posting."""
    parts = (
        canonical_text(company),
        canonical_text(title),
        canonical_text(description)[:description_chars],
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


def match_key(company: str | None, title: str) -> str:
    """Short key for fuzzy comparison of two postings."""
    return f"{canonical_text(company)} {canonical_text(title)}".strip()
