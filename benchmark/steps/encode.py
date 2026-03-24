"""Dispatch encoding jobs to providers."""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from benchmark.providers import get_provider
from benchmark.util.log import setup_logging

log = setup_logging("encode")


def _load_video_urls() -> list[str]:
    """Load presigned video URLs from video_urls.txt."""
    filepath = Path("video_urls.txt")
    if not filepath.exists():
        log.error(f"Video URLs file not found: {filepath}")
        log.error("Run 'python -m benchmark upload --update-urls' first.")
        sys.exit(1)
    urls = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    if not urls:
        log.error(f"No URLs found in {filepath}")
        sys.exit(1)
    return urls


def run(config: dict, provider_name: str | None = None, codec: str | None = None,
        video_filter: str | None = None):
    """Run the encode step."""
    providers_config = config.get("providers", {})
    codecs = [codec] if codec else config.get("codecs", ["av1", "h265"])
    inputs_dir = Path(config.get("inputs", {}).get("dir", "./data/inputs"))

    # Determine which providers to use
    if provider_name:
        provider_names = [provider_name]
    else:
        provider_names = [name for name, cfg in providers_config.items() if cfg.get("enabled", True)]

    for pname in provider_names:
        log.info(f"\nProvider: {pname}")

        if pname == "bitmovin":
            # Bitmovin needs video URLs
            video_urls = _load_video_urls()

            if video_filter:
                filter_basename = os.path.basename(video_filter)
                video_urls = [u for u in video_urls
                              if video_filter in u or filter_basename in os.path.basename(urlparse(u).path)]
                if not video_urls:
                    log.error(f"No matching video URL for: {video_filter}")
                    sys.exit(1)

            provider = get_provider(pname, config)

            submitted = []
            for url in video_urls:
                video_name = os.path.basename(urlparse(url).path)
                input_file = inputs_dir / video_name

                for c in codecs:
                    log.info(f"\nVideo: {video_name}")
                    log.info(f"Codec: {c}")
                    try:
                        results = provider.get_results(input_file, c, video_url=url)
                        for r in results:
                            submitted.append(r)
                            log.info(f"  Submitted: {r.encoding_name} (ID: {r.encoding_id})")
                    except Exception as e:
                        log.error(f"  Failed: {e}")

            log.info(f"\nSubmitted {len(submitted)} encoding job(s) to {pname}")

        else:
            log.info(f"  Provider '{pname}' does not support encoding submission (manual provider)")
