"""Clean up remote and local resources."""

import shutil
from pathlib import Path

from benchmark.providers import get_provider
from benchmark.util.log import setup_logging

log = setup_logging("cleanup")


def run(config: dict, provider_name: str | None = None,
        encoding_ids: list[str] | None = None, delete: bool = False,
        keep_local: bool = False):
    """Run the cleanup step."""
    data_dir = Path(config.get("data_dir", "./data"))
    outputs_dir = data_dir / "outputs"

    pname = provider_name or "bitmovin"
    provider = get_provider(pname, config)

    if "cleanup" not in provider.capabilities:
        # For manual providers, only offer local cleanup
        if delete and not keep_local:
            provider_dir = outputs_dir / pname
            if provider_dir.exists():
                log.info(f"Deleting local directory: {provider_dir}")
                shutil.rmtree(provider_dir)
                log.info("Deleted.")
            else:
                log.info(f"No local directory found: {provider_dir}")
        else:
            log.info(f"Provider '{pname}' does not support remote cleanup")
        return

    if not delete:
        # Dry run: list what would be deleted
        rows = provider.list_encodings()
        if not rows:
            log.info("No benchmark encodings found.")
            return

        log.info(f"Found {len(rows)} encoding(s):")
        for row in rows:
            log.info(f"  {row['encoding_id']} | {row['status']} | {row['name']}")
        log.info("\nDry run. Use --delete to actually remove these encodings.")
        return

    count = provider.cleanup_all(
        encoding_ids=encoding_ids,
        keep_local=keep_local,
        local_output_dir=outputs_dir,
    )
    log.info(f"\nCleanup complete. Deleted {count} encoding(s).")
