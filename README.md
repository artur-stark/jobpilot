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
| 3 | hh.ru search via app token (Ekb `area 3` / `1261`, `work_format REMOTE`) | next |
| 4 | Hard filters + scoring against 4 personas (python / js / embedded / qa) | planned |
| 5 | Cover letters with a fact validator, Telegram review queue | planned |
| 6 | Tracker with follow-up reminders and funnel analytics | planned |

### Why not a "mass apply" bot

Volume is not the bottleneck: identical replies convert at 1–2%, targeted ones
at 10–25%. The pipeline is therefore built around **filtering, explaining and
preparing**, with a human approving each outgoing message. Anti-bot limits and
account bans are treated as a design constraint, not an obstacle to work around.

---

## Architecture

```
  sources/                     normalize/                  db/
  ├── feed.py     (RSS)   ─┐   ├── extract.py  (heuristics)  ├── Vacancy
  ├── jsonapi.py  (JSON)  ─┼─▶ ├── fingerprint.py            ├── VacancyCluster
  ├── fake.py     (demo)  ─┘   └── dedupe.py   (clusters)    └── SourceRun
  └── registry.py                                            (SQLite, WAL)
                                     │
                                     ▼
                               cli.py: collect | feed | stats
```

Everything downstream of `RawVacancy` is source-agnostic: adding a board is a
YAML edit, not a new module.

```yaml
# config/sources.yml
sources:
  - id: habr_python
    kind: feed
    priority: 20                     # lower wins when the same job comes twice
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
256 unique clusters, 28 duplicates collapsed, 0 errors.

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
| company | RSS `<author>`, `Компания «X» ищет`, `Role → Company` |
| level | lead / senior / middle / junior / intern keyword rules |
| format | remote / hybrid / office |
| city | `City, Россия` patterns |
| language | ru / uk / en by character statistics |
| refs | `hh:123`, `habr:1000170506`, … extracted for cross-source linking |

## Tests

```bash
.venv/bin/pytest      # 32 tests
.venv/bin/ruff check src tests
```

## Non-goals

- No HTML scraping by default: RSS and open JSON APIs cover most of the market;
  an adapter for a specific site is added only when the data is unique.
- No mass automated applications, no proxy rotation, no fake accounts.
- No credentials in the database: tokens live in `.env` (git-ignored).

## License

MIT — see [LICENSE](LICENSE).
