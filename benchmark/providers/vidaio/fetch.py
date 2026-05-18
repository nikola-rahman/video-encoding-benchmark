#!/usr/bin/env python3
"""Download Vidaio pre-encoded outputs from Hippius S3 with renaming.

Vidaio uses different naming (low/medium/high, hevc/av1) than our convention
(<clip>_<codec>_vmaf<target>.mp4 with h265/av1). This downloads and renames
to match our pipeline.

Usage:
    python -m benchmark.providers.vidaio.fetch --prefix samples/vidaio_outputs/ --out-dir data/outputs/vidaio
"""

import argparse
import re
from pathlib import Path

from dotenv import load_dotenv

from benchmark.util.s3 import get_s3_client, get_bucket

load_dotenv()

LEVEL_MAP = {"low": 85, "medium": 89, "high": 93}
CODEC_MAP = {"hevc": "h265", "av1": "av1"}


def main():
    parser = argparse.ArgumentParser(description="Download Vidaio outputs from S3 with renaming")
    parser.add_argument("--prefix", required=True,
                        help="S3 prefix to list (e.g. samples/vidaio_outputs/)")
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="Local directory to write renamed files into")
    args = parser.parse_args()

    prefix = args.prefix.rstrip("/") + "/"
    pattern = re.compile(
        rf"^{re.escape(prefix)}(?P<clip>.+)_(?P<codec>hevc|av1)_(?P<level>low|medium|high)\.mp4$"
    )

    s3 = get_s3_client()
    bucket = get_bucket()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    paginator = s3.get_paginator("list_objects_v2")
    downloaded = exists = unmatched = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            m = pattern.match(key)
            if not m:
                print(f"SKIP (no match): {key}")
                unmatched += 1
                continue
            clip = m.group("clip")
            codec = CODEC_MAP[m.group("codec")]
            target = LEVEL_MAP[m.group("level")]
            new_name = f"{clip}_{codec}_vmaf{target}.mp4"
            local_path = args.out_dir / new_name
            if local_path.exists():
                exists += 1
                continue
            print(f"  {new_name}")
            s3.download_file(bucket, key, str(local_path))
            downloaded += 1

    print(f"\nDownloaded: {downloaded}, already existed: {exists}, unmatched: {unmatched}")


if __name__ == "__main__":
    main()
