#!/usr/bin/env python3
"""
Upload & Presign Input Videos
==============================
Uploads local video files from data/inputs/ to Hippius S3 and generates
presigned HTTPS URLs. Optionally skip upload if files already exist in the bucket.

Prerequisites:
  pip install boto3 python-dotenv

Usage:
  python upload_inputs.py                       # upload all files in data/inputs/ and presign
  python upload_inputs.py --presign-only        # only generate presigned URLs (skip upload)
  python upload_inputs.py --file video.mp4      # upload/presign specific file(s)
  python upload_inputs.py --expires 604800      # presigned URL valid for 7 days (default)
  python upload_inputs.py --update-urls         # also write presigned URLs to video_urls.txt
"""

import os
import sys
import argparse
import logging
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

HIPPIUS_ENDPOINT = os.environ.get("HIPPIUS_S3_ENDPOINT", "https://s3.hippius.com")
HIPPIUS_BUCKET = os.environ.get("HIPPIUS_S3_BUCKET", "<bucket>")
HIPPIUS_ACCESS_KEY = os.environ.get("HIPPIUS_S3_ACCESS_KEY", "")
HIPPIUS_SECRET_KEY = os.environ.get("HIPPIUS_S3_SECRET_KEY", "")
HIPPIUS_REGION = os.environ.get("HIPPIUS_S3_REGION", "decentralized")

S3_PREFIX = "benchmark-inputs/"

DATA_DIR = Path(__file__).parent / "data"
INPUTS_DIR = DATA_DIR / "inputs"
VIDEO_URLS_FILE = Path(__file__).parent / "video_urls.txt"

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("upload")

# ─────────────────────────────────────────────────────────────
# S3 Client
# ─────────────────────────────────────────────────────────────

def get_s3_client():
    if not HIPPIUS_ACCESS_KEY or not HIPPIUS_SECRET_KEY:
        log.error("HIPPIUS_S3_ACCESS_KEY / HIPPIUS_S3_SECRET_KEY not set in .env")
        sys.exit(1)
    return boto3.client(
        "s3",
        endpoint_url=HIPPIUS_ENDPOINT,
        aws_access_key_id=HIPPIUS_ACCESS_KEY,
        aws_secret_access_key=HIPPIUS_SECRET_KEY,
        region_name=HIPPIUS_REGION,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def object_exists(s3_client, bucket: str, key: str) -> bool:
    """Check if an object already exists in S3."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def upload_file(s3_client, local_path: Path, bucket: str, key: str, skip_existing: bool = True) -> bool:
    """Upload a file to S3. Returns True if uploaded, False if skipped."""
    if skip_existing and object_exists(s3_client, bucket, key):
        log.info(f"  Already exists in S3: {key}")
        return False

    file_size = local_path.stat().st_size
    log.info(f"  Uploading: {local_path.name} ({file_size / (1024 * 1024):.1f} MB) → s3://{bucket}/{key}")
    s3_client.upload_file(str(local_path), bucket, key)
    log.info(f"  Uploaded successfully")
    return True


def presign_url(s3_client, bucket: str, key: str, expires_in: int) -> str:
    """Generate a presigned GET URL."""
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload input videos to Hippius S3 and generate presigned URLs")
    parser.add_argument("--file", nargs="*", default=None,
                        help="Specific file(s) to upload (relative to data/inputs/ or absolute path)")
    parser.add_argument("--presign-only", action="store_true",
                        help="Skip upload, only generate presigned URLs for existing files")
    parser.add_argument("--expires", type=int, default=604800,
                        help="Presigned URL expiration in seconds (default: 604800 = 7 days)")
    parser.add_argument("--update-urls", action="store_true",
                        help="Write presigned URLs to video_urls.txt")
    args = parser.parse_args()

    s3_client = get_s3_client()

    # Determine which files to process
    if args.file:
        files = []
        for f in args.file:
            p = Path(f)
            if not p.is_absolute():
                p = INPUTS_DIR / p
            if not p.exists():
                log.error(f"File not found: {p}")
                sys.exit(1)
            files.append(p)
    else:
        if not INPUTS_DIR.exists():
            log.error(f"Inputs directory not found: {INPUTS_DIR}")
            sys.exit(1)
        files = sorted([
            f for f in INPUTS_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".y4m", ".avi")
        ])

    if not files:
        log.info("No video files found to process.")
        return

    log.info(f"Processing {len(files)} file(s)")
    log.info(f"Bucket: {HIPPIUS_BUCKET}")
    log.info(f"Prefix: {S3_PREFIX}")
    log.info(f"URL expiration: {args.expires}s ({args.expires / 3600:.0f}h)")

    presigned_urls = []

    for filepath in files:
        s3_key = f"{S3_PREFIX}{filepath.name}"

        log.info(f"\n{'─' * 50}")
        log.info(f"File: {filepath.name}")

        # Upload
        if not args.presign_only:
            upload_file(s3_client, filepath, HIPPIUS_BUCKET, s3_key)

        # Presign
        url = presign_url(s3_client, HIPPIUS_BUCKET, s3_key, args.expires)
        log.info(f"  Presigned URL: {url[:80]}...")
        presigned_urls.append((filepath.name, url))

    # Write to video_urls.txt
    if args.update_urls:
        with open(VIDEO_URLS_FILE, "w") as f:
            f.write("# Presigned URLs for benchmark input videos\n")
            for name, url in presigned_urls:
                f.write(f"# {name}\n")
                f.write(f"{url}\n")
        log.info(f"\nWritten {len(presigned_urls)} URL(s) to {VIDEO_URLS_FILE}")

    # Summary
    log.info(f"\n{'=' * 60}")
    log.info("PRESIGNED URLS")
    log.info(f"{'=' * 60}")
    for name, url in presigned_urls:
        log.info(f"\n  {name}:")
        log.info(f"  {url}")


if __name__ == "__main__":
    main()
