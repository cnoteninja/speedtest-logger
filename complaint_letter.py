#!/usr/bin/env python3
"""
complaint_letter: turn your speedlog data into a ready-to-send ISP complaint.

Reads speedlog.csv, runs the same outage analysis as outage_report.py
(log parsing and outage/degradation detection are imported from there),
and writes a formal complaint letter in BOTH Markdown and plain text.

Personal details stay as bracketed placeholders — fill them in before
sending. Every placeholder is documented in the README.

Usage:
    python complaint_letter.py                      # real data -> complaint_letter.md/.txt
    python complaint_letter.py --demo               # sample data -> complaint_letter-demo.md/.txt
    python complaint_letter.py --out my_letter      # -> my_letter.md/.txt

    # same analysis knobs as outage_report.py:
    python complaint_letter.py --gap-minutes 30 --min-mbps 100 --consecutive 12

Zero third-party dependencies.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from outage_report import load, summarize, fmt_dt  # noqa: E402
from demo_data import write_csv as demo_csv  # noqa: E402

CSV_DEFAULT = os.path.join(HERE, "speedlog.csv")

# Every [BRACKETED] placeholder the letter uses. Documented in README.
PLACEHOLDERS = ["[YOUR NAME]", "[ACCOUNT NUMBER]", "[ISP NAME]",
                "[SERVICE ADDRESS]", "[PLAN_DOWN_MBPS]", "[PLAN_UP_MBPS]"]


def letter_data(rows, gap_minutes, min_mbps, consecutive):
    """Computed numbers the letter body is built from."""
    s = summarize(rows, gap_minutes, min_mbps, consecutive)
    speeds = [r["_mbps"] for r in rows if r["_mbps"] is not None]
    # typical test spacing: median gap between consecutive rows
    deltas = sorted(
        (b["_t"] - a["_t"]).total_seconds() / 60
        for a, b in zip(rows, rows[1:]))
    median_interval = round(deltas[len(deltas) // 2]) if deltas else gap_minutes
    return {
        "s": s,
        "avg_mbps": sum(speeds) / len(speeds) if speeds else None,
        "min_mbps_measured": min(speeds) if speeds else None,
        "max_mbps_measured": max(speeds) if speeds else None,
        "median_interval": median_interval,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def md_body(d):
    s = d["s"]
    lines = [
        "# Formal Complaint: Chronic Service Interruptions",
        "",
        "**Date:** %s" % d["date"],
        "**To:** [ISP NAME] — Customer Support / Executive Relations",
        "**From:** [YOUR NAME] (Account [ACCOUNT NUMBER])",
        "**Service address:** [SERVICE ADDRESS]",
        "**Advertised plan:** [PLAN_DOWN_MBPS] Mbps down / [PLAN_UP_MBPS] Mbps up",
        "",
        "Dear [ISP NAME] Support,",
        "",
        "I am writing to formally complain about the quality and reliability "
        "of the internet service on the account above. To document the problem "
        "I ran automated speed tests every %d minutes from **%s** to **%s** "
        "(**%d tests**, %d successful). The results show the service I am "
        "paying for is not the service I am receiving." % (
            d["median_interval"], fmt_dt(s["first"]), fmt_dt(s["last"]),
            s["n_tests"], s["n_success"]),
        "",
        "## Measured vs. advertised speeds",
        "",
        "- Average measured download: **%.1f Mbps** (advertised: [PLAN_DOWN_MBPS] Mbps)" % d["avg_mbps"],
        "- Lowest measured download: **%.1f Mbps**" % d["min_mbps_measured"],
        "- Highest measured download: **%.1f Mbps**" % d["max_mbps_measured"],
        "- **Uptime: %.2f%%** — %.0f minutes of total outage during the monitoring period" % (
            s["uptime"], s["outage_minutes"]),
        "- Tests at or above %.0f Mbps: %s" % (
            s["min_mbps"],
            "%.1f%%" % s["pct_above"] if s["pct_above"] is not None else "n/a"),
        "",
        "## Outage windows (%d)" % len(s["windows"]),
        "",
        "| Start (UTC) | End (UTC) | Duration | Status |",
        "|---|---|---|---|",
    ]
    for w in s["windows"]:
        status = "ongoing at end of monitoring" if w["ongoing"] else "closed"
        lines.append("| %s | %s | %.0f min | %s |" % (
            fmt_dt(w["start"]), fmt_dt(w["end"]),
            w["duration"].total_seconds() / 60, status))
    if not s["windows"]:
        lines.append("| _none recorded_ | | | |")
    lines += [
        "",
        "## Sustained degradation episodes (%d)" % len(s["episodes"]),
        "",
        "Periods where download speed stayed below %.0f Mbps for %d or more "
        "consecutive tests:" % (s["min_mbps"], s["consecutive"]),
        "",
        "| Start (UTC) | End (UTC) | Tests | Worst | Avg |",
        "|---|---|---|---|---|---|",
    ]
    for e in s["episodes"]:
        lines.append("| %s | %s | %d | %.1f Mbps | %.1f Mbps |" % (
            fmt_dt(e["start"]), fmt_dt(e["end"]), e["count"],
            e["worst_mbps"], e["avg_mbps"]))
    if not s["episodes"]:
        lines.append("| _none recorded_ | | | | |")
    lines += [
        "",
        "## Remedy requested",
        "",
        "1. A service credit covering the documented outage period.",
        "2. Investigation and repair of the underlying issue — "
        "I can provide the raw test log on request.",
        "3. Written confirmation that the line is provisioned at the "
        "advertised [PLAN_DOWN_MBPS]/[PLAN_UP_MBPS] Mbps rate.",
        "",
        "If I do not receive a response within 14 days I will escalate to "
        "the state public utilities commission.",
        "",
        "Sincerely,",
        "",
        "[YOUR NAME]",
        "",
        "_Before sending: replace every [BRACKETED] placeholder — "
        "see README for the full list._",
    ]
    return "\n".join(lines) + "\n"


def txt_body(d):
    """Plain-text twin of the Markdown letter: same content, no formatting."""
    return md_body(d).replace("**", "").replace("#", "").replace("|", " ")


def write_letters(base, d):
    md_path = os.path.join(HERE, base + ".md")
    txt_path = os.path.join(HERE, base + ".txt")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_body(d))
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(txt_body(d))
    return md_path, txt_path


def main():
    ap = argparse.ArgumentParser(
        description="Generate an ISP complaint letter from speedlog data")
    ap.add_argument("--csv", default=CSV_DEFAULT,
                    help="input speed log (default speedlog.csv)")
    ap.add_argument("--out", default="complaint_letter",
                    help="output base name: writes <out>.md and <out>.txt")
    ap.add_argument("--demo", action="store_true",
                    help="use synthetic sample data instead of speedlog.csv")
    ap.add_argument("--gap-minutes", type=float, default=15.0)
    ap.add_argument("--min-mbps", type=float, default=50.0)
    ap.add_argument("--consecutive", type=int, default=6)
    args = ap.parse_args()

    if args.demo:
        csv_path = demo_csv(label="demo")
        out = "complaint_letter-demo" if args.out == "complaint_letter" else args.out
    else:
        csv_path = args.csv
        out = args.out
        if not os.path.exists(csv_path):
            print("no data: run speedlog.py first (or use --demo)")
            raise SystemExit(1)

    rows = load(csv_path)
    if not rows:
        print("empty csv")
        raise SystemExit(1)

    d = letter_data(rows, args.gap_minutes, args.min_mbps, args.consecutive)
    md_path, txt_path = write_letters(out, d)
    print("wrote %s and %s (uptime %.2f%%, %d outage windows)" % (
        md_path, txt_path, d["s"]["uptime"], len(d["s"]["windows"])))
    print("fill in the placeholders: %s" % ", ".join(PLACEHOLDERS))


if __name__ == "__main__":
    main()
