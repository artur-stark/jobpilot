"""Heuristic extraction of structured fields from free-form posting text.

Job feeds are messy: salary lives in the title on one board and in the body on
another, the company is sometimes an RSS <author> and sometimes a sentence in
the description. These helpers cover the common shapes and are pinned by tests.
"""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:  # selectolax >= 1.0 ships the lexbor backend only
    from selectolax.lexbor import LexborHTMLParser as _HTMLParser
except ImportError:  # pragma: no cover - older selectolax releases
    from selectolax.parser import HTMLParser as _HTMLParser

_SPACES = re.compile(r"[ \t\u00a0\u202f]+")
_NON_WORD = re.compile(r"[^\w\s+#./&-]")
_CYR = re.compile(r"[а-яё]", re.IGNORECASE)
_UK = re.compile(r"[іїєґ]", re.IGNORECASE)
_LAT = re.compile(r"[a-z]", re.IGNORECASE)

_CURRENCY = (
    ("₽", "RUB"),
    ("руб", "RUB"),
    ("rub", "RUB"),
    ("р.", "RUB"),
    ("$", "USD"),
    ("usd", "USD"),
    ("€", "EUR"),
    ("eur", "EUR"),
    ("грн", "UAH"),
    ("uah", "UAH"),
)

_NUM = r"(?:[₽$€]\s*)?(\d[\d \u00a0\u202f]{2,}|\d+)(?:[.,](\d{1,2}))?\s*([kк])?"
_CUR_INLINE = r"(?:₽|руб\.?|грн|\$|€|usd|eur|rub|uah)"
_RANGE_OT_DO = re.compile(
    rf"от\s*{_NUM}\s*(?:{_CUR_INLINE})?\s*(?:до|[-–—])\s*{_NUM}", re.IGNORECASE
)
_RANGE_DASH = re.compile(
    rf"{_NUM}\s*(?:{_CUR_INLINE})?\s*[-–—]\s*(?:{_CUR_INLINE})?\s*{_NUM}", re.IGNORECASE
)
_FROM = re.compile(rf"от\s*{_NUM}", re.IGNORECASE)
_TO = re.compile(rf"до\s*{_NUM}", re.IGNORECASE)

# salaries below these floors are almost certainly not salaries
_SALARY_FLOOR = {"RUB": 10000, "UAH": 4000, "USD": 150, "EUR": 150, "KZT": 50000}
# "6-12міс досвіду", "5-8 %", "2-3 года" - units that follow a bogus number
_UNIT_AFTER = re.compile(r"\s*(%|міс|мес|лет|год|дн|час|шт|раз)", re.IGNORECASE)

_REF_PATTERNS = (
    ("hh", re.compile(r"(?:hh\.ru|headhunter\.ru)/(?:vacancy|vacancies)/(\d+)")),
    ("habr", re.compile(r"career\.habr\.com/vacancies/(\d+)")),
    ("djinni", re.compile(r"djinni\.co/jobs/(\d+)")),
    ("linkedin", re.compile(r"linkedin\.com/jobs/view/(\d+)")),
    ("geekjob", re.compile(r"geekjob\.ru/vacancy/([0-9a-f]{24})")),
    ("greenhouse", re.compile(r"greenhouse\.io/([\w.-]+)/jobs/(\d+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{36})")),
)

_TRACKING_PARAMS = {
    "ref",
    "source",
    "fbclid",
    "gclid",
    "yclid",
    "_openstat",
    "from",
    "gh_src",
}

_EXPERIENCE_RULES = (
    ("lead", r"\blead\b|тимлид|team ?lead|head of|\bcto\b|руководител"),
    ("senior", r"senior|сеньор|ведущий специалист|\bболее 6\b|от 5 лет|от 6 лет"),
    ("middle", r"middle|мидл|от 1 года до 3|1-3 года|3-6 лет"),
    ("junior", r"junior|джун|младший|\b0-1\b"),
    ("intern", r"стаж[её]р|стажиров|intern|trainee|без опыта|нет опыта"),
)


