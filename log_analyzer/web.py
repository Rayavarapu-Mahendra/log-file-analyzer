"""Local web dashboard for analyzing uploaded log files."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import islice
from io import StringIO
from pathlib import Path
from typing import Any, TextIO

from .analyzer import analyze_events
from .parser import iter_log_stream, parse_line
from .storage import iter_stored_events, store_events

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_PATH = _PROJECT_ROOT / "sample.log"
_PAGE_PATH = Path(__file__).with_name("web.html")
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_MAX_REQUEST_BYTES = 12 * 1024 * 1024
_EVENT_PREVIEW_LIMIT = 500
logger = logging.getLogger("log_analyzer.web")


def analyze_stream(source: str, stream: TextIO, database: str | Path) -> dict[str, Any]:
    """Analyze a text stream, persist its events, and return dashboard data."""
    skipped_lines = 0

    def parsed_events():
        nonlocal skipped_lines
        for line_number, line in iter_log_stream(stream):
            event = parse_line(line, source, line_number)
            if event is None:
                skipped_lines += 1
            else:
                yield event

    ingestion_id = store_events(database, source, parsed_events())
    analysis = analyze_events(iter_stored_events(database, ingestion_id))
    preview = [
        {
            "timestamp": event.timestamp,
            "level": event.level,
            "module": event.module,
            "message": event.message,
            "line_number": event.line_number,
        }
        for event in islice(
            iter_stored_events(database, ingestion_id),
            _EVENT_PREVIEW_LIMIT,
        )
    ]
    return {
        "source": source,
        "ingestion_id": ingestion_id,
        "total_events": analysis.total_events,
        "error_count": analysis.error_count,
        "warning_count": analysis.warning_count,
        "info_count": analysis.info_count,
        "other_count": analysis.other_count,
        "skipped_lines": skipped_lines,
        "top_errors": [
            {"error": error, "count": count}
            for error, count in analysis.top_errors
        ],
        "events": preview,
        "preview_limit": _EVENT_PREVIEW_LIMIT,
    }


def _safe_filename(filename: str) -> str:
    """Keep only a display filename; never treat the upload name as a path."""
    return filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()


class LogDashboardServer(ThreadingHTTPServer):
    """HTTP server configured with the database path used by the dashboard."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], database: str | Path):
        self.database = Path(database)
        super().__init__(server_address, LogDashboardHandler)


class LogDashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard and its local analysis endpoints."""

    server: LogDashboardServer

    def do_GET(self) -> None:
        if self.path == "/":
            self._send_page()
        elif self.path == "/api/sample":
            self._analyze_sample()
        elif self.path == "/sample.log":
            self._download_sample(_SAMPLE_PATH)
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self._send_json(404, {"error": "Not found"})
            return

        content_length = self.headers.get("Content-Length")
        try:
            request_length = int(content_length or "")
        except ValueError:
            self._send_json(411, {"error": "A valid Content-Length header is required"})
            return
        if request_length < 1:
            self._send_json(400, {"error": "Request body cannot be empty"})
            return
        if request_length > _MAX_REQUEST_BYTES:
            self.close_connection = True
            self._send_json(413, {"error": "Request is too large"})
            return

        try:
            payload = json.loads(self.rfile.read(request_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Request body must be valid UTF-8 JSON"})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "Request body must be a JSON object"})
            return

        filename = payload.get("filename")
        content = payload.get("content")
        if not isinstance(filename, str) or not _safe_filename(filename):
            self._send_json(400, {"error": "A filename is required"})
            return
        if not isinstance(content, str):
            self._send_json(400, {"error": "Log content must be a string"})
            return
        if len(content.encode("utf-8")) > _MAX_UPLOAD_BYTES:
            self._send_json(413, {"error": "Log files must be 5 MiB or smaller"})
            return

        safe_name = _safe_filename(filename)
        try:
            result = analyze_stream(
                safe_name,
                StringIO(content),
                self.server.database,
            )
        except (OSError, sqlite3.Error):
            logger.exception("Web analysis failed for %s", safe_name)
            self._send_json(500, {"error": "Unable to analyze this log file"})
            return
        self._send_json(200, result)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _analyze_sample(self) -> None:
        try:
            with _SAMPLE_PATH.open(encoding="utf-8", errors="replace") as stream:
                result = analyze_stream(_SAMPLE_PATH.name, stream, self.server.database)
        except (OSError, sqlite3.Error):
            logger.exception("Unable to analyze bundled sample log")
            self._send_json(500, {"error": "Unable to analyze the sample log"})
            return
        self._send_json(200, result)

    def _download_sample(self, sample_path: Path) -> None:
        try:
            sample = sample_path.read_bytes()
        except OSError:
            logger.exception("Unable to read bundled sample log: %s", sample_path)
            self._send_json(500, {"error": "Sample log file is unavailable"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{sample_path.name}"',
        )
        self.send_header("Content-Length", str(len(sample)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(sample)

    def _send_page(self) -> None:
        try:
            page = _PAGE_PATH.read_bytes()
        except OSError:
            logger.exception("Unable to read dashboard page")
            self._send_json(500, {"error": "Dashboard page is unavailable"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(page)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the local web dashboard for log analysis."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface to bind to (default: 127.0.0.1; local machine only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("log_analysis.db"),
        help="SQLite database path (default: log_analysis.db)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        build_parser().error("--port must be between 1 and 65535")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        with LogDashboardServer((args.host, args.port), args.database) as server:
            logger.info(
                "Dashboard available at http://%s:%d",
                args.host,
                args.port,
            )
            print(f"Dashboard running at http://{args.host}:{args.port}")
            print("Press Ctrl+C to stop the server.")
            server.serve_forever()
    except OSError as exc:
        logger.error("Unable to start dashboard: %s", exc)
        print(f"Unable to start dashboard: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
