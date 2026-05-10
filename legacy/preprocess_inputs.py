#!/usr/bin/env python3
"""
Preprocess Input Videos
========================
Validates and fixes common issues with input videos before benchmarking:
  - B-frame flush: h264 with B-frames can produce extra decoded frames
    at the end when trimmed with -c copy. Fix: re-encode with -bf 0 -qp 0.
  - Duration alignment: ensures exact duration with no trailing partial frames.
  - Audio removal: strips audio tracks (not needed for video quality benchmarks).

Usage:
  python preprocess_inputs.py                    # check all inputs in data/inputs/
  python preprocess_inputs.py --fix              # fix any issues found
  python preprocess_inputs.py --file video.mp4   # check/fix a specific file
"""

import os
import sys
import argparse
import logging
import subprocess
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
INPUTS_DIR = DATA_DIR / "inputs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("preprocess")


def get_stream_info(path):
    """Get video stream info via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames,duration,codec_name,width,height,r_frame_rate,pix_fmt",
            "-of", "json",
            path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    import json
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {path}")
    return streams[0]


def has_audio(path):
    """Check if file has audio streams."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            path,
        ],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def count_decoded_frames(path, width, height):
    """Count actual decoded frames by decoding to raw video."""
    frame_bytes = width * height * 3 // 2  # yuv420p
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-i", path,
            "-pix_fmt", "yuv420p",
            "-f", "rawvideo", "-c:v", "rawvideo", "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {result.stderr.decode()}")
    total_bytes = len(result.stdout)
    return total_bytes // frame_bytes


def check_video(path):
    """Check a video file for common issues. Returns list of issues found."""
    path = str(path)
    issues = []

    info = get_stream_info(path)
    width = int(info["width"])
    height = int(info["height"])
    container_frames = int(info.get("nb_frames", 0))
    codec = info.get("codec_name", "unknown")
    duration = float(info.get("duration", 0))

    log.info(f"  Codec: {codec}, {width}x{height}, {container_frames} frames, {duration:.3f}s")

    # Check 1: Audio tracks
    if has_audio(path):
        issues.append({
            "type": "audio",
            "message": "Contains audio tracks (unnecessary for video quality benchmark)",
        })

    # Check 2: Frame count mismatch (B-frame flush issue)
    decoded_frames = count_decoded_frames(path, width, height)
    if decoded_frames != container_frames:
        issues.append({
            "type": "frame_mismatch",
            "message": f"Decoded {decoded_frames} frames but container says {container_frames} "
                       f"(likely B-frame flush from mid-GOP trim)",
            "decoded": decoded_frames,
            "container": container_frames,
        })
    else:
        log.info(f"  Frame count OK: {decoded_frames} decoded == {container_frames} in container")

    # Check 3: Non-integer duration (sign of imprecise trim)
    frac = duration % 1.0
    if frac > 0.001 and frac < 0.999:
        issues.append({
            "type": "fractional_duration",
            "message": f"Duration {duration:.6f}s is not a clean integer second boundary",
        })

    return issues, info


def fix_video(path, issues):
    """Fix issues by re-encoding with lossless h264, no B-frames, no audio."""
    path = Path(path)
    tmp_path = path.with_suffix(".tmp.mp4")

    info = get_stream_info(str(path))
    duration = float(info.get("duration", 0))
    # Round down to nearest integer second for clean duration
    target_duration = int(duration)

    log.info(f"  Re-encoding: lossless h264, no B-frames, no audio, {target_duration}s")
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(path),
            "-t", str(target_duration),
            "-c:v", "libx264", "-qp", "0", "-bf", "0",
            "-an",
            str(tmp_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Re-encode failed: {result.stderr}")

    # Replace original
    shutil.move(str(tmp_path), str(path))
    log.info(f"  Fixed: {path.name} ({path.stat().st_size / (1024 * 1024):.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Preprocess input videos for benchmarking")
    parser.add_argument("--fix", action="store_true", help="Fix any issues found")
    parser.add_argument("--file", nargs="*", help="Specific file(s) to check (default: all in data/inputs/)")
    args = parser.parse_args()

    if args.file:
        files = [Path(f) for f in args.file]
    else:
        if not INPUTS_DIR.exists():
            log.error(f"Inputs directory not found: {INPUTS_DIR}")
            sys.exit(1)
        files = sorted(INPUTS_DIR.glob("*.mp4"))

    if not files:
        log.info("No video files found.")
        return

    all_ok = True
    for f in files:
        log.info(f"\nChecking: {f.name}")
        try:
            issues, info = check_video(f)
        except Exception as e:
            log.error(f"  Error: {e}")
            all_ok = False
            continue

        if not issues:
            log.info(f"  OK")
            continue

        all_ok = False
        for issue in issues:
            log.warning(f"  ISSUE [{issue['type']}]: {issue['message']}")

        if args.fix:
            log.info(f"  Fixing...")
            try:
                fix_video(f, issues)
                # Verify fix
                issues_after, _ = check_video(f)
                if issues_after:
                    for issue in issues_after:
                        log.error(f"  Still broken [{issue['type']}]: {issue['message']}")
                else:
                    log.info(f"  Verified: all issues fixed")
            except Exception as e:
                log.error(f"  Fix failed: {e}")

    if all_ok:
        log.info("\nAll inputs OK.")
    elif not args.fix:
        log.info("\nIssues found. Run with --fix to resolve them.")


if __name__ == "__main__":
    main()
