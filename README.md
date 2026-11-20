# jobpilot

A personal vacancy pipeline: collect postings from many job boards, collapse
duplicates into clusters, and (next) score them against a candidate profile and
route the best ones to a review queue.

> **По-русски, коротко.** Собирает вакансии из нескольких источников (RSS/JSON API),
> склеивает дубли в кластеры, разбирает зарплату/город/грейд/формат и показывает
> единый фид в CLI. Дальше по плану: скоринг по 4 «персонам», генерация писем
> с валидацией фактов, трекер откликов. Сделано под рынок РФ (Екатеринбург + удалёнка).

[![CI](https://github.com/artur-stark/jobpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/artur-stark/jobpilot/actions/workflows/ci.yml)

---

## Status

| Step | Scope | State |
| --- | --- | --- |
| 1 | Generic `feed` (RSS/Atom) and `jsonapi` adapters, declarative YAML mapping | done |
| 2 | Dedupe: exact fingerprint + fuzzy merge, cluster with a primary record | done |
| 3 | hh.ru: 16 search RSS feeds (Ekb `area 3`, remote RF `area 113`), no app needed | done |
| 4 | Hard filters + scoring against 4 personas (python / js / embedded / qa) | next |
| 5 | Cover letters with a fact validator, Telegram review queue | planned |
| 6 | Tracker with follow-up reminders and funnel analytics | planned |

### hh.ru without an application

`api.hh.ru/vacancies` answers **403** to anonymous requests — even for a single
vacancy — and an app on `dev.hh.ru` goes through moderation. But hh also exposes
every search as an **RSS feed**, and that one needs no token, app or approval:

```bash
curl 'https://hh.ru/search/vacancy/rss?text=python&area=3&professional_role=96&order_by=publication_time'
# 20 newest postings, summary with labelled fields
```

Hence `kind: hh_rss`: 20 items per query, so the config runs 16 narrow queries
(8 stacks in Ekaterinburg + 6 remote across RF + 2 salary-only slices), and the
dedupe layer collapses the overlap. Verified live: **259 hh postings, 100% with
company and city, 49% with a salary range, 0 errors**. The app registration is
still worth doing later (structured fields, search depth 2000), but nothing in
the pipeline waits for moderation.

### Why not a "mass apply" bot

Volume is not the bottleneck: identical replies convert at 1–2%, targeted ones
at 10–25%. The pipeline is therefore built around **filtering, explaining and
preparing**, with a human approving each outgoing message. Anti-bot limits and
account bans are treated as a design constraint, not an obstacle to work around.

---

## Architecture

```
  sources/                        normalize/                  db/
  ├── feed.py     (RSS)      ─┐   ├── extract.py  (heuristics)  ├── Vacancy
  ├── hh_rss.py   (hh.ru)    ─┼─▶ ├── fingerprint.py            ├── VacancyCluster
  ├── jsonapi.py  (JSON)     ─┤   └── dedupe.py   (clusters)    └── SourceRun
  ├── fake.py     (demo)     ─┘                                 (SQLite, WAL)
  └── registry.py
                                     │
                                     ▼
                               cli.py: collect | feed | stats
```

Everything downstream of `RawVacancy` is source-agnostic: adding a board is a
YAML edit, not a new module.

```yaml
# config/sources.yml
sources:
  - id: hh_ekb_python              # hh.ru search RSS: no app, no token
    kind: hh_rss
    priority: 15                   # lower wins when the same job comes twice
    url: https://hh.ru/search/vacancy/rss?text=python&area=3&professional_role=96&order_by=publication_time

  - id: hh_remote_python
    kind: hh_rss
    priority: 15
    url: https://hh.ru/search/vacancy/rss?text=python&area=113&work_format=REMOTE&professional_role=96
    defaults: {work_format: remote} # the RSS summary carries no work format

  - id: habr_python
    kind: feed
    priority: 20
    url: https://career.habr.com/vacancies/rss?q=python&remote=true

  - id: trudvsem
    kind: jsonapi
    url: https://opendata.trudvsem.ru/api/v1/vacancies
    items_path: results.vacancies
    mapping:
      external_id: vacancy.id
      title: vacancy.job-name
      company: vacancy.company.name
```

---

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/jobpilot collect            # fetch all enabled sources
.venv/bin/jobpilot feed --limit 20    # deduplicated feed
.venv/bin/jobpilot feed --remote --level middle
.venv/bin/jobpilot stats              # coverage and source health
```

First run against five live sources (Nov 2026): 284 postings fetched,
256 unique clusters, 28 duplicates collapsed, 0 errors. After adding the hh.ru
RSS layer: 545 postings, 392 unique clusters, 153 duplicates collapsed.

## Dedupe

The same job usually arrives from several boards with slightly different text,
so hashing alone is not enough:

1. `source + external_id` — the same item seen again is refreshed, not duplicated.
2. **Exact** — `sha256(company | title | description[:1500])` after aggressive
   normalisation (`Python-разработчик` == `python разработчик`).
3. **Fuzzy** — `rapidfuzz.token_set_ratio ≥ 92` on `company + title` inside a
   14-day window; different seniority levels are never merged.
4. Every posting belongs to a `vacancy_cluster` with one **primary** record
   chosen by source priority (company/ATS > curated board > aggregator), so the
   feed shows a job once and keeps the other links as provenance.

## Extraction

Feeds are messy, so fields are recovered heuristically and pinned by tests:

| Field | How |
| --- | --- |
| salary | currency must be adjacent to the number; rejects `6-12міс`, `5-8 %`, implausible amounts |
| company | RSS `<author>`, `Компания «X» ищет`, `Role → Company`, hh label `Вакансия компании:` |
| level | lead / senior / middle / junior / intern keyword rules |
| format | remote / hybrid / office |
| city | `City, Россия` patterns, hh label `Регион:` |
| language | ru / uk / en by character statistics |
| refs | `hh:123`, `habr:1000170506`, … extracted for cross-source linking |

hh.ru summaries are `Label: value` blocks whose line breaks are already collapsed
by the time they reach us, so `parse_labeled_block` splits them by the *next known
label* instead of by newlines: `Вакансия компании: X Создана: Y Регион: Z` still
yields three fields.

## Tests

```bash
.venv/bin/pytest      # 43 tests
.venv/bin/ruff check src tests
```

## Non-goals

- No HTML scraping by default: RSS and open JSON APIs cover most of the market;
  an adapter for a specific site is added only when the data is unique.
- No mass automated applications, no proxy rotation, no fake accounts.
- No credentials in the database: tokens live in `.env` (git-ignored).

## License

MIT — see [LICENSE](LICENSE).