def strip_html(value: str | None) -> str:
    """HTML -> plain text with normalised whitespace."""
    if not value:
        return ""
    text = html.unescape(value)
    if "<" in text and ">" in text:
        tree = _HTMLParser(text)
        for node in tree.css("script,style"):
            node.decompose()
        root = tree.body or tree.root
        text = root.text(separator=" ") if root else text
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def normalize_key(value: str | None) -> str:
    """Lowercase, punctuation-free form used for fingerprints and fuzzy match."""
    if not value:
        return ""
    text = strip_html(value).lower()
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def canonical_url(url: str) -> str:
    """Drop tracking parameters and fragments so reposts compare equal."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme or "https", parts.netloc.lower(), path, urlencode(query), ""))


def clean_title(title: str) -> tuple[str, str]:
    """Unwrap board-specific title noise. Returns (title, text_with_salary)."""
    text = strip_html(title).strip()
    hint = ""
    match = re.match(
        r"^(?:требуется|ищем|вакансия:?)\s*[«\"„](?P<t>.+?)[»\"“]\s*(?:\((?P<h>.+)\))?$",
        text,
        re.IGNORECASE,
    )
    if match:
        text = match.group("t").strip()
        hint = (match.group("h") or "").strip()
    return text.strip(" «»\"'"), hint


def _detect_currency(text: str) -> str | None:
    lowered = text.lower()
    for token, code in _CURRENCY:
        if token in lowered:
            return code
    return None


def _to_number(raw: str, decimals: str | None, thousands: str | None) -> int | None:
    digits = re.sub(r"[ \u00a0\u202f]", "", raw)
    try:
        value = float(digits.replace(",", "."))
    except ValueError:
        return None
    if decimals:
        value = float(f"{int(value)}.{decimals}")
    if thousands:
        value *= 1000
    return int(value)


def _plausible(value: int | None, currency: str) -> bool:
    if not value:
        return False
    return value >= _SALARY_FLOOR.get(currency, 1000)


def parse_salary(text: str) -> dict[str, int | str | None] | None:
    """Extract {'from', 'to', 'currency'} or None when nothing reliable found.

    Currency must sit next to the numbers: a "₽" somewhere else in a long
    description is not enough, otherwise "6-12міс досвіду" becomes a salary.
    """
    if not text:
        return None

    patterns = (
        (_RANGE_OT_DO, "range"),
        (_RANGE_DASH, "range"),
        (_FROM, "from"),
        (_TO, "to"),
    )
    for pattern, kind in patterns:
        for match in pattern.finditer(text):
            window = text[max(0, match.start() - 12) : match.end() + 12]
            currency = _detect_currency(window)
            if currency is None:
                continue
            if _UNIT_AFTER.match(text[match.end() : match.end() + 5]):
                continue

            groups = match.groups()
            if kind == "range":
                low = _to_number(groups[0], groups[1], groups[2])
                high = _to_number(groups[3], groups[4], groups[5])
                if not _plausible(low, currency) and not _plausible(high, currency):
                    continue
                if low and high and low > high:
                    low, high = high, low
                return {"from": low, "to": high, "currency": currency}

            value = _to_number(groups[0], groups[1], groups[2])
            if not _plausible(value, currency):
                continue
            if kind == "from":
                return {"from": value, "to": None, "currency": currency}
            return {"from": None, "to": value, "currency": currency}

    return None


def guess_company(title: str, description: str = "") -> str | None:
    for source in (title, description):
        match = re.search(r"компания\s*[«\"„]([^»\"“]{2,60})[»\"“]", source, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r"компания\s+([\w&.\- ]{2,40}?)\s+ищет", source, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def guess_city(text: str) -> str | None:
    match = re.search(
        r"([А-ЯЁ][а-яё\-]+(?:[\s-][А-ЯЁа-яё\-]+)?)\s*,\s*(?:Россия|Украина|Казахстан|Беларусь)",
        text,
    )
    return match.group(1).strip() if match else None


def guess_experience(text: str) -> str | None:
    lowered = text.lower()
    for level, pattern in _EXPERIENCE_RULES:
        if re.search(pattern, lowered):
            return level
    return None


def guess_work_format(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"гибрид|hybrid", lowered):
        return "hybrid"
    if re.search(r"удал[её]нн|удаленк|remote|дистанц|из дома", lowered):
        return "remote"
    if re.search(r"офис|на месте работодателя|on-?site", lowered):
        return "office"
    return None


def guess_language(text: str) -> str | None:
    if not text:
        return None
    if len(_UK.findall(text)) >= 3:
        return "uk"
    cyr = len(_CYR.findall(text))
    lat = len(_LAT.findall(text))
    if cyr == 0 and lat == 0:
        return None
    # technical Russian text is full of latin tokens (REST, FastAPI, middle),
    # so cyrillic does not need to dominate - it only needs to be present
    if cyr >= 5 and cyr * 2 >= lat:
        return "ru"
    if lat >= 5 and lat * 2 >= cyr:
        return "en"
    return "ru" if cyr > lat else "en"


def extract_refs(*texts: str) -> list[str]:
    """Provider ids found in urls/text, e.g. ['hh:123', 'habr:1000170506']."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for provider, pattern in _REF_PATTERNS:
            for match in pattern.finditer(text):
                value = ":".join(group for group in match.groups() if group)
                ref = f"{provider}:{value}"
                if ref not in found:
                    found.append(ref)
    return found
