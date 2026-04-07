#!/usr/bin/env python3
"""Prepare raw video samples into benchmark-ready inputs.

Re-encodes all videos to H.264 CRF 18, no audio, MP4 container.
Trims to specified duration if trim settings are in the catalog.
"""

import json
import subprocess
from pathlib import Path

from tqdm import tqdm

from benchmark.samples.catalog import load_catalog_raw, filter_catalog, find_raw_file


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name",
         "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    s = data.get("streams", [{}])[0]
    fmt = data.get("format", {})
    return {
        "width": s.get("width", 0),
        "height": s.get("height", 0),
        "codec": s.get("codec_name", "unknown"),
        "duration": float(fmt.get("duration", 0) or s.get("duration", 0)),
    }


def prepare_video(input_path: Path, output_path: Path, trim: dict | None = None) -> None:
    """Re-encode to H.264 CRF 18, no audio, with optional trim."""
    cmd = ["ffmpeg", "-y"]

    if trim:
        cmd += ["-ss", str(trim.get("start", 0))]

    cmd += ["-i", str(input_path)]

    if trim:
        cmd += ["-t", str(trim["duration"])]

    cmd += [
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")


def run(
    raw_dir: Path,
    output_dir: Path,
    verticals: list[str] | None = None,
    ids: list[str] | None = None,
    force: bool = False,
):
    catalog_data = load_catalog_raw()
    max_duration = catalog_data.get("max_duration")
    catalog = filter_catalog(catalog_data.get("sources", []), verticals, ids)
    if not catalog:
        print("No sources match filters.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    ready = []
    missing = []
    failed = []

    for source in tqdm(catalog, desc="Preparing", unit="video"):
        sid = source["id"]
        out_file = output_dir / f"{sid}.mp4"

        if not force and out_file.exists():
            ready.append(sid)
            continue

        raw_file = find_raw_file(source, raw_dir)
        if not raw_file:
            missing.append(sid)
            continue

        try:
            trim = source.get("trim")
            if not trim and max_duration:
                info = probe_video(raw_file)
                if info["duration"] > max_duration:
                    trim = {"start": 0, "duration": max_duration}

            prepare_video(raw_file, out_file, trim=trim)
            info = probe_video(out_file)
            tqdm.write(f"  {sid}: {info['width']}x{info['height']} {info['duration']:.0f}s {info['codec']}")
            ready.append(sid)
        except Exception as e:
            out_file.unlink(missing_ok=True)
            failed.append((sid, str(e)))

    print(f"\n{len(ready)} prepared, {len(missing)} missing, {len(failed)} failed")

    if missing:
        print(f"\nMissing raw files:")
        for sid in missing:
            print(f"  {sid}")

    if failed:
        for sid, err in failed:
            print(f"  FAILED {sid}: {err}")
        raise RuntimeError(f"{len(failed)} preparation(s) failed.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prepare raw samples into benchmark inputs")
    parser.add_argument("raw_dir", type=Path, help="Directory with raw downloads")
    parser.add_argument("output_dir", type=Path, help="Output directory for prepared files")
    parser.add_argument("--vertical", nargs="*")
    parser.add_argument("--id", nargs="*")
    parser.add_argument("--force", action="store_true", help="Re-encode even if output exists")
    args = parser.parse_args()
    run(raw_dir=args.raw_dir, output_dir=args.output_dir, verticals=args.vertical, ids=args.id, force=args.force)
