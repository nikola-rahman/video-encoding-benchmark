"""Poll encoding status from providers."""

import os
import time

from benchmark.providers import get_provider
from benchmark.util.log import setup_logging

log = setup_logging("poll")


def run(config: dict, provider_name: str | None = None, watch: int | None = None,
        encoding_ids: list[str] | None = None, status_filter: str | None = None,
        all_encodings: bool = False, limit: int = 50):
    """Run the poll step."""
    pname = provider_name or "bitmovin"
    provider = get_provider(pname, config)

    if "poll" not in provider.capabilities:
        log.error(f"Provider '{pname}' does not support status polling")
        return

    def do_check():
        if encoding_ids:
            for eid in encoding_ids:
                info = provider.check_status(eid)
                log.info(f"  {info['status']:<10}{info['progress']:<7} | {info['encoding_id']} | {info['name']}")
        else:
            rows = provider.list_encodings(
                status_filter=status_filter,
                limit=limit,
                all_encodings=all_encodings,
            )
            if not rows:
                log.info("No matching encodings found.")
                return

            for row in rows:
                log.info(f"  {row['status']:<10}{row['progress']:<7} | {row['encoding_id']} | {row['name']}")

            counts = {}
            for row in rows:
                counts[row['status']] = counts.get(row['status'], 0) + 1
            log.info(f"\n  Total: {len(rows)} - " + ", ".join(
                f"{v} {k.lower()}" for k, v in sorted(counts.items())))

    if watch:
        try:
            while True:
                os.system("clear")
                log.info(f"Polling every {watch}s (Ctrl+C to stop)\n")
                do_check()
                time.sleep(watch)
        except KeyboardInterrupt:
            log.info("\nStopped.")
    else:
        do_check()
