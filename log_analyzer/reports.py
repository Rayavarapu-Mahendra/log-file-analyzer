"""Console, text, and CSV report generation."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .analyzer import Analysis
from .parser import LogEvent


def format_summary(source: str, analysis: Analysis, skipped_lines: int) -> str:
    lines = [
        f"Log analysis for: {source}",
        f"Parsed events: {analysis.total_events}",
        f"Errors (ERROR/CRITICAL): {analysis.error_count}",
        f"Warnings: {analysis.warning_count}",
        f"Info: {analysis.info_count}",
        f"Other levels: {analysis.other_count}",
        f"Unparsed lines: {skipped_lines}",
        "",
        "Top recurring errors:",
    ]
    if analysis.top_errors:
        lines.extend(f"  {count}x  {error}" for error, count in analysis.top_errors)
    else:
        lines.append("  None")
    return "\n".join(lines)


def write_reports(
    report_dir: str | Path,
    source: str | Path,
    events: Iterable[LogEvent],
    summary: str,
) -> tuple[Path, Path]:
    """Write a human-readable summary and a CSV containing parsed events."""
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    stem = Path(source).stem
    text_path = report_path / f"{stem}_report.txt"
    csv_path = report_path / f"{stem}_events.csv"

    text_path.write_text(f"{summary}\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "timestamp",
                "level",
                "module",
                "message",
                "source",
                "line_number",
            ],
        )
        writer.writeheader()
        for event in events:
            writer.writerow(
                {
                    "timestamp": _spreadsheet_safe(event.timestamp),
                    "level": _spreadsheet_safe(event.level),
                    "module": _spreadsheet_safe(event.module),
                    "message": _spreadsheet_safe(event.message),
                    "source": _spreadsheet_safe(event.source),
                    "line_number": event.line_number,
                }
            )
    return text_path, csv_path


def _spreadsheet_safe(value: str) -> str:
    """Prevent log content from being interpreted as a spreadsheet formula."""
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
