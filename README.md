# speedtest-logger

End "the internet is slow" arguments with data.

Logs latency, DNS time, and download speed on a schedule, then charts it all
into a shareable HTML report — so you can show a client (or an ISP) exactly
when the connection dips, instead of debating vibes.

Built for field engineers troubleshooting intermittent internet complaints.
Zero dependencies.

## Quick start

```bash
# Test every 15 minutes, 96 times (24 hours)
python speedlog.py --interval 15 --count 96 --label "Branch office"

# Build the chart report
python speed_report.py

# SLA-style outage & degradation analysis (Markdown + HTML)
python outage_report.py
```

Open `speed.html`. That's your evidence.

## How it works

- **Latency** — TCP connect time to 1.1.1.1:443 (last-mile latency proxy)
- **DNS** — resolution time for a test domain
- **Download** — timed 10 MB download, converted to Mbps
- Every result lands in `speedlog.csv` with a UTC timestamp

## Outage & degradation analysis

`outage_report.py` reads `speedlog.csv` and produces an SLA-style summary —
useful when you need "the internet was down for 40 minutes on Tuesday"
instead of a chart.

```bash
python outage_report.py
python outage_report.py --gap-minutes 30 --min-mbps 100 --consecutive 12
python outage_report.py --webhook-url https://hooks.example.com/alert
```

| Flag | Default | Meaning |
|---|---|---|
| `--gap-minutes` | 15 | Outage = gap with no successful test longer than this. Set to ~2x your logging interval so one missed test doesn't count as an outage. |
| `--min-mbps` | 50 | Sustained-degradation threshold: download below this… |
| `--consecutive` | 6 | …for this many tests in a row counts as a degradation episode |
| `--csv` | speedlog.csv | Input log |
| `--md` / `--html` | outage_report.md / outage.html | Output reports (git-ignored) |
| `--webhook-url` | — | POST a JSON alert per NEW outage/degradation window |
| `--state` | .outage_state.json | State file (git-ignored) tracking the last analyzed timestamp |

What counts:

- A **successful test** is one with a recorded `download_mbps` — a test with
  ping OK but download failed folds into the outage window.
- **Uptime %** = (log period − total outage time) / log period. The log period
  runs from the first to the last row in the CSV.
- Windows ending **after** the last analyzed timestamp are "new". A trailing
  window with no successful test by log end is marked **ongoing**.

Example output (`outage_report.md`):

```markdown
# Outage & Degradation Report

- Log period: 2026-10-14 00:00 UTC → 2026-10-14 05:45 UTC (24 tests, 21 successful)
- **Uptime: 82.61%** (60 min of outage)
- Longest outage: 60 min
- Tests at/above 50 Mbps: 71.4%
- Degradation episodes (< 50 Mbps x 6 in a row): 1

## Outage windows (1)

| Start (UTC) | End (UTC) | Duration | Status |
|---|---|---|---|
| 2026-10-14 01:45 UTC | 2026-10-14 02:45 UTC | 60 min | closed |
```

**Webhook alerts** (`--webhook-url`): POSTs one JSON payload per new window,
e.g. `{"source": "speedtest-logger/outage_report", "type": "outage",
"start": "2026-10-14T01:45:00Z", "end": "2026-10-14T02:45:00Z",
"duration_minutes": 60.0, "uptime_pct": 82.61}`. Only windows ending after the
timestamp stored in `.outage_state.json` alert — run once **without**
`--webhook-url` first to seed the state, or you'll get alerts for old history.
A failed POST doesn't mark the window as alerted, so it retries next run.

## Files

| File | Purpose |
|---|---|
| `speedlog.py` | The logger — schedule it, let it run |
| `speed_report.py` | Builds `speed.html` with an SVG chart, stats, and slow-test table |
| `outage_report.py` | SLA-style outage/degradation report (`outage_report.md`, `outage.html`) + optional webhook alerts |
| `.outage_state.json` | Last-analyzed timestamp for alert dedupe (created on first run, git-ignored) |
| `speedlog.csv` | Raw measurements (created on first run, git-ignored) |

## Requirements

- Python 3.8+, no pip packages
- Windows / Linux / macOS

## License

MIT — use it on client jobs.
