"""Command line entry point: collect -> feed -> stats."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import httpx
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, func, select

from jobpilot import __version__
from jobpilot.config import Settings
from jobpilot.db import SourceRun, Vacancy, VacancyCluster, init_db, make_engine, session_scope
from jobpilot.normalize.dedupe import insert_vacancy
from jobpilot.sources import build_sources

console = Console()


def _open_db(args: argparse.Namespace, settings: Settings):
    engine = make_engine(args.db or settings.db_url)
    init_db(engine)
    return engine


def cmd_collect(args: argparse.Namespace, settings: Settings) -> int:
    engine = _open_db(args, settings)
    configs = settings.load_sources(args.source)
    if not configs:
        console.print("[yellow]no enabled sources in config/sources.yml[/yellow]")
        return 1

    rows: list[tuple[str, int, int, int, int, str]] = []
    with httpx.Client(timeout=settings.http_timeout, follow_redirects=True) as client:
        for source in build_sources(configs, client, settings.user_agent):
            started = time.monotonic()
            fetched = inserted = duplicates = errors = 0
            message = ""
            try:
                raws = source.fetch()
                fetched = len(raws)
                if args.limit:
                    raws = raws[: args.limit]
                with session_scope(engine) as session:
                    for raw in raws:
                        try:
                            result = insert_vacancy(
                                session,
                                raw,
                                priority=source.priority,
                                fuzzy_threshold=settings.fuzzy_threshold,
                                fuzzy_window_days=settings.fuzzy_window_days,
                            )
                        except Exception as exc:  # noqa: BLE001 - keep the run alive
                            errors += 1
                            message = f"{type(exc).__name__}: {exc}"
                            continue
                        if result.inserted:
                            inserted += 1
                            duplicates += int(result.merged)
                        else:
                            duplicates += 1
            except Exception as exc:  # noqa: BLE001 - one broken source must not stop others
                errors += 1
                message = f"{type(exc).__name__}: {exc}"

            elapsed = time.monotonic() - started
            with session_scope(engine) as session:
                session.add(
                    SourceRun(
                        source=source.id,
                        fetched=fetched,
                        inserted=inserted,
                        duplicates=duplicates,
                        errors=errors,
                        finished_at=datetime.now(UTC),
                        message=message[:500] or None,
                    )
                )
            rows.append((source.id, fetched, inserted, duplicates, errors, f"{elapsed:.1f}s"))
            console.print(
                f"  {source.id}: fetched={fetched} new={inserted} "
                f"dup={duplicates} errors={errors} ({elapsed:.1f}s)"
            )

    table = Table(title="collect summary")
    for column in ("source", "fetched", "new", "duplicates", "errors", "time"):
        table.add_column(column)
    for row in rows:
        table.add_row(*[str(value) for value in row])
    console.print(table)
    return 0


def _dup_counts(session: Session) -> dict[int, int]:
    rows = session.exec(
        select(Vacancy.cluster_id, func.count()).group_by(Vacancy.cluster_id)
    ).all()
    return {cluster_id: count for cluster_id, count in rows if cluster_id is not None}


def cmd_feed(args: argparse.Namespace, settings: Settings) -> int:
    engine = _open_db(args, settings)
    items: list[dict] = []
    with session_scope(engine) as session:
        stmt = select(Vacancy).join(VacancyCluster, Vacancy.id == VacancyCluster.primary_id)
        if args.remote:
            stmt = stmt.where(Vacancy.work_format == "remote")
        if args.level:
            stmt = stmt.where(Vacancy.experience.in_(args.level))
        stmt = stmt.order_by(
            func.coalesce(Vacancy.published_at, Vacancy.fetched_at).desc()
        ).limit(args.limit)
        duplicates = _dup_counts(session)
        for vacancy in session.exec(stmt).all():
            published = vacancy.published_at or vacancy.fetched_at
            items.append(
                {
                    "id": vacancy.id,
                    "source": vacancy.source,
                    "title": vacancy.title,
                    "company": vacancy.company,
                    "salary": vacancy.salary_label,
                    "city": vacancy.city,
                    "work_format": vacancy.work_format,
                    "experience": vacancy.experience,
                    "language": vacancy.language,
                    "published_at": published.isoformat() if published else None,
                    "published_label": published.strftime("%d.%m") if published else "-",
                    "url": vacancy.url,
                    "duplicates": duplicates.get(vacancy.cluster_id or 0, 1) - 1,
                }
            )

    if args.json:
        console.print_json(json.dumps(items, ensure_ascii=False))
        return 0

    if not items:
        console.print("[yellow]feed is empty - run `jobpilot collect` first[/yellow]")
        return 1

    table = Table(title=f"jobpilot feed ({len(items)})")
    table.add_column("date", style="dim", width=8)
    table.add_column("title", overflow="fold")
    table.add_column("salary", width=19, overflow="fold")

    width = console.width
    show_where = width >= 92
    show_level = width >= 100
    show_source = width >= 118
    if show_where:
        table.add_column("where", width=16, overflow="fold")
    if show_level:
        table.add_column("lvl", width=7)
    if show_source:
        table.add_column("src", width=14)
        table.add_column("dup", width=4, justify="right")

    for item in items:
        row = [
            item["published_label"],
            f"{item['title']}\n[dim]{item['company'] or '-'}[/dim]",
            item["salary"],
        ]
        if show_where:
            row.append(", ".join(filter(None, [item["city"], item["work_format"]])) or "-")
        if show_level:
            row.append(item["experience"] or "-")
        if show_source:
            row.extend([item["source"], str(item["duplicates"])])
        table.add_row(*row)
    console.print(table)
    return 0


def cmd_stats(args: argparse.Namespace, settings: Settings) -> int:
    engine = _open_db(args, settings)
    with session_scope(engine) as session:
        total = session.exec(select(func.count()).select_from(Vacancy)).one()
        clusters = session.exec(
            select(func.count())
            .select_from(VacancyCluster)
            .where(VacancyCluster.primary_id.is_not(None))
        ).one()
        by_source = session.exec(
            select(Vacancy.source, func.count())
            .group_by(Vacancy.source)
            .order_by(func.count().desc())
        ).all()
        by_level = session.exec(
            select(Vacancy.experience, func.count())
            .group_by(Vacancy.experience)
            .order_by(func.count().desc())
        ).all()
        by_format = session.exec(
            select(Vacancy.work_format, func.count())
            .group_by(Vacancy.work_format)
            .order_by(func.count().desc())
        ).all()
        runs = session.exec(select(SourceRun).order_by(SourceRun.id.desc()).limit(10)).all()

    summary = Table(title="jobpilot stats")
    summary.add_column("metric")
    summary.add_column("value", justify="right")
    summary.add_row("vacancies stored", str(total))
    summary.add_row("unique clusters", str(clusters))
    summary.add_row("duplicates collapsed", str(max(total - clusters, 0)))
    console.print(summary)

    groups = (("by source", by_source), ("by level", by_level), ("by format", by_format))
    for title, rows in groups:
        table = Table(title=title)
        table.add_column("key")
        table.add_column("count", justify="right")
        for key, count in rows:
            table.add_row(str(key or "-"), str(count))
        console.print(table)

    if runs:
        history = Table(title="recent runs")
        for column in ("source", "fetched", "new", "dup", "errors", "when"):
            history.add_column(column)
        for run in runs:
            history.add_row(
                run.source,
                str(run.fetched),
                str(run.inserted),
                str(run.duplicates),
                str(run.errors),
                (run.finished_at or run.started_at).strftime("%d.%m %H:%M"),
            )
        console.print(history)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobpilot", description="personal vacancy pipeline")
    parser.add_argument("--version", action="version", version=f"jobpilot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="fetch sources and store vacancies")
    collect.add_argument("--source", action="append", metavar="ID", help="only these sources")
    collect.add_argument("--limit", type=int, default=0, help="max items per source")
    collect.add_argument("--db", help="override database url")
    collect.set_defaults(func=cmd_collect)

    feed = sub.add_parser("feed", help="show deduplicated vacancies")
    feed.add_argument("--limit", type=int, default=20)
    feed.add_argument("--remote", action="store_true", help="only remote vacancies")
    feed.add_argument("--level", action="append", metavar="LEVEL", help="middle/senior/...")
    feed.add_argument("--json", action="store_true", help="machine readable output")
    feed.add_argument("--db", help="override database url")
    feed.set_defaults(func=cmd_feed)

    stats = sub.add_parser("stats", help="coverage and source health")
    stats.add_argument("--db", help="override database url")
    stats.set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args, Settings())


if __name__ == "__main__":
    raise SystemExit(main())
