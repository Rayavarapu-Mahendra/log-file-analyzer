# Log File Analyzer & Error Monitoring Tool

A Python command-line utility that streams a log file line by line, parses common
timestamped entries, summarizes event levels and recurring errors, stores parsed
events in SQLite, and writes text and CSV reports. It uses only the Python
standard library. Events are inserted in batches and read back from SQLite in
batches, so the full input does not need to remain in memory.

## Supported input

Each parsed line must contain an ISO-style timestamp, a recognized level, a
module, and a message. Both of these forms are supported:

```text
2026-10-19 09:12:30 ERROR auth: Invalid login token
2026-10-19T09:13:02Z [WARNING] database - Connection pool is nearly full
```

Recognized levels are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.
Invalid or unsupported lines are skipped from event storage and counted in the
summary as unparsed lines.

## Run

From the project directory, use the included virtual environment:

```powershell
.\Scripts\python.exe -m log_analyzer sample.log
```

The command prints a summary and creates:

- `reports\sample_report.txt` — analysis summary and top recurring errors
- `reports\sample_events.csv` — parsed event details
- `log_analysis.db` — SQLite ingestion and event tables
- `logs\log_analyzer.log` — application execution log

CSV text fields that begin with spreadsheet formula characters are prefixed
with an apostrophe to prevent spreadsheet applications from evaluating log
content as formulas.

Options:

```powershell
.\Scripts\python.exe -m log_analyzer path\to\application.log `
  --database path\to\events.db `
  --report-dir path\to\reports `
  --app-log path\to\analyzer.log `
  --top 10
```

## View results in a web page

Start the local dashboard:

```powershell
.\Scripts\python.exe -m log_analyzer.web
```

Open `http://127.0.0.1:8000` in your browser. The sample log is analyzed when
the page loads. Use **Choose file** and **Analyze log** to view another `.log`
or `.txt` file. Selecting a file automatically starts its analysis; **Analyze
log** can be used to run it again. Use **Download sample log** to save the
included `sample.log` when no file has been selected. After selecting an
uploaded file, the download link changes to **Download _filename_** and saves
that selected file instead. The dashboard shows level totals, recurring errors,
and a filterable preview of parsed events. The full results are stored in the
same SQLite database as CLI runs.

For a larger upload test, use the provided [`sample1.log`](./sample1.log) file.
It contains 50 log entries, recurring errors, and a mix of supported severity
levels.

The web server binds to `127.0.0.1` by default so it is available only on your
computer. Uploaded logs are limited to 5 MiB. For a different port or database:

```powershell
.\Scripts\python.exe -m log_analyzer.web --port 8080 --database path\to\events.db
```

## Run tests

```powershell
.\Scripts\python.exe -m unittest discover -s tests -v
```

## Project layout

- `log_analyzer\parser.py` — streaming file reads and regex parsing
- `log_analyzer\analyzer.py` — level counts and `Counter`-based recurring errors
- `log_analyzer\storage.py` — SQLite schema and persistence
- `log_analyzer\reports.py` — text and CSV report output
- `log_analyzer\cli.py` — command-line interface and application logging
- `log_analyzer\web.py` and `log_analyzer\web.html` — local web dashboard
- `tests\` — parser, analysis, storage, and report tests
