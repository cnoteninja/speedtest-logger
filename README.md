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
```

Open `speed.html`. That's your evidence.

## How it works

- **Latency** — TCP connect time to 1.1.1.1:443 (last-mile latency proxy)
- **DNS** — resolution time for a test domain
- **Download** — timed 10 MB download, converted to Mbps
- Every result lands in `speedlog.csv` with a UTC timestamp

## Files

| File | Purpose |
|---|---|
| `speedlog.py` | The logger — schedule it, let it run |
| `speed_report.py` | Builds `speed.html` with an SVG chart, stats, and slow-test table |
| `speedlog.csv` | Raw measurements (created on first run, git-ignored) |

## Requirements

- Python 3.8+, no pip packages
- Windows / Linux / macOS

## License

MIT — use it on client jobs.
