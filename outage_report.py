#!/usr/bin/env python3
"""
outage_report: SLA-style downtime & degradation analysis for speedlog.csv.

Reads the speed log and:
  - detects outage windows: a gap with no successful speed test longer
    than --gap-minutes,
  - computes uptime % over the log period,
  - detects sustained degradation: download below --min-mbps for
    --consecutive tests in a row,
  - writes an SLA-style summary (uptime %, longest outage, % of tests
    above threshold, outage windows) as Markdown and HTML.

A "successful" test is one with a recorded download_mbps value — a test
with ping OK but download failed counts as a failed test and folds into
the outage window. Tip: set --gap-minutes to ~2x your logging interval so
one missed test doesn't count as an outage.

Optionally POSTs a JSON alert to --webhook-url when NEW outage/degradation
windows are found. State lives in .outage_state.json (git-ignored): only
windows ending after the last analysis timestamp alert, and the state
file is updated after every run. First run seeds the state; run once
WITHOUT --webhook-url to avoid alerting on old history.

Usage:
    python outage_report.py
    python outage_report.py --gap-minutes 30 --min-mbps 100 --consecutive 12
    python outage_report.py --webhook-url https://hooks.example.com/alert

Zero third-party dependencies. Windows / Linux / macOS.
"""

import argparse
import csv
import html
import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DEFAULT = os.path.join(HERE, "speedlog.csv")
STATE_DEFAULT = os.path.join(HERE, ".outage_state.json")
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_ts(s):
    return datetime.strptime(s, TS_FMT).replace(tzinfo=timezone.utc)


