"""Command-line entry point for the log analyzer."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from .analyzer import analyze_events
from .parser import iter_log_stream, parse_line
from .reports import format_summary, write_reports
from .storage import iter_stored_events, store_events

logger = logging.getLogger("log_analyzer")


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse, analyze, and report on an application log file."
    )
    parser.add_argument("log_file", type=Path, help="path to the input .log file")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("log_analysis.db"),
        help="SQLite database path (default: log_analysis.db)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="directory for text and CSV reports (default: reports)",
    )
    parser.add_argument(
        "--app-log",
        type=Path,
        default=Path("logs/log_analyzer.log"),
        help="application log path (default: logs/log_analyzer.log)",
    )
    parser.add_argument(
        "--top",
        type=_positive_int,
        default=5,
        help="number of recurring errors to show (default: 5)",
    )
    return parser


def _configure_logging(path: Path) -> logging.FileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = None
    try:
        handler = _configure_logging(args.app_log)

        skipped_lines = 0

        with args.log_file.open(encoding="utf-8", errors="replace") as log_file:
            def parsed_events():
                nonlocal skipped_lines
                for line_number, line in iter_log_stream(log_file):
                    event = parse_line(line, str(args.log_file), line_number)
                    if event is None:
                        skipped_lines += 1
                    else:
                        yield event

            ingestion_id = store_events(
                args.database,
                str(args.log_file),
                parsed_events(),
            )
        analysis = analyze_events(
            iter_stored_events(args.database, ingestion_id),
            args.top,
        )
        summary = format_summary(str(args.log_file), analysis, skipped_lines)
        text_path, csv_path = write_reports(
            args.report_dir,
            args.log_file,
            iter_stored_events(args.database, ingestion_id),
            summary,
        )

        print(summary)
        print(f"\nText report: {text_path}")
        print(f"CSV report: {csv_path}")
        print(f"SQLite database: {args.database} (ingestion {ingestion_id})")
        logger.info(
            "Analyzed %s: %d parsed events, %d unparsed lines, ingestion %d",
            args.log_file,
            analysis.total_events,
            skipped_lines,
            ingestion_id,
        )
        return 0
    except (OSError, sqlite3.Error) as exc:
        logger.exception("Log analysis failed for %s", args.log_file)
        print(f"Log analysis failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()
