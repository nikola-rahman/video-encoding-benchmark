#!/usr/bin/env python3
"""Compute clip metadata (SI, TI, resolution, duration) for prepared videos.

Usage:
    python -m benchmark.samples.compute_metadata data/samples/prepared data/results/clip_metadata.csv
"""

import argparse
import csv
import json
import subprocess
from pathlib import Path

from benchmark.samples.catalog import load_catalog

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name,duration,r_frame_rate,nb_frames",
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
        "duration": float(fmt.get("duration", 0) or s.get("duration", 0)),
        "size": int(fmt.get("size", 0)),
    }


def compute_si_ti(path: Path) -> tuple[float, float]:
    """Compute Spatial Information (SI) and Temporal Information (TI)."""
    # SI: std of Sobel-filtered frames
    si_cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-vf", "sobel,metadata=print:file=-",
        "-f", "null", "-",
    ]
    # Use simpler approach: compute SI/TI via signalstats filter
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-vf", "signalstats=stat=tout+vrep+brng,metadata=print:file=-",
        "-f", "null", "-",
    ]
    # Simplest reliable approach: compute SI as avg of per-frame Sobel std,
    # TI as avg of per-frame difference std

    # SI: average spatial complexity via edge detection
    si_result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", "sobel,mestimate,metadata=print:file=/dev/stdout",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )

    # Fallback: use simpler approach with two-pass
    # Pass 1: compute SI (Sobel standard deviation per frame)
    si_val = _compute_si(path)
    ti_val = _compute_ti(path)

    return si_val, ti_val


def _compute_si(path: Path) -> float:
    """Compute Spatial Information as mean of per-frame Sobel energy."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", "sobel,crop=iw:ih:0:0,entropy",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    # Simpler: just use the raw pixel variance approach
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", "sobel",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    if not result.stdout:
        return 0.0

    import numpy as np
    pixels = np.frombuffer(result.stdout, dtype=np.uint8)
    return float(np.std(pixels))


def _compute_ti(path: Path) -> float:
    """Compute Temporal Information as mean of inter-frame differences."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", "tblend=all_mode=difference",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    if not result.stdout:
        return 0.0

    import numpy as np
    pixels = np.frombuffer(result.stdout, dtype=np.uint8)
    return float(np.std(pixels))


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