def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def load(path):
    """All rows with a parseable timestamp, sorted oldest-first."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                r["_t"] = parse_ts(r.get("timestamp", ""))
            except (ValueError, TypeError):
                continue
            r["_mbps"] = num(r.get("download_mbps"))
            rows.append(r)
    rows.sort(key=lambda r: r["_t"])
    return rows


def detect_outages(successes, gap, period_end):
    """Windows where consecutive successful tests are farther apart than gap.

    Returns list of dicts: start, end, duration (timedelta), ongoing (bool).
    """
    windows = []
    for prev, cur in zip(successes, successes[1:]):
        if cur["_t"] - prev["_t"] > gap:
            windows.append({"start": prev["_t"], "end": cur["_t"],
                            "duration": cur["_t"] - prev["_t"],
                            "ongoing": False})
    if successes and period_end - successes[-1]["_t"] > gap:
        windows.append({"start": successes[-1]["_t"], "end": period_end,
                        "duration": period_end - successes[-1]["_t"],
                        "ongoing": True})
    return windows


def detect_degradation(successes, min_mbps, consecutive):
    """Runs of `consecutive`+ successful tests all below min_mbps.

    A failed test (no download_mbps) breaks the run.
    """
    episodes = []
    run = []
    for r in successes + [None]:
        if r is not None and r["_mbps"] < min_mbps:
            run.append(r)
            continue
        if len(run) >= consecutive:
            speeds = [x["_mbps"] for x in run]
            episodes.append({"start": run[0]["_t"], "end": run[-1]["_t"],
                             "count": len(run),
                             "worst_mbps": min(speeds),
                             "avg_mbps": sum(speeds) / len(speeds)})
        run = []
    return episodes


def summarize(rows, gap_minutes, min_mbps, consecutive):
    gap = timedelta(minutes=gap_minutes)
    successes = [r for r in rows if r["_mbps"] is not None]
    first, last = rows[0]["_t"], rows[-1]["_t"]
    period = last - first

    windows = detect_outages(successes, gap, last)
    episodes = detect_degradation(successes, min_mbps, consecutive)
    if not successes and period.total_seconds() > 0:
        # no successful test at all: the whole log period is an outage
        windows.append({"start": first, "end": last, "duration": period,
                        "ongoing": True})

    outage_secs = sum((w["duration"].total_seconds() for w in windows), 0.0)
    if period.total_seconds() > 0:
        uptime = max(0.0, (period.total_seconds() - outage_secs)
                     / period.total_seconds() * 100)
    else:
        uptime = 100.0 if successes else 0.0

    above = [r for r in successes if r["_mbps"] >= min_mbps]
    pct_above = (len(above) / len(successes) * 100) if successes else None
    longest = max((w["duration"] for w in windows), default=None)

    label = Counter(r.get("label", "") for r in rows).most_common(1)[0][0]
    return {
        "first": first, "last": last, "period": period,
        "n_tests": len(rows), "n_success": len(successes),
        "uptime": uptime, "outage_minutes": outage_secs / 60,
        "longest": longest, "windows": windows, "episodes": episodes,
        "pct_above": pct_above, "min_mbps": min_mbps,
        "gap_minutes": gap_minutes, "consecutive": consecutive,
        "label": label,
    }


def render_markdown(s):
    def wline(w):
        status = "ongoing" if w["ongoing"] else "closed"
        return "| %s | %s | %.0f min | %s |" % (
            fmt_dt(w["start"]), fmt_dt(w["end"]),
            w["duration"].total_seconds() / 60, status)

    def eline(e):
        return "| %s | %s | %d tests | %.1f Mbps | %.1f Mbps |" % (
            fmt_dt(e["start"]), fmt_dt(e["end"]), e["count"],
            e["worst_mbps"], e["avg_mbps"])

    lines = [
        "# Outage & Degradation Report",
        "",
        "- Log period: %s → %s (%d tests, %d successful)" % (
            fmt_dt(s["first"]), fmt_dt(s["last"]), s["n_tests"], s["n_success"]),
        "- **Uptime: %.2f%%** (%.0f min of outage)" % (
            s["uptime"], s["outage_minutes"]),
        "- Longest outage: %s" % (
            "%.0f min" % (s["longest"].total_seconds() / 60)
            if s["longest"] else "none"),
        "- Tests at/above %.0f Mbps: %s" % (
            s["min_mbps"],
            "%.1f%%" % s["pct_above"] if s["pct_above"] is not None else "n/a"),
        "- Degradation episodes (< %.0f Mbps x %d in a row): %d" % (
            s["min_mbps"], s["consecutive"], len(s["episodes"])),
        "",
        "## Outage windows (%d)" % len(s["windows"]),
        "",
        "| Start (UTC) | End (UTC) | Duration | Status |",
        "|---|---|---|---|",
    ]
    lines += [wline(w) for w in s["windows"]] or ["_none_"]
    lines += [
        "",
        "## Degradation episodes (%d)" % len(s["episodes"]),
        "",
        "| Start (UTC) | End (UTC) | Length | Worst | Avg |",
        "|---|---|---|---|---|---|",
    ]
    lines += [eline(e) for e in s["episodes"]] or ["_none_"]
    lines += [
        "",
        "_Generated by speedtest-logger `outage_report.py` — "
        "gap > %d min, threshold %.0f Mbps, streak %d._" % (
            s["gap_minutes"], s["min_mbps"], s["consecutive"]),
    ]
    return "\n".join(lines) + "\n"


def render_html(s):
    def wrow(w):
        status = "<b>ongoing</b>" if w["ongoing"] else "closed"
        return ("<tr><td>%s</td><td>%s</td><td>%.0f min</td><td>%s</td></tr>"
                % (fmt_dt(w["start"]), fmt_dt(w["end"]),
                   w["duration"].total_seconds() / 60, status))

    def erow(e):
        return ("<tr><td>%s</td><td>%s</td><td>%d</td>"
                "<td>%.1f Mbps</td><td>%.1f Mbps</td></tr>"
                % (fmt_dt(e["start"]), fmt_dt(e["end"]), e["count"],
                   e["worst_mbps"], e["avg_mbps"]))

    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Outage Report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:.4em .6em;text-align:left}}
th{{background:#f5f5f5}}.kpi{{display:flex;gap:1em;flex-wrap:wrap}}.kpi div{{border:1px solid #ddd;border-radius:8px;padding:.8em 1.2em}}
.kpi b{{font-size:1.4em}}</style></head><body>
<h1>Outage &amp; Degradation Report{label}</h1>
<p>{n} tests ({ns} successful) from {a} to {b}</p>
<div class="kpi">
<div><b>{uptime}%</b><br>uptime</div>
<div><b>{om} min</b><br>total outage</div>
<div><b>{long}</b><br>longest outage</div>
<div><b>{pa}</b><br>tests ≥ {thr} Mbps</div>
<div><b>{ep}</b><br>degradation episodes</div>
</div>
<h2>Outage windows ({nw})</h2>
<table><tr><th>Start (UTC)</th><th>End (UTC)</th><th>Duration</th><th>Status</th></tr>{wrows}</table>
<h2>Degradation episodes ({ne})</h2>
<table><tr><th>Start (UTC)</th><th>End (UTC)</th><th>Length</th><th>Worst</th><th>Avg</th></tr>{erows}</table>
<p><small>Gap &gt; {gap} min, threshold {thr} Mbps, streak {con}. Generated by
<a href="https://github.com/cnoteninja/speedtest-logger">speedtest-logger</a></small></p>
</body></html>""".format(
        label=" — " + html.escape(s["label"]) if s["label"] else "",
        n=s["n_tests"], ns=s["n_success"],
        a=fmt_dt(s["first"]), b=fmt_dt(s["last"]),
        uptime="%.2f" % s["uptime"], om="%.0f" % s["outage_minutes"],
        long="%.0f min" % (s["longest"].total_seconds() / 60)
        if s["longest"] else "none",
        pa="%.1f%%" % s["pct_above"] if s["pct_above"] is not None else "n/a",
        thr="%.0f" % s["min_mbps"], ep=len(s["episodes"]),
        nw=len(s["windows"]), ne=len(s["episodes"]),
        wrows="".join(wrow(w) for w in s["windows"])
        or "<tr><td colspan=4>none — no outage windows</td></tr>",
        erows="".join(erow(e) for e in s["episodes"])
        or "<tr><td colspan=5>none</td></tr>",
        gap=s["gap_minutes"], con=s["consecutive"])


