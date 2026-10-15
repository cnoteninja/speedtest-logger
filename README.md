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

# Turn the outage data into a ready-to-send ISP complaint letter
python complaint_letter.py

# Local read-only web dashboard
python dashboard.py --serve        # http://127.0.0.1:8000/

# Sanity-check the setup before scheduling the logger
python check_setup.py
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

## ISP complaint letter

`complaint_letter.py` reads `speedlog.csv`, runs the same outage analysis
as `outage_report.py`, and writes a formal complaint letter in **both
Markdown and plain text** (`complaint_letter.md`, `complaint_letter.txt`).
The body lists outage windows with dates and durations, uptime %,
measured-vs-advertised speed summary, and degradation episodes — with
placeholders for your personal details. Fill them in before sending.

```bash
python complaint_letter.py                     # real data
python complaint_letter.py --demo              # sample data -> complaint_letter-demo.md/.txt
python complaint_letter.py --out my_letter     # -> my_letter.md/.txt
python complaint_letter.py --gap-minutes 30 --min-mbps 100 --consecutive 12
```

Every `[BRACKETED]` placeholder in the letter, what it means, and what to
put there:

| Placeholder | Meaning | Example |
|---|---|---|
| `[YOUR NAME]` | Account holder name | Jane Smith |
| `[ACCOUNT NUMBER]` | ISP account number | 555-0123-8891 |
| `[ISP NAME]` | Your ISP's name | Acme Fiber |
| `[SERVICE ADDRESS]` | Address the service is installed at | 123 Main St, Apt 4, Cleveland OH 44113 |
| `[PLAN_DOWN_MBPS]` | Advertised download speed of your plan | 300 |
| `[PLAN_UP_MBPS]` | Advertised upload speed of your plan | 20 |

## Local web dashboard

`dashboard.py` serves a single read-only page (stdlib `http.server` only,
no packages): the latest result, uptime %, recent outage windows, and the
same SVG chart `speed_report.py` renders. Binds to `127.0.0.1` by default —
localhost only, no auth needed. Nothing on the page can change state.

```bash
python dashboard.py                   # build dashboard.html from speedlog.csv
python dashboard.py --serve           # serve at http://127.0.0.1:8000/
python dashboard.py --serve --port 8123 --host 127.0.0.1
python dashboard.py --demo --serve    # sample data, no real tests needed
```

The page auto-refreshes every 5 minutes. If there's no data yet it tells
you to run `speedlog.py` (or `--demo`).

## Demo mode

New here and want to see everything in ~30 seconds with no real tests?

```bash
python dashboard.py --demo --serve    # sample data + sample outage report, served at :8000
python complaint_letter.py --demo    # sample complaint letter (md + txt)
```

Demo data is generated deterministically in code (`demo_data.py`): 96
synthetic tests over 24 hours with one outage window, one sustained
degradation episode, and two slow blips — same every run. The demo never
touches your real `speedlog.csv`.

## Setup checker

`check_setup.py` prints plain-English `PASS`/`FAIL` lines (no tracebacks)
before you schedule the logger:

```bash
python check_setup.py
```

```
PASS: Python version is 3.8 or newer (3.12.3)
PASS: log directory exists and is writable (/home/chris/speedtest-logger)
PASS: DNS lookups work (example.com resolves)
PASS: latency probe reachable (TCP connect to 1.1.1.1:443 ok)
PASS: download test server reachable (speed.cloudflare.com serves test data)

5 of 5 checks passed
```

It checks the Python version, that the log directory exists and is
writable, and that the three things `speedlog.py` actually uses — DNS
resolution, the TCP latency probe to `1.1.1.1:443`, and the Cloudflare
download test endpoint — all work from this machine. Exit code 0 when
everything passes, 1 otherwise.

## Files

| File | Purpose |
|---|---|
| `speedlog.py` | The logger — schedule it, let it run |
| `speed_report.py` | Builds `speed.html` with an SVG chart, stats, and slow-test table |
| `outage_report.py` | SLA-style outage/degradation report (`outage_report.md`, `outage.html`) + optional webhook alerts |
| `complaint_letter.py` | ISP complaint letter from outage data (`complaint_letter.md`, `complaint_letter.txt`) |
| `dashboard.py` | Local read-only web dashboard (stdlib `http.server`; `--serve --port 8000`) |
| `check_setup.py` | Prerequisite checker — plain-English PASS/FAIL lines |
| `demo_data.py` | Deterministic synthetic data generator for `--demo` modes |
| `.outage_state.json` | Last-analyzed timestamp for alert dedupe (created on first run, git-ignored) |
| `speedlog.csv` | Raw measurements (created on first run, git-ignored) |

## Requirements

- Python 3.8+, no pip packages
- Windows / Linux / macOS

## License

MIT — use it on client jobs.
