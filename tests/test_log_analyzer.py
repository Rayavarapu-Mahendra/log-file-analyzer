import csv
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from threading import Thread
from pathlib import Path

from log_analyzer.analyzer import analyze_events
from log_analyzer.parser import iter_log_lines, parse_line
from log_analyzer.reports import format_summary, write_reports
from log_analyzer.cli import main
from log_analyzer.storage import iter_stored_events, store_events
from log_analyzer.web import LogDashboardServer, analyze_stream


class ParserTests(unittest.TestCase):
    def test_parses_plain_and_bracketed_levels(self):
        plain = parse_line(
            "2026-10-19 09:12:30 ERROR auth: Invalid token",
            "app.log",
            1,
        )
        bracketed = parse_line(
            "2026-10-19T09:13:02Z [WARNING] database - Slow query",
            "app.log",
            2,
        )

        self.assertIsNotNone(plain)
        self.assertEqual((plain.level, plain.module, plain.message), ("ERROR", "auth", "Invalid token"))
        self.assertIsNotNone(bracketed)
        self.assertEqual((bracketed.level, bracketed.module), ("WARNING", "database"))

    def test_rejects_invalid_timestamp_and_unrecognized_line(self):
        self.assertIsNone(parse_line("not a log entry", "app.log", 1))
        self.assertIsNone(
            parse_line("2026-99-19 09:12:30 ERROR auth: Bad date", "app.log", 2)
        )

    def test_reads_lines_as_numbered_iterator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.log"
            path.write_text("first\nsecond\n", encoding="utf-8")

            self.assertEqual(list(iter_log_lines(str(path))), [(1, "first"), (2, "second")])


class AnalysisTests(unittest.TestCase):
    def test_counts_levels_and_ranks_recurring_errors(self):
        events = [
            parse_line("2026-10-19 09:12:30 ERROR auth: Invalid token", "app.log", 1),
            parse_line("2026-10-19 09:12:31 ERROR auth: Invalid token", "app.log", 2),
            parse_line("2026-10-19 09:12:32 WARNING api: Slow response", "app.log", 3),
            parse_line("2026-10-19 09:12:33 INFO api: Request complete", "app.log", 4),
        ]
        analysis = analyze_events(event for event in events if event is not None)

        self.assertEqual(analysis.total_events, 4)
        self.assertEqual(analysis.error_count, 2)
        self.assertEqual(analysis.warning_count, 1)
        self.assertEqual(analysis.info_count, 1)
        self.assertEqual(analysis.top_errors, (("auth: Invalid token", 2),))

    def test_rejects_non_positive_top_n(self):
        with self.assertRaises(ValueError):
            analyze_events([], top_n=0)


class PersistenceAndReportTests(unittest.TestCase):
    def test_persists_events_and_writes_reports(self):
        event = parse_line(
            "2026-10-19 09:12:30 ERROR auth: Invalid token",
            "app.log",
            1,
        )
        self.assertIsNotNone(event)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "data" / "events.db"
            ingestion_id = store_events(database, "app.log", [event])
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    "SELECT level, module, message FROM log_events WHERE ingestion_id = ?",
                    (ingestion_id,),
                ).fetchone()
            self.assertEqual(row, ("ERROR", "auth", "Invalid token"))

            analysis = analyze_events([event])
            summary = format_summary("app.log", analysis, skipped_lines=1)
            text_path, csv_path = write_reports(
                root / "reports",
                "app.log",
                [event],
                summary,
            )
            self.assertIn("Unparsed lines: 1", text_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["message"], "Invalid token")

    def test_csv_escapes_formula_like_log_messages(self):
        event = parse_line(
            "2026-10-19 09:12:30 ERROR auth: =HYPERLINK(\"https://bad\")",
            "app.log",
            1,
        )
        self.assertIsNotNone(event)

        with tempfile.TemporaryDirectory() as directory:
            _, csv_path = write_reports(directory, "app.log", [event], "summary")
            with csv_path.open(encoding="utf-8", newline="") as csv_file:
                row = next(csv.DictReader(csv_file))

        self.assertEqual(row["message"], "'=HYPERLINK(\"https://bad\")")

    def test_store_and_read_events_without_materializing_input(self):
        event = parse_line(
            "2026-10-19 09:12:30 ERROR auth: Invalid token",
            "app.log",
            1,
        )
        self.assertIsNotNone(event)
        consumed_count = 0

        def events():
            nonlocal consumed_count
            for _ in range(1001):
                consumed_count += 1
                yield event

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "events.db"
            ingestion_id = store_events(database, "app.log", events())
            stored_count = sum(
                1 for _ in iter_stored_events(database, ingestion_id)
            )

        self.assertEqual(consumed_count, 1001)
        self.assertEqual(stored_count, 1001)


