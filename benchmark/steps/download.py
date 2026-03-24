"""Download encoded outputs from providers."""

import json
from pathlib import Path

from benchmark.providers import get_provider
from benchmark.metadata import load_metadata, save_metadata, merge_metadata
from benchmark.util.log import setup_logging

log = setup_logging("download")


def run(config: dict, provider_name: str | None = None,
        encoding_ids: list[str] | None = None, list_only: bool = False):
    """Run the download step."""
    data_dir = Path(config.get("data_dir", "./data"))
    outputs_dir = data_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = data_dir / "metadata.json"

    pname = provider_name or "bitmovin"
    provider = get_provider(pname, config)

    if "download" not in provider.capabilities:
        log.error(f"Provider '{pname}' does not support downloading")
        return

    if list_only:
        rows = provider.list_encodings(status_filter="finished")
        for row in rows:
            log.info(f"  {row['encoding_id']} | {row['name']}")
        return

    results = provider.download_all_finished(outputs_dir, encoding_ids=encoding_ids)

    if not results:
        log.info("No results to download.")
        return

    # Build metadata and merge
    all_meta = [r.to_metadata_dict() for r in results]
    existing = load_metadata(metadata_path)
    merged = merge_metadata(existing, all_meta, pname)
    save_metadata(metadata_path, merged)
    log.info(f"\nMetadata written to {metadata_path}")

    # Summary
    log.info(f"\n{'=' * 60}")
    log.info("SUMMARY")
    log.info(f"{'=' * 60}")
    for r in results:
        log.info(f"\n  Encoding: {r.encoding_name}")
        log.info(f"  Codec:    {r.codec}")
        log.info(f"  Input:    {r.input_file.name}")
        log.info(f"  Renditions: {len(r.renditions)}")
        for rend in r.renditions:
            kbps = round(rend.bitrate_bps / 1000, 1)
            size_mb = rend.total_size_bytes / (1024 * 1024)
            log.info(f"    {kbps:>8} kbps | {size_mb:.1f} MB")
