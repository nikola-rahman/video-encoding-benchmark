#!/usr/bin/env python3
"""
Cleanup Bitmovin Encodings
===========================
Deletes Bitmovin encoding jobs and their corresponding S3 output files from Hippius.
Also removes local downloaded files.

Usage:
  python cleanup_encodings.py                      # list all benchmark encodings (dry run)
  python cleanup_encodings.py --delete             # delete all benchmark encodings + S3 files + local files
  python cleanup_encodings.py --id <ID> --delete   # delete specific encoding(s)
  python cleanup_encodings.py --delete --keep-local  # delete remote only, keep local files
"""

import os
import sys
import argparse
import logging
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import boto3
from botocore.config import Config as BotoConfig
from bitmovin_api_sdk import BitmovinApi
from bitmovin_api_sdk.models import Status

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

API_KEY = os.environ.get("BITMOVIN_API_KEY", "")
S3_OUTPUT_BASE_PATH = os.environ.get("BITMOVIN_S3_OUTPUT_BASE_PATH", "encoding-benchmarks/")

HIPPIUS_ENDPOINT = os.environ.get("HIPPIUS_S3_ENDPOINT", "https://s3.hippius.com")
HIPPIUS_BUCKET = os.environ.get("HIPPIUS_S3_BUCKET", "<bucket>")
HIPPIUS_ACCESS_KEY = os.environ.get("HIPPIUS_S3_ACCESS_KEY", "")
HIPPIUS_SECRET_KEY = os.environ.get("HIPPIUS_S3_SECRET_KEY", "")
HIPPIUS_REGION = os.environ.get("HIPPIUS_S3_REGION", "decentralized")

DATA_DIR = Path(__file__).parent / "data"
OUTPUTS_DIR = DATA_DIR / "outputs" / "bitmovin"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cleanup")


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=HIPPIUS_ENDPOINT,
        aws_access_key_id=HIPPIUS_ACCESS_KEY,
        aws_secret_access_key=HIPPIUS_SECRET_KEY,
        region_name=HIPPIUS_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )


def list_benchmark_encodings(api):
    """List all encodings that start with 'benchmark_'."""
    encodings = api.encoding.encodings.list(sort="createdAt:DESC").items
    return [e for e in encodings if e.name and e.name.startswith("benchmark_")]


def delete_s3_prefix(s3_client, bucket, prefix):
    """Delete all objects under an S3 prefix. Returns count of deleted objects."""
    deleted = 0
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
        deleted += len(delete_keys)
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Cleanup Bitmovin benchmark encodings")
    parser.add_argument("--id", nargs="*", dest="encoding_ids",
                        help="Specific encoding ID(s) to delete. If omitted, targets all benchmark_ encodings.")
    parser.add_argument("--delete", action="store_true",
                        help="Actually delete (without this flag, only lists what would be deleted).")
    parser.add_argument("--keep-local", action="store_true",
                        help="Keep local downloaded files (only delete remote).")
    args = parser.parse_args()

    if not API_KEY:
        log.error("BITMOVIN_API_KEY not set in .env")
        sys.exit(1)

    api = BitmovinApi(api_key=API_KEY)
    s3_client = get_s3_client()

    # Find encodings to process
    if args.encoding_ids:
        encodings = []
        for eid in args.encoding_ids:
            try:
                enc = api.encoding.encodings.get(encoding_id=eid)
                encodings.append(enc)
            except Exception as e:
                log.error(f"Could not find encoding {eid}: {e}")
    else:
        log.info("Finding all benchmark encodings...")
        encodings = list_benchmark_encodings(api)

    if not encodings:
        log.info("No benchmark encodings found.")
        return

    log.info(f"Found {len(encodings)} encoding(s):")
    for enc in encodings:
        try:
            status_resp = api.encoding.encodings.status(encoding_id=enc.id)
            status = status_resp.status
        except Exception:
            status = "unknown"
        log.info(f"  {enc.id} | {status} | {enc.name}")

    if not args.delete:
        log.info("\nDry run. Use --delete to actually remove these encodings.")
        return

    # Delete each encoding
    for enc in encodings:
        log.info(f"\n{'=' * 60}")
        log.info(f"Deleting: {enc.name} ({enc.id})")

        # 1. Delete S3 output files
        s3_prefix = f"{S3_OUTPUT_BASE_PATH.rstrip('/')}/{enc.name}/"
        log.info(f"  Deleting S3 prefix: {s3_prefix}")
        try:
            count = delete_s3_prefix(s3_client, HIPPIUS_BUCKET, s3_prefix)
            log.info(f"  Deleted {count} S3 object(s)")
        except Exception as e:
            log.error(f"  S3 delete failed: {e}")

        # 2. Delete local output files
        if not args.keep_local:
            local_dir = OUTPUTS_DIR / enc.name
            if local_dir.exists():
                log.info(f"  Deleting local: {local_dir}")
                shutil.rmtree(local_dir)
                log.info(f"  Deleted local directory")
            else:
                log.info(f"  No local directory found")

        # 3. Delete Bitmovin encoding job
        log.info(f"  Deleting Bitmovin encoding...")
        try:
            api.encoding.encodings.delete(encoding_id=enc.id)
            log.info(f"  Deleted encoding {enc.id}")
        except Exception as e:
            log.error(f"  Bitmovin delete failed: {e}")

    log.info(f"\nCleanup complete. Deleted {len(encodings)} encoding(s).")


if __name__ == "__main__":
    main()