class CliTests(unittest.TestCase):
    def test_cli_summarizes_and_persists_sample_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "input.log"
            log_path.write_text(
                "2026-10-19 09:12:30 ERROR auth: Invalid token\n"
                "not a log entry\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        str(log_path),
                        "--database",
                        str(root / "events.db"),
                        "--report-dir",
                        str(root / "reports"),
                        "--app-log",
                        str(root / "analyzer.log"),
                    ]
                )

            self.assertEqual(exit_code, 0, stderr.getvalue())
            self.assertIn("Parsed events: 1", stdout.getvalue())
            self.assertIn("Unparsed lines: 1", stdout.getvalue())
            self.assertTrue((root / "reports" / "input_events.csv").exists())

    def test_cli_reports_missing_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        str(root / "missing.log"),
                        "--database",
                        str(root / "events.db"),
                        "--report-dir",
                        str(root / "reports"),
                        "--app-log",
                        str(root / "analyzer.log"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("Log analysis failed:", stderr.getvalue())
            self.assertFalse((root / "events.db").exists())


class WebDashboardTests(unittest.TestCase):
    def test_analyze_stream_returns_dashboard_summary_and_preview(self):
        content = (
            "2026-10-19 09:12:30 ERROR auth: Invalid token\n"
            "2026-10-19 09:12:31 ERROR auth: Invalid token\n"
            "not a log entry\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = analyze_stream(
                "upload.log",
                io.StringIO(content),
                Path(directory) / "events.db",
            )

        self.assertEqual(result["total_events"], 2)
        self.assertEqual(result["error_count"], 2)
        self.assertEqual(result["skipped_lines"], 1)
        self.assertEqual(result["top_errors"], [{"error": "auth: Invalid token", "count": 2}])
        self.assertEqual(len(result["events"]), 2)

    def test_dashboard_page_and_upload_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            server = LogDashboardServer(
                ("127.0.0.1", 0),
                Path(directory) / "events.db",
            )
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET", "/")
                page_response = connection.getresponse()
                page = page_response.read().decode("utf-8")
                self.assertEqual(page_response.status, 200)
                self.assertIn("Make sense of your logs.", page)
                self.assertIn('id="download-log" class="file-label" href="/sample.log"', page)
                self.assertIn(
                    "Click Analyze log to process it.",
                    page,
                )
                self.assertNotIn("Download 50-line sample", page)

                connection.request("GET", "/sample.log")
                sample_response = connection.getresponse()
                sample_contents = sample_response.read()
                self.assertEqual(sample_response.status, 200)
                self.assertIn("attachment; filename=\"sample.log\"", sample_response.getheader("Content-Disposition"))
                self.assertEqual(
                    sample_response.getheader("Content-Type"),
                    "application/octet-stream",
                )
                self.assertEqual(
                    sample_contents,
                    (Path(__file__).resolve().parents[1] / "sample.log").read_bytes(),
                )

                payload = json.dumps(
                    {
                        "filename": "folder\\upload.log",
                        "content": "2026-10-19 09:12:30 WARNING api: Slow response\n",
                    }
                )
                connection.request(
                    "POST",
                    "/api/analyze",
                    body=payload,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                result = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(result["source"], "upload.log")
                self.assertEqual(result["warning_count"], 1)
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
