#!/usr/bin/env python3
"""
speedlog: internet speed logger for "the internet is slow" tickets.

Measures latency, DNS time, and download speed on a schedule, logs every
result to CSV. Run it for a day at a problem site, then build the chart
report with speed_report.py and show the client exactly when it dips.

Usage:
    python speedlog.py --interval 15 --count 96 --label "Branch office"
        Test every 15 minutes, 96 times (24 hours), tagged "Branch office".

    python speedlog.py --interval 5 --duration 60
        Every 5 minutes for 60 minutes.

Zero third-party dependencies. Windows / Linux / macOS.
"""

import argparse
import csv
import os
import socket
import time
import urllib.request
from datetime import datetime, timezone

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speedlog.csv")
CSV_FIELDS = ["timestamp", "label", "latency_ms", "dns_ms",
              "download_mbps", "bytes", "error"]

DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=10000000"  # 10 MB
PING_HOST, PING_PORT = "1.1.1.1", 443


def measure_latency():
    """TCP connect time to Cloudflare DNS — proxy for last-mile latency."""
    t = time.time()
    try:
        s = socket.create_connection((PING_HOST, PING_PORT), timeout=5)
        s.close()
        return round((time.time() - t) * 1000, 1), ""
    except Exception as exc:
        return None, str(exc)[:60]


def measure_dns():
    t = time.time()
    try:
        socket.gethostbyname("example.com")
        return round((time.time() - t) * 1000, 1), ""
    except Exception as exc:
        return None, str(exc)[:60]


def measure_download(url=DOWNLOAD_URL, cap_seconds=45):
    start = time.time()
    total = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "speedlog/1.0"})
        with urllib.request.urlopen(req, timeout=cap_seconds + 10) as resp:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if time.time() - start > cap_seconds:
                    break
    except Exception as exc:
        return None, total, str(exc)[:60]
    elapsed = time.time() - start
    if elapsed <= 0 or total == 0:
        return None, total, "no data"
    return round(total * 8 / elapsed / 1e6, 1), total, ""


def log_row(label, lat, lat_err, dns, dns_err, mbps, nbytes, err):
    new_file = not os.path.exists(CSV_PATH)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({"timestamp": ts, "label": label, "latency_ms": lat or "",
                    "dns_ms": dns or "", "download_mbps": mbps or "",
                    "bytes": nbytes,
                    "error": err or lat_err or dns_err})


def main():
    ap = argparse.ArgumentParser(description="Log internet speed over time")
    ap.add_argument("--interval", type=int, default=15,
                    help="minutes between tests")
    ap.add_argument("--count", type=int, default=0,
                    help="number of tests (0 = until --duration)")
    ap.add_argument("--duration", type=int, default=0,
                    help="total minutes to run (0 = run on --count)")
    ap.add_argument("--label", default="", help="site label for this run")
    args = ap.parse_args()

    if args.count:
        total_runs = args.count
    elif args.duration:
        total_runs = max(1, args.duration // args.interval)
    else:
        total_runs = 96  # 24h at 15-min intervals

    print("speedlog: every %d min x %d runs%s (Ctrl+C to stop)" % (
        args.interval, total_runs,
        " [%s]" % args.label if args.label else ""))
    run = 0
    try:
        while run < total_runs:
            run += 1
            lat, lat_err = measure_latency()
            dns, dns_err = measure_dns()
            mbps, nbytes, dl_err = measure_download()
            log_row(args.label, lat, lat_err, dns, dns_err, mbps, nbytes, dl_err)
            print("[%s] run %d/%d: %s ms ping, %s ms dns, %s Mbps" % (
                datetime.now().strftime("%H:%M"), run, total_runs,
                lat if lat is not None else "FAIL",
                dns if dns is not None else "FAIL",
                mbps if mbps is not None else "FAIL"))
            if run < total_runs:
                time.sleep(args.interval * 60)
    except KeyboardInterrupt:
        pass
    print("done -> %s  |  build the chart with: python speed_report.py" % CSV_PATH)


if __name__ == "__main__":
    main()
