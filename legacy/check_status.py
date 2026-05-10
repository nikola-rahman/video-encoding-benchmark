#!/usr/bin/env python3
"""
Check Bitmovin Encoding Status
================================
Usage:
  python check_status.py                  # all benchmark encodings
  python check_status.py --all            # all encodings (not just benchmark_*)
  python check_status.py --status running # filter by status
  python check_status.py --watch 30       # poll every 30 seconds
  python check_status.py --id <enc_id>    # check specific encoding
"""

import os
import sys
import time
import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

from bitmovin_api_sdk import BitmovinApi
from bitmovin_api_sdk.models import Status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("status")

API_KEY = os.environ.get("BITMOVIN_API_KEY", "")

STATUS_MAP = {
    "created": Status.CREATED,
    "queued": Status.QUEUED,
    "running": Status.RUNNING,
    "finished": Status.FINISHED,
    "error": Status.ERROR,
}


def check(api, args):
    if args.id:
        encodings = [api.encoding.encodings.get(encoding_id=eid) for eid in args.id]
    else:
        encodings = api.encoding.encodings.list(sort="createdAt:DESC", limit=args.limit).items
        if not args.all:
            encodings = [e for e in encodings if e.name and e.name.startswith("benchmark_")]

    status_filter = STATUS_MAP.get(args.status.lower()) if args.status else None

    rows = []
    for enc in encodings:
        try:
            resp = api.encoding.encodings.status(encoding_id=enc.id)
        except Exception:
            continue
        if status_filter and resp.status != status_filter:
            continue

        progress = ""
        if resp.status == Status.RUNNING and resp.progress is not None:
            progress = f" ({resp.progress}%)"

        rows.append((str(resp.status).replace("Status.", ""), progress, enc.id, enc.name or ""))

    if not rows:
        log.info("No matching encodings found.")
        return

    for status, progress, eid, name in rows:
        log.info(f"  {status:<10}{progress:<7} | {eid} | {name}")

    counts = {}
    for status, *_ in rows:
        counts[status] = counts.get(status, 0) + 1
    log.info(f"\n  Total: {len(rows)} — " + ", ".join(f"{v} {k.lower()}" for k, v in sorted(counts.items())))


def main():
    parser = argparse.ArgumentParser(description="Check Bitmovin encoding status")
    parser.add_argument("--id", nargs="*", help="Specific encoding ID(s)")
    parser.add_argument("--status", choices=["created", "queued", "running", "finished", "error"],
                        help="Filter by status")
    parser.add_argument("--all", action="store_true", help="Show all encodings, not just benchmark_*")
    parser.add_argument("--limit", type=int, default=50, help="Max encodings to fetch (default: 50)")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="Poll every N seconds")
    args = parser.parse_args()

    if not API_KEY:
        log.error("BITMOVIN_API_KEY not set in .env")
        sys.exit(1)

    api = BitmovinApi(api_key=API_KEY)

    if args.watch:
        try:
            while True:
                os.system("clear")
                log.info(f"Polling every {args.watch}s (Ctrl+C to stop)\n")
                check(api, args)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            log.info("\nStopped.")
    else:
        check(api, args)


if __name__ == "__main__":
    main()
