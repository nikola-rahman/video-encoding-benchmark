#!/usr/bin/env python3
"""
Register Manually-Encoded Outputs
===================================
Adds manually-encoded video files to metadata.json so calculate_vmaf.py
can evaluate them alongside API-based encodings.

Usage:
  # Register a single file
  python add_output.py --provider vidaio --input data/inputs/video.mp4 --output /path/to/encoded.mp4 --codec av1

  # Scan all files under a provider directory and register them
  python add_output.py --provider vidaio --scan

Directory convention for --scan:
  data/outputs/<provider>/<input_stem>_<codec>[_<extra>]/output.mp4

  Examples:
    data/outputs/vidaio/BigBuckBunny_720p_60s_av1_basic/output.mp4
    data/outputs/vidaio/TearsOfSteel_1080p_60s_hevc_hyper/output.mp4

  The script matches <input_stem> against files in data/inputs/ and extracts
  the codec from the directory name.
"""

import os
import sys
import json
import re
import shutil
import argparse
import logging
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("add_output")

DATA_DIR = Path(__file__).parent / "data"
INPUTS_DIR = DATA_DIR / "inputs"
OUTPUTS_DIR = DATA_DIR / "outputs"
METADATA_FILE = DATA_DIR / "metadata.json"

KNOWN_CODECS = ["av1", "hevc", "h265", "h264", "vp9"]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def get_video_info(path: str) -> dict:
    """Get bitrate, duration, resolution via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration,bit_rate:stream=width,height,codec_name",
            "-of", "json",
            path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return json.loads(result.stdout)


def load_metadata():
    if METADATA_FILE.exists():
        with open(METADATA_FILE) as f:
            return json.load(f)
    return []


def save_metadata(metadata):
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2, default=str)


def find_input_file(dir_name: str) -> Path | None:
    """Match a directory name like 'BigBuckBunny_720p_60s_av1_basic' to an input file."""
    inputs = sorted(INPUTS_DIR.iterdir()) if INPUTS_DIR.exists() else []
    # Try longest stem match first
    for inp in sorted(inputs, key=lambda p: len(p.stem), reverse=True):
        if dir_name.startswith(inp.stem):
            return inp
    return None


def extract_codec(dir_name: str, input_stem: str) -> str | None:
    """Extract codec from the part of dir_name after the input stem."""
    remainder = dir_name[len(input_stem):].lstrip("_")
    # First token should be the codec
    parts = remainder.split("_")
    for part in parts:
        if part.lower() in KNOWN_CODECS:
            return part.lower()
    return None


def find_video_file(directory: Path) -> Path | None:
    """Find a single video file in a directory."""
    videos = [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
    if len(videos) == 1:
        return videos[0]
    if len(videos) > 1:
        # Prefer output.mp4 or the largest file
        for v in videos:
            if v.stem == "output":
                return v
        return max(videos, key=lambda f: f.stat().st_size)
    return None


def build_entry(provider: str, encoding_name: str, codec: str, input_file: Path, output_file: Path) -> dict:
    """Build a metadata entry for one output."""
    probe = get_video_info(str(output_file))
    fmt = probe.get("format", {})
    bitrate_bps = int(fmt.get("bit_rate", 0))
    file_size = os.path.getsize(output_file)

    return {
        "provider": provider,
        "encoding_name": encoding_name,
        "codec": codec,
        "input": {
            "local_path": str(input_file),
            "filename": input_file.name,
        },
        "renditions": [
            {
                "bitrate_bps": bitrate_bps,
                "bitrate_kbps": round(bitrate_bps / 1000, 2),
                "local_file": str(output_file),
                "file_count": 1,
                "total_size_bytes": file_size,
            }
        ],
    }


def cmd_scan(args):
    """Scan a provider's output directory and register all found video files."""
    provider = args.provider
    provider_dir = OUTPUTS_DIR / provider

    if not provider_dir.exists():
        log.error(f"Provider directory not found: {provider_dir}")
        sys.exit(1)

    metadata = load_metadata()

    # Build set of already-registered (provider, encoding_name) pairs
    registered = {(e["provider"], e["encoding_name"]) for e in metadata}

    added = 0
    skipped = 0

    for subdir in sorted(provider_dir.iterdir()):
        if not subdir.is_dir():
            continue

        dir_name = subdir.name

        # Check if already registered
        if (provider, dir_name) in registered:
            log.info(f"  Already registered: {dir_name}")
            skipped += 1
            continue

        # Find video file
        video_file = find_video_file(subdir)
        if not video_file:
            log.warning(f"  No video file found in {dir_name}/, skipping")
            continue

        # Match input file
        input_file = find_input_file(dir_name)
        if not input_file:
            log.warning(f"  Could not match input for {dir_name}/, skipping")
            continue

        # Extract codec
        codec = extract_codec(dir_name, input_file.stem)
        if not codec:
            log.warning(f"  Could not extract codec from {dir_name}/, skipping")
            continue

        log.info(f"  Registering: {dir_name}")
        log.info(f"    Input: {input_file.name}")
        log.info(f"    Codec: {codec}")
        log.info(f"    File:  {video_file.name}")

        entry = build_entry(provider, dir_name, codec, input_file, video_file)

        bitrate = entry["renditions"][0]["bitrate_kbps"]
        size_mb = entry["renditions"][0]["total_size_bytes"] / (1024 * 1024)
        log.info(f"    Bitrate: {bitrate} kbps, Size: {size_mb:.2f} MB")

        metadata.append(entry)
        added += 1

    save_metadata(metadata)

    log.info(f"\nDone: {added} added, {skipped} already registered")
    log.info(f"Metadata: {METADATA_FILE}")


