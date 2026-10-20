"""Parsing helpers for timestamped application log lines."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, TextIO

_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_LEVEL_PATTERN = "|".join(_LEVELS)
_LOG_PATTERN = re.compile(
    rf"""
    ^\s*
    (?P<timestamp>
        \d{{4}}-\d{{2}}-\d{{2}}[ T]\d{{2}}:\d{{2}}:\d{{2}}
        (?:[.,]\d{{1,6}})?
        (?:Z|[+-]\d{{2}}:?\d{{2}})?
    )
    \s+
    (?:\[(?P<bracket_level>{_LEVEL_PATTERN})\]|(?P<plain_level>{_LEVEL_PATTERN}))
    \s+
    (?P<module>[\w./-]+)
    \s*[:\-]\s*
    (?P<message>.*?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class LogEvent:
    timestamp: str
    level: str
    module: str
    message: str
    source: str
    line_number: int


def iter_log_lines(path: str) -> Iterator[tuple[int, str]]:
    """Yield each source line and its one-based line number without loading the file."""
    with open(path, encoding="utf-8", errors="replace") as log_file:
        yield from iter_log_stream(log_file)


def iter_log_stream(log_file: TextIO) -> Iterator[tuple[int, str]]:
    """Yield numbered lines from an already-open log stream."""
    for line_number, line in enumerate(log_file, start=1):
        yield line_number, line.rstrip("\r\n")


def parse_line(line: str, source: str, line_number: int) -> LogEvent | None:
    """Parse a supported log format, returning None for lines that do not match."""
    match = _LOG_PATTERN.match(line)
    if match is None:
        return None

    timestamp = match.group("timestamp")
    timestamp_for_validation = timestamp.replace(",", ".")
    if timestamp_for_validation.endswith("Z"):
        timestamp_for_validation = f"{timestamp_for_validation[:-1]}+00:00"
    try:
        datetime.fromisoformat(timestamp_for_validation)
    except ValueError:
        return None

    level = match.group("bracket_level") or match.group("plain_level")
    return LogEvent(
        timestamp=timestamp,
        level=level.upper(),
        module=match.group("module"),
        message=match.group("message").strip(),
        source=source,
        line_number=line_number,
    )
