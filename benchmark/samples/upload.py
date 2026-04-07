#!/usr/bin/env python3
"""Upload a directory of video files to S3."""

from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from benchmark.config import load_config
from benchmark.util.s3 import get_s3_client, object_exists

load_dotenv()

VIDEO_EXTENSIONS = {".mp4", ".ogv", ".mkv", ".webm", ".avi", ".mov"}


def run(local_dir: Path, s3_prefix: str, force: bool = False):
    config = load_config()
    s3 = get_s3_client(config)
    bucket = config["storage"]["s3"]["bucket"]

    files = sorted(f for f in local_dir.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS)

    if not files:
        print(f"No video files in {local_dir}")
        return

    print(f"{local_dir} -> s3://{bucket}/{s3_prefix}/")

    uploaded = 0
    skipped = 0

    for f in tqdm(files, desc="Uploading", unit="file"):
        key = f"{s3_prefix}/{f.name}"

        if not force and object_exists(s3, bucket, key):
            skipped += 1
            continue

        size_mb = f.stat().st_size / (1024 * 1024)
        tqdm.write(f"  {f.name} ({size_mb:.1f} MB)")
        s3.upload_file(str(f), bucket, key)
        uploaded += 1

    print(f"{uploaded} uploaded, {skipped} skipped")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Upload a directory of videos to S3")
    parser.add_argument("dir", type=Path, help="Local directory to upload")
    parser.add_argument("prefix", help="S3 key prefix (e.g. samples/raw, inputs)")
    parser.add_argument("--force", action="store_true", help="Re-upload even if file exists")
    args = parser.parse_args()
    run(args.dir, args.prefix, args.force)
