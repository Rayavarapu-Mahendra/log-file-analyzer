# Log File Analyzer & Error Monitoring Tool

A lightweight Python tool for parsing application logs, spotting recurring errors, and exploring results in a local web dashboard. It streams log files line by line, saves parsed events to SQLite, and creates text and CSV reports—using only the Python standard library.

## Features

- Parse timestamped log entries with `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL` levels.
- Summarize event counts and rank recurring `ERROR` and `CRITICAL` messages.
- Process large files incrementally instead of loading the whole file into memory.
- Store each analysis in SQLite and export readable text and CSV reports.
- Explore results in a browser with a local dashboard, log upload, and filterable event preview.
- Protect CSV exports from spreadsheet formula injection.

## Requirements

- Python 3.10 or newer
- No third-party Python packages

## Get started

Clone the repository and open its directory:

```bash
git clone https://github.com/Rayavarapu-Mahendra/log-file-analyzer.git
cd log-file-analyzer
```

Analyze the included sample log:

```bash
python -m log_analyzer sample.log
```

The command prints a summary and creates:

| File | Description |
| --- | --- |
| `reports/sample_report.txt` | Summary and most frequent errors |
| `reports/sample_events.csv` | Parsed event details |
| `log_analysis.db` | SQLite database containing the analysis |
| `logs/log_analyzer.log` | Application execution log |

Generated reports, logs, and the database are excluded from version control.

## Supported log format

Each line must contain a valid ISO-style timestamp, a supported level, a module name, and a message. The level may be plain or in square brackets; either a colon or hyphen can separate the module from the message.

```text
2026-10-19 09:12:30 ERROR auth: Invalid login token
2026-10-19T09:13:02Z [WARNING] database - Connection pool is nearly full
```

Lines that do not match the supported format are skipped and counted as unparsed. `DEBUG` events are parsed and stored; the summary groups levels other than `ERROR`, `CRITICAL`, `WARNING`, and `INFO` under “Other levels.”

## Command-line options

Pass a log path as the required first argument. The output paths and number of recurring errors can be customized:

```bash
python -m log_analyzer path/to/application.log \
  --database path/to/events.db \
  --report-dir path/to/reports \
  --app-log path/to/analyzer.log \
  --top 10
```

| Option | Default | Description |
| --- | --- | --- |
| `--database` | `log_analysis.db` | SQLite database file |
| `--report-dir` | `reports` | Directory for text and CSV reports |
| `--app-log` | `logs/log_analyzer.log` | Application log file |
| `--top` | `5` | Number of recurring errors to display |

## Web dashboard

Start the local dashboard:

```bash
python -m log_analyzer.web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. The dashboard analyzes the included sample log when it loads. Choose a `.log` or `.txt` file to analyze it, then view level totals, recurring errors, and a filterable preview of parsed events. The preview shows up to 500 events; all parsed events are stored in SQLite.

Uploads are limited to 5 MiB. The server binds to `127.0.0.1` by default, so it is available only on your computer. To change the port or database file:

```bash
python -m log_analyzer.web --port 8080 --database path/to/events.db
```

Use `--host` to choose a different interface to bind to.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Project structure

```text
log_analyzer/
├── analyzer.py    # Event totals and recurring-error analysis
├── cli.py         # Command-line interface and application logging
├── parser.py      # Streaming log reads and line parsing
├── reports.py     # Text and CSV report generation
├── storage.py     # SQLite persistence
├── web.html       # Dashboard page
└── web.py         # Local dashboard server
sample.log         # Example input
tests/             # Unit and integration tests
```
