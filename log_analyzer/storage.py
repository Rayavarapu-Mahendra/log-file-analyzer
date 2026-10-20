"""SQLite persistence for parsed events and ingestion runs."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator

from .parser import LogEvent

_BATCH_SIZE = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS log_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_id INTEGER NOT NULL REFERENCES ingestions(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    module TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    line_number INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_events_ingestion_level
    ON log_events(ingestion_id, level);
"""


def store_events(database: str | Path, source: str, events: Iterable[LogEvent]) -> int:
    """Persist one ingestion and its parsed events; return the ingestion ID."""
    database_path = Path(database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    event_iterator = iter(events)
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(_SCHEMA)
            cursor = connection.execute(
                "INSERT INTO ingestions (source) VALUES (?)",
                (source,),
            )
            ingestion_id = cursor.lastrowid
            insert_sql = """
                INSERT INTO log_events
                    (ingestion_id, timestamp, level, module, message, source, line_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            while batch := list(islice(event_iterator, _BATCH_SIZE)):
                connection.executemany(
                    insert_sql,
                    [
                        (
                            ingestion_id,
                            event.timestamp,
                            event.level,
                            event.module,
                            event.message,
                            event.source,
                            event.line_number,
                        )
                        for event in batch
                    ],
                )
    return ingestion_id


def iter_stored_events(database: str | Path, ingestion_id: int) -> Iterator[LogEvent]:
    """Yield one ingestion's events from SQLite without loading them all at once."""
    with closing(sqlite3.connect(database)) as connection:
        cursor = connection.execute(
            """
            SELECT timestamp, level, module, message, source, line_number
            FROM log_events
            WHERE ingestion_id = ?
            ORDER BY line_number
            """,
            (ingestion_id,),
        )
        while rows := cursor.fetchmany(_BATCH_SIZE):
            for row in rows:
                yield LogEvent(*row)
