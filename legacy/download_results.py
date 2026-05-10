#!/usr/bin/env python3
"""
Download Benchmark Results
==========================
Downloads input videos and Bitmovin-encoded outputs from Hippius S3,
then generates a metadata JSON mapping inputs to their encoded renditions.

Prerequisites:
  pip install boto3 bitmovin-api-sdk python-dotenv

Usage:
  python download_results.py                        # download all completed encodings
  python download_results.py --encoding-id <ID>     # download a specific encoding
  python download_results.py --list                  # list completed encodings without downloading
"""

import os
import sys
import json
import argparse
import logging
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

import boto3
from botocore.config import Config as BotoConfig
from dotenv import load_dotenv

load_dotenv()

from bitmovin_api_sdk import BitmovinApi, BitmovinApiLogger
from bitmovin_api_sdk.models import Status

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

API_KEY = os.environ.get("BITMOVIN_API_KEY", "")
S3_OUTPUT_ID = os.environ.get("BITMOVIN_S3_OUTPUT_ID", "")

HIPPIUS_ENDPOINT = os.environ.get("HIPPIUS_S3_ENDPOINT", "https://s3.hippius.com")
HIPPIUS_BUCKET = os.environ.get("HIPPIUS_S3_BUCKET", "<bucket>")
HIPPIUS_ACCESS_KEY = os.environ.get("HIPPIUS_S3_ACCESS_KEY", "")
HIPPIUS_SECRET_KEY = os.environ.get("HIPPIUS_S3_SECRET_KEY", "")
HIPPIUS_REGION = os.environ.get("HIPPIUS_S3_REGION", "decentralized")

DATA_DIR = Path(__file__).parent / "data"
INPUTS_DIR = DATA_DIR / "inputs"
OUTPUTS_DIR = DATA_DIR / "outputs"
VIDEO_URLS_FILE = os.environ.get("BITMOVIN_VIDEO_URLS_FILE", "video_urls.txt")

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("download")

# ─────────────────────────────────────────────────────────────
# S3 Client
# ─────────────────────────────────────────────────────────────

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=HIPPIUS_ENDPOINT,
        aws_access_key_id=HIPPIUS_ACCESS_KEY,
        aws_secret_access_key=HIPPIUS_SECRET_KEY,
        region_name=HIPPIUS_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )


# ─────────────────────────────────────────────────────────────
# Bitmovin helpers
# ─────────────────────────────────────────────────────────────

def get_encoding_details(api, encoding_id):
    """Get encoding info, streams, and muxings."""
    encoding = api.encoding.encodings.get(encoding_id=encoding_id)
    status_resp = api.encoding.encodings.status(encoding_id=encoding_id)

    # Get streams
    streams = api.encoding.encodings.streams.list(encoding_id=encoding_id).items

    # Get muxings (both fmp4 and progressive mp4)
    fmp4_muxings = api.encoding.encodings.muxings.fmp4.list(encoding_id=encoding_id).items
    mp4_muxings = api.encoding.encodings.muxings.mp4.list(encoding_id=encoding_id).items

    return encoding, status_resp, streams, fmp4_muxings, mp4_muxings


def list_completed_encodings(api):
    """List all encodings that start with 'benchmark_' and are FINISHED."""
    encodings = api.encoding.encodings.list(sort="createdAt:DESC").items
    completed = []
    for enc in encodings:
        if enc.name and enc.name.startswith("benchmark_"):
            try:
                status_resp = api.encoding.encodings.status(encoding_id=enc.id)
                if status_resp.status == Status.FINISHED:
                    completed.append(enc)
            except Exception:
                pass
    return completed


# ─────────────────────────────────────────────────────────────
# Download helpers
# ─────────────────────────────────────────────────────────────

def download_input_video(url, inputs_dir):
    """Download input video from its URL. Returns local path."""
    parsed = urlparse(url)
    # Extract filename from path (before query params)
    filename = os.path.basename(parsed.path)
    if not filename:
        filename = "input_video.mp4"

    local_path = inputs_dir / filename
    if local_path.exists():
        log.info(f"  Input already downloaded: {local_path}")
        return local_path

    log.info(f"  Downloading input: {filename}")

    # If it's a Hippius/S3 presigned URL, use requests
    import requests
    resp = requests.get(url, stream=True)
    resp.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    size_mb = local_path.stat().st_size / (1024 * 1024)
    log.info(f"  Downloaded input: {filename} ({size_mb:.1f} MB)")
    return local_path


