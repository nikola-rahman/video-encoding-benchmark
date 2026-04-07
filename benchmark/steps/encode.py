"""Dispatch encoding jobs to providers."""

from pathlib import Path

from benchmark.providers import get_provider
from benchmark.util.log import setup_logging

log = setup_logging("encode")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def run(config: dict, provider_name: str | None = None, codec: str | None = None,
        video_filter: str | None = None):
    """Run the encode step."""
    providers_config = config["providers"]
    codecs = [codec] if codec else config["codecs"]
    inputs_dir = Path(config["inputs"]["dir"])
    s3_prefix = config["storage"]["s3"]["prefix"]

    if not inputs_dir.exists():
        log.error(f"Inputs directory not found: {inputs_dir}")
        return

    input_files = sorted(
        f for f in inputs_dir.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )

    if video_filter:
        input_files = [f for f in input_files if video_filter in f.name]

    if not input_files:
        log.info("No input files found.")
        return

    if provider_name:
        provider_names = [provider_name]
    else:
        provider_names = [
            name for name, cfg in providers_config.items()
            if cfg.get("enabled", False) and "submit" in get_provider(name, config).capabilities
        ]

    for pname in provider_names:
        log.info(f"\nProvider: {pname}")
        provider = get_provider(pname, config)

        submitted = []
        for input_file in input_files:
            s3_key = f"{s3_prefix}/{input_file.name}"
            input_url = provider.prepare_input(input_file, s3_key)

            for c in codecs:
                log.info(f"\n  Video: {input_file.name}")
                log.info(f"  Codec: {c}")
                try:
                    results = provider.get_results(input_file, c, video_url=input_url)
                    for r in results:
                        submitted.append(r)
                        log.info(f"  Submitted: {r.encoding_name} (ID: {r.encoding_id})")
                except Exception as e:
                    log.error(f"  Failed: {e}")

        log.info(f"\nSubmitted {len(submitted)} encoding job(s) to {pname}")
