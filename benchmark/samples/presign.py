#!/usr/bin/env python3
"""Generate presigned URLs for prepared samples on S3."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from benchmark.util.s3 import get_s3_client, get_bucket, presign_url

load_dotenv()


def run(s3_prefix: str, output_file: Path, expires: int = 604800):
    s3 = get_s3_client()
    bucket = get_bucket()

    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.rsplit("/", 1)[-1]
            if filename:
                objects.append((key, filename))

    if not objects:
        print(f"No files found at s3://{bucket}/{s3_prefix}/")
        return

    urls = []
    for key, filename in sorted(objects):
        url = presign_url(s3, bucket, key, expires)
        urls.append((filename, url))

    with open(output_file, "w") as f:
        for filename, url in urls:
            f.write(f"# {filename}\n")
            f.write(f"{url}\n")

    print(f"{len(urls)} URLs written to {output_file} (expires in {expires // 3600}h)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate presigned URLs for S3 samples")
    parser.add_argument("s3_prefix", help="S3 key prefix (e.g. samples/prepared)")
    parser.add_argument("output_file", type=Path, help="Output file for URLs (e.g. video_urls.txt)")
    parser.add_argument("--expires", type=int, default=604800, help="URL expiry in seconds (default: 7 days)")
    args = parser.parse_args()
    run(args.s3_prefix, args.output_file, args.expires)