def get_actual_bitrate(filepath):
    """Get actual bitrate from file via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=bit_rate", "-of", "csv=p=0", filepath],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return None


def download_s3_prefix(s3_client, bucket, prefix, local_dir):
    """Download all files under an S3 prefix to a local directory. Returns list of downloaded files."""
    downloaded = []
    paginator = s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Relative path from the prefix
            rel_path = key[len(prefix):].lstrip("/")
            if not rel_path:
                continue

            local_path = local_dir / rel_path
            local_path.parent.mkdir(parents=True, exist_ok=True)

            if local_path.exists() and local_path.stat().st_size == obj["Size"]:
                log.info(f"    Already downloaded: {rel_path}")
            else:
                log.info(f"    Downloading: {rel_path} ({obj['Size'] / 1024:.1f} KB)")
                s3_client.download_file(bucket, key, str(local_path))

            downloaded.append({
                "s3_key": key,
                "local_path": str(local_path),
                "size_bytes": obj["Size"],
            })

    return downloaded


def download_encoding_outputs(s3_client, encoding, fmp4_muxings, mp4_muxings, outputs_dir):
    """Download all muxing outputs for an encoding. Returns rendition info."""
    renditions = []

    # Prefer progressive MP4 muxings (single file, proper seek indices)
    # Fall back to fmp4 muxings only if no mp4 muxings exist
    muxings_to_use = mp4_muxings if mp4_muxings else fmp4_muxings
    muxing_type = "mp4" if mp4_muxings else "fmp4"

    for muxing in muxings_to_use:
        if not muxing.outputs:
            continue

        for output in muxing.outputs:
            output_path = output.output_path
            # Skip the Per-Title template muxing (contains {bitrate} placeholder)
            if "{bitrate}" in output_path or "{uuid}" in output_path:
                continue
            # output_path looks like: encoding-benchmarks/benchmark_xxx/video/240000/
            # The bitrate is the last directory component
            parts = output_path.rstrip("/").split("/")
            bitrate_dir = parts[-1] if parts else "unknown"

            rendition_dir = outputs_dir / "bitmovin" / encoding.name / bitrate_dir
            rendition_dir.mkdir(parents=True, exist_ok=True)

            log.info(f"  Downloading rendition: {bitrate_dir} bps ({muxing_type})")
            files = download_s3_prefix(s3_client, HIPPIUS_BUCKET, output_path, rendition_dir)

            rendition_info = {
                "bitrate_bps": int(bitrate_dir) if bitrate_dir.isdigit() else bitrate_dir,
                "s3_prefix": output_path,
                "file_count": len(files),
                "total_size_bytes": sum(f["size_bytes"] for f in files),
            }

            if muxing_type == "mp4":
                # Progressive MP4: single file, use local_file
                mp4_files = [f for f in files if f["local_path"].endswith(".mp4")]
                if mp4_files:
                    rendition_info["local_file"] = mp4_files[0]["local_path"]
                    actual = get_actual_bitrate(mp4_files[0]["local_path"])
                    if actual:
                        rendition_info["bitrate_bps"] = actual
                else:
                    rendition_info["local_dir"] = str(rendition_dir)
            else:
                # fmp4 segments: need remuxing later
                rendition_info["local_dir"] = str(rendition_dir)
                rendition_info["segment_length"] = muxing.segment_length

            rendition_info["bitrate_kbps"] = rendition_info["bitrate_bps"] / 1000 if isinstance(rendition_info["bitrate_bps"], (int, float)) else None
            renditions.append(rendition_info)

    return renditions


# ─────────────────────────────────────────────────────────────
# Metadata
# ─────────────────────────────────────────────────────────────

def load_video_urls(filepath):
    """Load video URLs from file."""
    urls = []
    if not os.path.isfile(filepath):
        return urls
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def match_input_url(encoding_name, video_urls):
    """Try to match an encoding name back to its input URL."""
    # encoding_name format: benchmark_{video_id}_{codec}_{timestamp}
    # video_id is extracted from the URL filename
    for url in video_urls:
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        video_id = filename.rsplit(".", 1)[0]
        if video_id in encoding_name:
            return url
    return None


def extract_codec_from_name(encoding_name):
    """Extract codec from encoding name like benchmark_xxx_av1_20260223_211159."""
    match = re.search(r"_(h265|av1|h264|vp9)_\d{8}_", encoding_name)
    if match:
        return match.group(1)
    return "unknown"


def build_metadata(encoding, streams, renditions, input_url, input_local_path):
    """Build a metadata dict for one encoding job."""
    codec = extract_codec_from_name(encoding.name)

    return {
        "provider": "bitmovin",
        "encoding_id": encoding.id,
        "encoding_name": encoding.name,
        "codec": codec,
        "created_at": encoding.created_at.isoformat() if encoding.created_at else None,
        "input": {
            "url": input_url,
            "local_path": str(input_local_path) if input_local_path else None,
            "filename": os.path.basename(str(input_local_path)) if input_local_path else None,
        },
        "renditions": renditions,
    }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Download Bitmovin benchmark results")
    parser.add_argument(
        "--encoding-id", nargs="*",
        help="Specific encoding ID(s) to download. If omitted, downloads all completed benchmark encodings.",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_only",
        help="List completed encodings without downloading.",
    )
    args = parser.parse_args()

    if not API_KEY:
        log.error("BITMOVIN_API_KEY not set in .env")
        sys.exit(1)

    api = BitmovinApi(api_key=API_KEY)
    s3_client = get_s3_client()
    video_urls = load_video_urls(VIDEO_URLS_FILE)

    # Determine which encodings to process
    if args.encoding_id:
        encoding_ids = args.encoding_id
    else:
        log.info("Finding completed benchmark encodings...")
        completed = list_completed_encodings(api)
        if not completed:
            log.info("No completed benchmark encodings found.")
            return
        encoding_ids = [e.id for e in completed]
        log.info(f"Found {len(encoding_ids)} completed encoding(s)")

    if args.list_only:
        for eid in encoding_ids:
            enc = api.encoding.encodings.get(encoding_id=eid)
            codec = extract_codec_from_name(enc.name or "")
            log.info(f"  {eid} | {codec:>5} | {enc.name}")
        return

    # Create directories
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    all_metadata = []

    for eid in encoding_ids:
        log.info(f"\n{'=' * 60}")
        log.info(f"Processing encoding: {eid}")
        log.info(f"{'=' * 60}")

        encoding, status_resp, streams, fmp4_muxings, mp4_muxings = get_encoding_details(api, eid)
        log.info(f"  Name: {encoding.name}")
        log.info(f"  Status: {status_resp.status}")

        if status_resp.status != Status.FINISHED:
            log.warning(f"  Skipping (not finished)")
            continue

        # Match input URL
        input_url = match_input_url(encoding.name, video_urls)
        input_local_path = None

        if input_url:
            log.info(f"\nDownloading input video...")
            input_local_path = download_input_video(input_url, INPUTS_DIR)
        else:
            log.warning("  Could not match input URL from video_urls.txt")

        # Download outputs
        log.info(f"\nDownloading encoded outputs...")
        renditions = download_encoding_outputs(s3_client, encoding, fmp4_muxings, mp4_muxings, OUTPUTS_DIR)
        log.info(f"  Downloaded {len(renditions)} rendition(s)")

        # Build metadata
        meta = build_metadata(encoding, streams, renditions, input_url, input_local_path)
        all_metadata.append(meta)

    # Write metadata (merge with existing non-bitmovin entries)
    metadata_path = DATA_DIR / "metadata.json"
    existing = []
    if metadata_path.exists():
        with open(metadata_path) as f:
            existing = json.load(f)
    # Keep entries from other providers
    other_providers = [e for e in existing if e.get("provider") != "bitmovin"]
    merged = all_metadata + other_providers
    with open(metadata_path, "w") as f:
        json.dump(merged, f, indent=2, default=str)
    log.info(f"\nMetadata written to {metadata_path}")

    # Print summary
    log.info(f"\n{'=' * 60}")
    log.info("SUMMARY")
    log.info(f"{'=' * 60}")
    for meta in all_metadata:
        log.info(f"\n  Encoding: {meta['encoding_name']}")
        log.info(f"  Codec:    {meta['codec']}")
        log.info(f"  Input:    {meta['input']['filename']}")
        log.info(f"  Renditions:")
        for r in meta["renditions"]:
            size_mb = r["total_size_bytes"] / (1024 * 1024)
            kbps = r['bitrate_kbps'] if r['bitrate_kbps'] is not None else '?'
            log.info(f"    {kbps:>8} kbps | {r['file_count']} files | {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
