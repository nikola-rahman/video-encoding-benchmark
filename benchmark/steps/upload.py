"""Upload input videos to S3 and generate presigned URLs."""

import sys
from pathlib import Path

from benchmark.util.s3 import get_s3_client, get_bucket, upload_file, presign_url
from benchmark.util.log import setup_logging

log = setup_logging("upload")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".y4m", ".avi"}


def run(config: dict, presign_only: bool = False, expires: int = 604800,
        update_urls: bool = False, files: list[str] | None = None):
    """Run the upload step."""
    inputs_dir = Path(config.get("inputs", {}).get("dir", "./data/samples/prepared"))
    s3_cfg = config.get("storage", {}).get("s3", {})
    bucket = get_bucket()
    prefix = s3_cfg.get("prefix", "benchmark-inputs/")

    s3_client = get_s3_client()

    if files:
        video_files = []
        for f in files:
            p = Path(f)
            if not p.is_absolute():
                p = inputs_dir / p
            if not p.exists():
                log.error(f"File not found: {p}")
                sys.exit(1)
            video_files.append(p)
    else:
        if not inputs_dir.exists():
            log.error(f"Inputs directory not found: {inputs_dir}")
            sys.exit(1)
        video_files = sorted([
            f for f in inputs_dir.iterdir()
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
        ])

    if not video_files:
        log.info("No video files found to process.")
        return

    log.info(f"Processing {len(video_files)} file(s)")
    log.info(f"Bucket: {bucket}")
    log.info(f"Prefix: {prefix}")
    log.info(f"URL expiration: {expires}s ({expires / 3600:.0f}h)")

    presigned_urls = []

    for filepath in video_files:
        s3_key = f"{prefix}{filepath.name}"

        log.info(f"\n{'=' * 50}")
        log.info(f"File: {filepath.name}")

        if not presign_only:
            upload_file(s3_client, filepath, bucket, s3_key)

        url = presign_url(s3_client, bucket, s3_key, expires)
        log.info(f"  Presigned URL: {url[:80]}...")
        presigned_urls.append((filepath.name, url))

    if update_urls:
        video_urls_file = Path("video_urls.txt")
        with open(video_urls_file, "w") as f:
            f.write("# Presigned URLs for benchmark input videos\n")
            for name, url in presigned_urls:
                f.write(f"# {name}\n")
                f.write(f"{url}\n")
        log.info(f"\nWritten {len(presigned_urls)} URL(s) to {video_urls_file}")

    log.info(f"\n{'=' * 60}")
    log.info("PRESIGNED URLS")
    log.info(f"{'=' * 60}")
    for name, url in presigned_urls:
        log.info(f"\n  {name}:")
        log.info(f"  {url}")
