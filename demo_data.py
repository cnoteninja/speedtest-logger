#!/usr/bin/env python3
"""
demo_data: deterministic synthetic speedlog data for demos.

Generates a speedlog-style CSV with a realistic day of measurements:
  - healthy baseline (~85 Mbps down),
  - one real outage window (4 missed tests = ~75 min dark),
  - one sustained degradation episode (8 tests in a row under 50 Mbps),
  - a couple of one-off slow blips.

Same seed every run, so the demo always looks the same. Used by
dashboard.py --demo and complaint_letter.py --demo. Nothing touches
your real speedlog.csv.

Zero third-party dependencies.
"""

import csv
import random
import tempfile
from datetime import datetime, timedelta, timezone

CSV_FIELDS = ["timestamp", "label", "latency_ms", "dns_ms",
              "download_mbps", "bytes", "error"]

SEED = 42
N_TESTS = 96          # 24 hours at 15-minute intervals
INTERVAL_MIN = 15
OUTAGE_LO, OUTAGE_HI = 40, 43      # indices with no successful test (outage)
DEGRADE_LO, DEGRADE_HI = 64, 71    # indices stuck under the degradation threshold
SLOW_BLIPS = {10: 6.0, 88: 9.0}    # one-off slow tests (not outages)
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def generate_rows():
    """List of speedlog-style row dicts, oldest first."""
    rnd = random.Random(SEED)
    start = (datetime.now(timezone.utc)
             .replace(minute=0, second=0, microsecond=0)
             - timedelta(hours=24))
    rows = []
    for i in range(N_TESTS):
        ts = start + timedelta(minutes=INTERVAL_MIN * i)
        lat = round(16 + rnd.gauss(0, 3), 1)
        dns = round(10 + rnd.gauss(0, 4), 1)
        mbps, nbytes, err = "", 0, ""
        if OUTAGE_LO <= i <= OUTAGE_HI:
            err = "timeout"  # no download_mbps -> counts as an outage gap
        elif i in SLOW_BLIPS:
            mbps = SLOW_BLIPS[i]
            nbytes = 10000000
        elif DEGRADE_LO <= i <= DEGRADE_HI:
            mbps = round(max(4.0, 13 + rnd.gauss(0, 3)), 1)
            nbytes = 10000000
        else:
            mbps = round(max(20.0, 85 + rnd.gauss(0, 8)), 1)
            nbytes = 10000000
        rows.append({"timestamp": ts.strftime(TS_FMT), "label": "demo",
                     "latency_ms": lat, "dns_ms": dns,
                     "download_mbps": mbps, "bytes": nbytes, "error": err})
    return rows


def write_csv(path=None, label="demo"):
    """Write the synthetic log to `path` (a fresh temp file if None).

    Returns the CSV path.
    """
    if path is None:
        fd, path = tempfile.mkstemp(prefix="speedlog-demo-",
                                    suffix=".csv")
        import os
        os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in generate_rows():
            r = dict(r)
            r["label"] = label
            w.writerow({k: r[k] for k in CSV_FIELDS})
    return path


def describe():
    return ("%d synthetic tests over 24h (15-min interval): one outage window "
            "(tests %d-%d dark), one degradation episode (tests %d-%d under "
            "threshold), two slow blips" % (
                N_TESTS, OUTAGE_LO, OUTAGE_HI, DEGRADE_LO, DEGRADE_HI))


if __name__ == "__main__":
    print(write_csv(), "-", describe())
