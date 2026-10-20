"""Counter-based analysis of parsed log events."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .parser import LogEvent


@dataclass(frozen=True, slots=True)
class Analysis:
    total_events: int
    error_count: int
    warning_count: int
    info_count: int
    other_count: int
    top_errors: tuple[tuple[str, int], ...]


def analyze_events(events: Iterable[LogEvent], top_n: int = 5) -> Analysis:
    """Count event levels and return the most frequent module/message error pairs."""
    if top_n < 1:
        raise ValueError("top_n must be at least 1")

    counts: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    total_events = 0
    for event in events:
        total_events += 1
        counts[event.level] += 1
        if event.level in {"ERROR", "CRITICAL"}:
            errors[f"{event.module}: {event.message}"] += 1

    return Analysis(
        total_events=total_events,
        error_count=counts["ERROR"] + counts["CRITICAL"],
        warning_count=counts["WARNING"],
        info_count=counts["INFO"],
        other_count=sum(
            count
            for level, count in counts.items()
            if level not in {"ERROR", "CRITICAL", "WARNING", "INFO"}
        ),
        top_errors=tuple(errors.most_common(top_n)),
    )