def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        last = d.get("last_seen", "")
        parse_ts(last)  # validate
        return parse_ts(last), set(d.get("alerted", []))
    except (OSError, ValueError, TypeError):
        return None, set()


def save_state(path, last_seen, alerted):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"last_seen": last_seen.strftime(TS_FMT),
                   "alerted": sorted(alerted)[-500:]}, fh, indent=2)


def post_alert(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "speedtest-logger/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def main():
    ap = argparse.ArgumentParser(description="Outage & degradation analysis")
    ap.add_argument("--csv", default=CSV_DEFAULT)
    ap.add_argument("--gap-minutes", type=float, default=15.0,
                    help="outage = gap with no successful test longer than this (default 15)")
    ap.add_argument("--min-mbps", type=float, default=50.0,
                    help="degradation threshold in Mbps (default 50)")
    ap.add_argument("--consecutive", type=int, default=6,
                    help="tests in a row under --min-mbps to count as degraded (default 6)")
    ap.add_argument("--md", default="outage_report.md",
                    help="markdown output filename (default outage_report.md)")
    ap.add_argument("--html", default="outage.html",
                    help="html output filename (default outage.html)")
    ap.add_argument("--webhook-url", default=None,
                    help="POST a JSON alert here for each NEW outage/degradation window")
    ap.add_argument("--state", default=STATE_DEFAULT,
                    help="state file tracking the last analyzed timestamp")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print("no data: run speedlog.py first")
        raise SystemExit(1)
    rows = load(args.csv)
    if not rows:
        print("empty csv")
        raise SystemExit(1)

    s = summarize(rows, args.gap_minutes, args.min_mbps, args.consecutive)

    md_path = os.path.join(HERE, os.path.basename(args.md))
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(s))
    html_path = os.path.join(HERE, os.path.basename(args.html))
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(s))
    print("wrote %s, %s (uptime %.2f%%, %d outage windows, %d degradation episodes)"
          % (md_path, html_path, s["uptime"], len(s["windows"]),
             len(s["episodes"])))

    # ---- alerting: only windows ending after the last analyzed timestamp ----
    prev_seen, alerted = load_state(args.state)
    candidates = []
    for w in s["windows"]:
        wid = "outage:%s|%s" % (w["start"].strftime(TS_FMT),
                                "ongoing" if w["ongoing"]
                                else w["end"].strftime(TS_FMT))
        candidates.append((w["end"], wid, {
            "source": "speedtest-logger/outage_report",
            "label": s["label"], "type": "outage",
            "start": w["start"].strftime(TS_FMT),
            "end": ("ongoing" if w["ongoing"]
                    else w["end"].strftime(TS_FMT)),
            "duration_minutes": round(w["duration"].total_seconds() / 60, 1),
            "uptime_pct": round(s["uptime"], 2)}))
    for e in s["episodes"]:
        eid = "degradation:%s|%s" % (e["start"].strftime(TS_FMT),
                                    e["end"].strftime(TS_FMT))
        candidates.append((e["end"], eid, {
            "source": "speedtest-logger/outage_report",
            "label": s["label"], "type": "degradation",
            "start": e["start"].strftime(TS_FMT),
            "end": e["end"].strftime(TS_FMT),
            "test_count": e["count"],
            "worst_mbps": e["worst_mbps"],
            "threshold_mbps": s["min_mbps"],
            "uptime_pct": round(s["uptime"], 2)}))

    new = [c for c in candidates
           if c[1] not in alerted and (prev_seen is None or c[0] > prev_seen)]
    save_last = s["last"]
    if args.webhook_url:
        sent = 0
        failed_ends = []
        for end, wid, payload in new:
            try:
                status = post_alert(args.webhook_url, payload)
                print("alert %s -> %s (HTTP %s)" % (payload["type"], wid, status))
                alerted.add(wid)
                sent += 1
            except Exception as exc:
                print("alert FAILED for %s: %s (will retry next run)" % (wid, exc))
                failed_ends.append(end)
        if not new:
            print("no new outage/degradation windows — no alerts sent")
        elif failed_ends:
            # hold last_seen back so failed windows are still "new" next run
            save_last = min(save_last,
                            min(failed_ends) - timedelta(seconds=1))
    save_state(args.state, save_last, alerted)
    print("state -> %s" % args.state)


if __name__ == "__main__":
    main()
