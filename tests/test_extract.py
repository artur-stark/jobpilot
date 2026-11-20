from __future__ import annotations

from jobpilot.normalize.extract import (
    canonical_url,
    clean_title,
    extract_refs,
    guess_city,
    guess_company,
    guess_experience,
    guess_language,
    guess_work_format,
    normalize_key,
    parse_salary,
    strip_html,
)


def test_parse_salary_range_from_title() -> None:
    salary = parse_salary("(от 40 000 до 60 000 ₽)")
    assert salary == {"from": 40000, "to": 60000, "currency": "RUB"}


def test_parse_salary_dash_range() -> None:
    salary = parse_salary("Зарплата: 130 000 - 190 000 ₽ на руки")
    assert salary == {"from": 130000, "to": 190000, "currency": "RUB"}


def test_parse_salary_open_ended() -> None:
    assert parse_salary("от 150 000 ₽") == {"from": 150000, "to": None, "currency": "RUB"}
    assert parse_salary("до 220 000 руб.") == {"from": None, "to": 220000, "currency": "RUB"}


def test_parse_salary_usd_with_suffix_k() -> None:
    salary = parse_salary("$3k - $5k per month")
    assert salary == {"from": 3000, "to": 5000, "currency": "USD"}


def test_parse_salary_ignores_experience_numbers() -> None:
    assert parse_salary("Опыт работы 5 лет, высшее образование") is None


def test_parse_salary_ignores_month_ranges() -> None:
    text = "Досвід у SEO від 2 років. Не менше 6-12міс досвіду з UK-гео. Оплата в ₽."
    assert parse_salary(text) is None


def test_parse_salary_ignores_percentages() -> None:
    assert parse_salary("Ставка 5 - 8 % от выручки, выплаты в ₽") is None


def test_parse_salary_range_with_currency_between_numbers() -> None:
    assert parse_salary("Salary: 100 000 ₽ - 150 000 ₽") == {
        "from": 100000,
        "to": 150000,
        "currency": "RUB",
    }


def test_clean_title_unwraps_board_noise() -> None:
    title, hint = clean_title("Требуется «Python-разработчик» (от 150 000 ₽)")
    assert title == "Python-разработчик"
    assert hint == "от 150 000 ₽"


def test_company_from_description() -> None:
    assert guess_company("Python-разработчик", "Компания «Уралкод» ищет специалиста") == "Уралкод"


def test_city_from_description() -> None:
    assert guess_city("Екатеринбург, Россия. Полный рабочий день.") == "Екатеринбург"


def test_experience_levels() -> None:
    assert guess_experience("Стажировка, без опыта") == "intern"
    assert guess_experience("Уровень Middle, продуктовая команда") == "middle"
    assert guess_experience("Senior backend engineer") == "senior"


def test_work_format() -> None:
    assert guess_work_format("Можно удалённо") == "remote"
    assert guess_work_format("Гибрид, 2 дня в офисе") == "hybrid"
    assert guess_work_format("Работа в офисе, полный день") == "office"


def test_language_detection() -> None:
    assert guess_language("Разработка REST API на FastAPI") == "ru"
    assert guess_language("Міжнародна студія шукає режисера монтажу") == "uk"
    assert guess_language("Senior backend engineer, remote") == "en"


def test_strip_html_and_normalize() -> None:
    html = "<p>Hello&nbsp;<b>world</b></p><script>x()</script>"
    assert strip_html(html) == "Hello world"
    assert normalize_key("  Python-разработчик,  Middle! ") == "python-разработчик middle"


def test_canonical_url_drops_tracking() -> None:
    url = "https://career.habr.com/vacancies/1000170001?utm_source=rss&utm_medium=feed#top"
    assert canonical_url(url) == "https://career.habr.com/vacancies/1000170001"


def test_extract_refs() -> None:
    refs = extract_refs(
        "https://hh.ru/vacancy/987654?from=feed",
        "Подробности: https://career.habr.com/vacancies/1000170506",
    )
    assert refs == ["hh:987654", "habr:1000170506"]
