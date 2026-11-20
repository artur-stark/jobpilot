from __future__ import annotations

from jobpilot.normalize.fingerprint import canonical_text, make_fingerprint, match_key


def test_fingerprint_ignores_case_hyphens_and_spacing() -> None:
    first = make_fingerprint("Уралкод", "Python-разработчик", "FastAPI, PostgreSQL")
    second = make_fingerprint("уралкод", "python разработчик", "fastapi postgresql")
    assert first == second
    assert len(first) == 32


def test_fingerprint_changes_with_content() -> None:
    assert make_fingerprint("X", "Backend", "one") != make_fingerprint("X", "Backend", "two")
    assert make_fingerprint("X", "Backend", "text") != make_fingerprint("Y", "Backend", "text")


def test_fingerprint_uses_only_description_prefix() -> None:
    prefix = "a" * 1500
    assert make_fingerprint("X", "Backend", prefix + " tail 1") == make_fingerprint(
        "X", "Backend", prefix + " tail 2"
    )


def test_canonical_text() -> None:
    assert canonical_text("  Python-разработчик,  Junior! ") == "python разработчик junior"
    assert canonical_text(None) == ""


def test_match_key() -> None:
    assert match_key("Уралкод", "Python-разработчик (FastAPI)") == (
        "уралкод python разработчик fastapi"
    )
