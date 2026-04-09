#!/usr/bin/env python3
"""Compute clip metadata (SI, TI, resolution, duration) for prepared videos.

Uses ffmpeg's siti filter for SI/TI computation.

Usage:
    python -m benchmark.samples.compute_metadata data/samples/prepared report/data/clip_metadata.csv
"""

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

from benchmark.samples.catalog import load_catalog

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-show_entries", "format=duration,size",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    s = data.get("streams", [{}])[0]
    fmt = data.get("format", {})
    return {
        "width": s.get("width", 0),
        "height": s.get("height", 0),
        "duration": float(fmt.get("duration", 0)),
        "size": int(fmt.get("size", 0)),
    }


def compute_si_ti(path: Path) -> tuple[float, float]:
    """Compute average SI and TI using ffmpeg's siti filter."""
    result = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path),
         "-vf", "siti=print_summary=1",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )

    output = result.stderr + result.stdout

    si_match = re.search(r"Spatial Information:\nAverage:\s*([\d.]+)", output)
    ti_match = re.search(r"Temporal Information:\nAverage:\s*([\d.]+)", output)

    si = float(si_match.group(1)) if si_match else 0.0
    ti = float(ti_match.group(1)) if ti_match else 0.0

    return si, ti


def run(input_dir: Path, output_file: Path):
    catalog = load_catalog()
    clip_vertical = {s["id"]: s["vertical"] for s in catalog}

    videos = sorted(f for f in input_dir.iterdir() if f.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        print(f"No videos in {input_dir}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)

    columns = ["clip", "vertical", "resolution", "duration_s", "si", "ti", "input_size_bytes"]

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        for video in videos:
            clip = video.stem
            print(f"  {clip}...", end=" ", flush=True)

            info = probe_video(video)
            si, ti = compute_si_ti(video)

            writer.writerow({
                "clip": clip,
                "vertical": clip_vertical.get(clip, ""),
                "resolution": f"{info['width']}x{info['height']}",
                "duration_s": round(info["duration"], 1),
                "si": round(si, 1),
                "ti": round(ti, 1),
                "input_size_bytes": info["size"],
            })
            print(f"SI={si:.1f} TI={ti:.1f}")

    print(f"\n{len(videos)} clips -> {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute clip metadata (SI, TI)")
    parser.add_argument("input_dir", type=Path, help="Directory with prepared videos")
    parser.add_argument("output_file", type=Path, help="Output CSV path")
    args = parser.parse_args()
    run(args.input_dir, args.output_file)
