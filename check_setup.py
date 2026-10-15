#!/usr/bin/env python3
"""
check_setup: plain-English prerequisite checker for speedtest-logger.

Checks, with PASS/FAIL lines and no tracebacks:
  - Python version (needs 3.8+),
  - the log directory exists and is writable,
  - the speed-test machinery this repo uses actually works here:
    TCP latency probe (socket), DNS lookup, and the download test
    endpoint speedlog.py measures against.

Run it before scheduling speedlog.py — it tells you in plain English
what's missing instead of blowing up mid-run.

Usage:
    python check_setup.py

Exit code 0 when everything passes, 1 otherwise.
Zero third-party dependencies.
"""

import os
import socket
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE)  # speedlog.csv lives next to the scripts
DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=10000000"  # 10 MB
PING_HOST, PING_PORT = "1.1.1.1", 443

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("%s: %s%s" % ("PASS" if ok else "FAIL", name,
                        " (%s)" % detail if detail else ""))


def main():
    print("speedtest-logger setup check\n")

    # 1. Python version
    v = sys.version_info
    check("Python version is 3.8 or newer",
          v >= (3, 8), "%d.%d.%d" % v[:3])

    # 2. log directory exists and is writable
    if os.path.isdir(LOG_DIR):
        writable = os.access(LOG_DIR, os.W_OK)
        check("log directory exists and is writable",
              writable, LOG_DIR if writable else
              LOG_DIR + " is not writable — run from a writable folder")
    else:
        check("log directory exists and is writable", False, LOG_DIR)

    # 3. speed-test machinery: this repo uses the stdlib only —
    #    socket for latency + DNS, urllib for the download test.
    try:
        socket.gethostbyname("example.com")
        check("DNS lookups work", True, "example.com resolves")
    except Exception as exc:
        check("DNS lookups work", False,
              "can't resolve names (%s) — the logger's DNS test will fail"
              % exc)

    try:
        s = socket.create_connection((PING_HOST, PING_PORT), timeout=5)
        s.close()
        check("latency probe reachable", True,
              "TCP connect to %s:%d ok" % (PING_HOST, PING_PORT))
    except Exception as exc:
        check("latency probe reachable", False,
              "can't reach %s:%d (%s) — latency tests will fail"
              % (PING_HOST, PING_PORT, exc))

    try:
        req = urllib.request.Request(
            DOWNLOAD_URL,
            headers={"User-Agent": "speedlog/1.0",
                     "Range": "bytes=0-1023"})  # 1 KB, just to prove it serves
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read(1024)
        check("download test server reachable", True,
              "speed.cloudflare.com serves test data")
    except Exception as exc:
        check("download test server reachable", False,
              "can't reach the download test server (%s) — speed tests will fail"
              % exc)

    passed = sum(results)
    print("\n%d of %d checks passed" % (passed, len(results)))
    if passed == len(results):
        print("You're good to go: python speedlog.py --interval 15 --count 96")
    else:
        print("Fix the FAILED lines above, then run this check again.")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