def cmd_single(args):
    """Register a single output file."""
    input_file = Path(args.input_file).resolve()
    output_file = Path(args.output_file).resolve()

    if not input_file.exists():
        log.error(f"Input file not found: {input_file}")
        sys.exit(1)
    if not output_file.exists():
        log.error(f"Output file not found: {output_file}")
        sys.exit(1)

    input_stem = input_file.stem
    encoding_name = args.name or f"{input_stem}_{args.codec}"

    dest_dir = OUTPUTS_DIR / args.provider / encoding_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / output_file.name

    if dest_file.exists():
        log.info(f"Output already exists at {dest_file}")
    elif args.copy:
        log.info(f"Copying {output_file.name} to {dest_dir}/")
        shutil.copy2(str(output_file), str(dest_file))
    else:
        log.info(f"Moving {output_file.name} to {dest_dir}/")
        shutil.move(str(output_file), str(dest_file))

    metadata = load_metadata()
    entry = build_entry(args.provider, encoding_name, args.codec, input_file, dest_file)

    bitrate = entry["renditions"][0]["bitrate_kbps"]
    size_mb = entry["renditions"][0]["total_size_bytes"] / (1024 * 1024)
    log.info(f"  Bitrate: {bitrate} kbps, Size: {size_mb:.2f} MB")

    metadata.append(entry)
    save_metadata(metadata)

    log.info(f"\nRegistered: [{args.provider}] {encoding_name} ({args.codec})")


def main():
    parser = argparse.ArgumentParser(description="Register manually-encoded video outputs")
    parser.add_argument("--provider", required=True, help="Provider name (e.g. vidaio, ffmpeg)")
    parser.add_argument("--scan", action="store_true",
                        help="Scan data/outputs/<provider>/ and register all found video files")

    # Single-file mode args
    parser.add_argument("--input", dest="input_file", help="Path to the source input video")
    parser.add_argument("--output", dest="output_file", help="Path to the encoded output video")
    parser.add_argument("--codec", help="Codec used (e.g. av1, hevc, h264, vp9)")
    parser.add_argument("--name", default=None, help="Encoding name (default: auto-generated)")
    parser.add_argument("--copy", action="store_true", help="Copy output file (default: move)")
    args = parser.parse_args()

    if args.scan:
        cmd_scan(args)
    else:
        if not args.input_file or not args.output_file or not args.codec:
            parser.error("--input, --output, and --codec are required (or use --scan)")
        cmd_single(args)


if __name__ == "__main__":
    main()
