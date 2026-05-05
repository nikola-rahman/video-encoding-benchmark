#!/usr/bin/env python3
"""Download Vidaio pre-encoded outputs from Hippius S3 with renaming.

Vidaio uses different naming (low/medium/high, hevc/av1) than our convention
(<clip>_<codec>_vmaf<target>.mp4 with h265/av1). This downloads from
samples/vidaio_outputs/ and renames to match our pipeline.

Usage:
    python -m benchmark.providers.vidaio.fetch
"""

import re
from pathlib import Path

from dotenv import load_dotenv

from benchmark.util.s3 import get_s3_client, get_bucket

load_dotenv()

LEVEL_MAP = {"low": 85, "medium": 89, "high": 93}
CODEC_MAP = {"hevc": "h265", "av1": "av1"}
SOURCE_PREFIX = "samples/vidaio_outputs/"
PATTERN = re.compile(
    r"^samples/vidaio_outputs/(?P<clip>.+)_(?P<codec>hevc|av1)_(?P<level>low|medium|high)\.mp4$"
)


def main():
    s3 = get_s3_client()
    bucket = get_bucket()
    out_dir = Path("data/outputs/vidaio")
    out_dir.mkdir(parents=True, exist_ok=True)

    resp = s3.list_objects_v2(Bucket=bucket, Prefix=SOURCE_PREFIX)
    downloaded = exists = unmatched = 0

    for obj in resp.get("Contents", []):
        key = obj["Key"]
        m = PATTERN.match(key)
        if not m:
            print(f"SKIP (no match): {key}")
            unmatched += 1
            continue
        clip = m.group("clip")
        codec = CODEC_MAP[m.group("codec")]
        target = LEVEL_MAP[m.group("level")]
        new_name = f"{clip}_{codec}_vmaf{target}.mp4"
        local_path = out_dir / new_name
        if local_path.exists():
            exists += 1
            continue
        print(f"  {new_name}")
        s3.download_file(bucket, key, str(local_path))
        downloaded += 1

    print(f"\nDownloaded: {downloaded}, already existed: {exists}, unmatched: {unmatched}")


if __name__ == "__main__":
    main()
