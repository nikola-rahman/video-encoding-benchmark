#!/usr/bin/env python3
"""Download video samples from S3."""

from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from benchmark.util.s3 import get_s3_client, get_bucket

load_dotenv()


def run(local_dir: Path, s3_prefix: str, force: bool = False):
    s3 = get_s3_client()
    bucket = get_bucket()

    local_dir.mkdir(parents=True, exist_ok=True)

    # List objects under prefix
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.rsplit("/", 1)[-1]
            if filename:
                objects.append((key, filename, obj["Size"]))

    if not objects:
        print(f"No files found at s3://{bucket}/{s3_prefix}/")
        return

    print(f"s3://{bucket}/{s3_prefix}/ -> {local_dir}")

    downloaded = 0
    skipped = 0

    for key, filename, size in tqdm(objects, desc="Downloading", unit="file"):
        local_path = local_dir / filename

        if not force and local_path.exists() and local_path.stat().st_size == size:
            skipped += 1
            continue

        size_mb = size / (1024 * 1024)
        tqdm.write(f"  {filename} ({size_mb:.1f} MB)")
        s3.download_file(bucket, key, str(local_path))
        downloaded += 1

    print(f"{downloaded} downloaded, {skipped} skipped")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download video samples from S3")
    parser.add_argument("local_dir", type=Path, help="Local directory to download to")
    parser.add_argument("s3_prefix", help="S3 key prefix (e.g. samples/raw, samples/prepared)")
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()
    run(args.local_dir, args.s3_prefix, args.force)
