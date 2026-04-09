#!/usr/bin/env python3
"""Compute clip metadata (SI, TI, resolution, duration) for prepared videos.

Uses OpenCV for SI/TI computation (12x faster than ffmpeg siti filter).

Usage:
    python -m benchmark.samples.compute_metadata data/samples/prepared report/data/clip_metadata.csv
"""

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

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
    """Compute average SI and TI using OpenCV."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {path}")

    si_values = []
    ti_values = []
    prev_frame = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # SI: Sobel magnitude std
        sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
        sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
        mag = cv2.magnitude(sx, sy)
        si_values.append(float(cv2.meanStdDev(mag)[1][0][0]))

        # TI: frame difference std
        if prev_frame is not None:
            diff = cv2.subtract(gray.astype(np.int16), prev_frame.astype(np.int16))
            ti_values.append(float(cv2.meanStdDev(diff)[1][0][0]))

        prev_frame = gray

    cap.release()

    si = sum(si_values) / len(si_values) if si_values else 0.0
    ti = sum(ti_values) / len(ti_values) if ti_values else 0.0
    return si, ti


def run(input_dir: Path, output_file: Path, workers: int = 8):
    catalog = load_catalog()
    clip_vertical = {s["id"]: s["vertical"] for s in catalog}

    videos = sorted(f for f in input_dir.iterdir() if f.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        print(f"No videos in {input_dir}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)

    columns = ["clip", "vertical", "resolution", "duration_s", "si", "ti", "input_size_bytes"]

    def process_video(video):
        clip = video.stem
        info = probe_video(video)
        si, ti = compute_si_ti(video)
        print(f"  {clip}: SI={si:.1f} TI={ti:.1f}")
        return {
            "clip": clip,
            "vertical": clip_vertical.get(clip, ""),
            "resolution": f"{info['width']}x{info['height']}",
            "duration_s": round(info["duration"], 1),
            "si": round(si, 1),
            "ti": round(ti, 1),
            "input_size_bytes": info["size"],
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_video, v): v for v in videos}
        rows = []
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda r: r["clip"])

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(videos)} clips -> {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute clip metadata (SI, TI)")
    parser.add_argument("input_dir", type=Path, help="Directory with prepared videos")
    parser.add_argument("output_file", type=Path, help="Output CSV path")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers (default: 8)")
    args = parser.parse_args()
    run(args.input_dir, args.output_file, workers=args.workers)
