#!/usr/bin/env python3
"""
VMAF Benchmark Calculator
=========================
Calculates VMAF scores for Bitmovin-encoded renditions against their source inputs.

Handles fmp4 segment remuxing (init.mp4 + segment_*.m4s → clean MP4),
then runs the vmaf CLI via named pipes to avoid writing raw y4m to disk.

Prerequisites:
  - ffmpeg / ffprobe on PATH
  - vmaf CLI (v3.x) on PATH

Usage:
  python calculate_vmaf.py                          # full VMAF on all renditions
  python calculate_vmaf.py --seed 42 --duration 10  # 10-second sample, deterministic
  python calculate_vmaf.py --threads 8              # use 8 threads for vmaf
"""

import os
import sys
import json
import argparse
import logging
import random
import subprocess
import tempfile
import glob
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
METADATA_FILE = DATA_DIR / "metadata.json"
RESULTS_FILE = DATA_DIR / "vmaf_results.json"

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vmaf")

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def get_video_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    return float(result.stdout.strip())


def remux_fmp4_to_mp4(rendition_dir: str) -> str:
    """Concatenate init.mp4 + segment_*.m4s and remux to a clean MP4.
    Returns path to the remuxed file. Caches as rendition.mp4."""
    rendition_dir = Path(rendition_dir)
    output_mp4 = rendition_dir / "rendition.mp4"

    if output_mp4.exists():
        log.info(f"    Remuxed MP4 already exists: {output_mp4.name}")
        return str(output_mp4)

    init_file = rendition_dir / "init.mp4"
    segment_files = sorted(glob.glob(str(rendition_dir / "segment_*.m4s")))

    if not init_file.exists():
        raise FileNotFoundError(f"Missing init.mp4 in {rendition_dir}")
    if not segment_files:
        raise FileNotFoundError(f"No segment_*.m4s files in {rendition_dir}")

    # Concatenate init + segments into a temp fmp4 file, then remux
    concat_tmp = rendition_dir / "concat_tmp.fmp4"
    try:
        with open(concat_tmp, "wb") as out:
            with open(init_file, "rb") as f:
                out.write(f.read())
            for seg in segment_files:
                with open(seg, "rb") as f:
                    out.write(f.read())

        # Remux to clean MP4 (lossless, just container change)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(concat_tmp),
                "-c", "copy",
                str(output_mp4),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg remux failed: {result.stderr}")

        log.info(f"    Remuxed: {output_mp4.name} ({output_mp4.stat().st_size / 1024:.1f} KB)")
    finally:
        if concat_tmp.exists():
            concat_tmp.unlink()

    return str(output_mp4)


def compute_start_time(video_duration: float, sample_duration: float, seed: int) -> float:
    """Pick a deterministic random start time for sampling."""
    max_start = video_duration - sample_duration
    if max_start <= 0:
        return 0.0
    rng = random.Random(seed)
    return round(rng.uniform(0, max_start), 3)


def run_vmaf(
    reference_mp4: str,
    distorted_mp4: str,
    output_json: str,
    start_time: float | None = None,
    duration: float | None = None,
    threads: int | None = None,
    model: str | None = None,
) -> dict:
    """Run VMAF comparison using named pipes for y4m conversion.
    Returns parsed VMAF JSON result."""

    with tempfile.TemporaryDirectory() as tmpdir:
        ref_fifo = os.path.join(tmpdir, "ref.y4m")
        dist_fifo = os.path.join(tmpdir, "dist.y4m")
        os.mkfifo(ref_fifo)
        os.mkfifo(dist_fifo)

        # Build ffmpeg decode commands
        # -ss after -i: frame-accurate decode-based seeking, required because
        # fmp4-remuxed files may lack proper keyframe indices
        def build_ffmpeg_cmd(input_path, fifo_path):
            cmd = ["ffmpeg", "-v", "error", "-i", input_path]
            if start_time is not None:
                cmd += ["-ss", str(start_time)]
            if duration is not None:
                cmd += ["-t", str(duration)]
            cmd += ["-pix_fmt", "yuv420p", "-f", "yuv4mpegpipe", "-y", fifo_path]
            return cmd

        ref_cmd = build_ffmpeg_cmd(reference_mp4, ref_fifo)
        dist_cmd = build_ffmpeg_cmd(distorted_mp4, dist_fifo)

        # Build vmaf command
        vmaf_cmd = [
            "vmaf",
            "-r", ref_fifo,
            "-d", dist_fifo,
            "--json",
            "-o", output_json,
            "-q",
        ]
        if threads is not None:
            vmaf_cmd += ["--threads", str(threads)]
        if model:
            vmaf_cmd += ["-m", model]

        # Launch ffmpeg decoders in background, then vmaf reads from fifos
        ref_proc = subprocess.Popen(ref_cmd, stderr=subprocess.PIPE)
        dist_proc = subprocess.Popen(dist_cmd, stderr=subprocess.PIPE)
        vmaf_result = subprocess.run(vmaf_cmd, capture_output=True, text=True)

        # Wait for ffmpeg processes
        ref_proc.wait()
        dist_proc.wait()

        if ref_proc.returncode != 0:
            stderr = ref_proc.stderr.read().decode() if ref_proc.stderr else ""
            raise RuntimeError(f"ffmpeg (reference) failed: {stderr}")
        if dist_proc.returncode != 0:
            stderr = dist_proc.stderr.read().decode() if dist_proc.stderr else ""
            raise RuntimeError(f"ffmpeg (distorted) failed: {stderr}")
        if vmaf_result.returncode != 0:
            raise RuntimeError(f"vmaf failed: {vmaf_result.stderr}")

    # Parse result
    with open(output_json) as f:
        return json.load(f)


def extract_vmaf_score(vmaf_json: dict) -> float:
    """Extract the mean VMAF score from vmaf JSON output."""
    # vmaf v3 JSON structure: pooled_metrics.vmaf.mean
    pooled = vmaf_json.get("pooled_metrics", {})
    vmaf_metric = pooled.get("vmaf", {})
    mean = vmaf_metric.get("mean")
    if mean is not None:
        return mean

    # Fallback: compute from per-frame scores
    frames = vmaf_json.get("frames", [])
    if frames:
        scores = [f["metrics"]["vmaf"] for f in frames if "vmaf" in f.get("metrics", {})]
        if scores:
            return sum(scores) / len(scores)

    raise ValueError("Could not extract VMAF score from results")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Calculate VMAF scores for benchmark renditions")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for deterministic sampling start point")
    parser.add_argument("--duration", type=float, default=None,
                        help="Duration in seconds of video segment to evaluate (requires --seed)")
    parser.add_argument("--threads", type=int, default=None,
                        help="Number of threads for vmaf (default: auto)")
    parser.add_argument("--model", type=str, default=None,
                        help="VMAF model param string (e.g. 'version=vmaf_v0.6.1')")
    args = parser.parse_args()

    if args.duration is not None and args.seed is None:
        parser.error("--duration requires --seed to pick a deterministic start point")

    if not METADATA_FILE.exists():
        log.error(f"Metadata file not found: {METADATA_FILE}")
        log.error("Run download_results.py first.")
        sys.exit(1)

    with open(METADATA_FILE) as f:
        metadata = json.load(f)

    all_results = []

    for encoding in metadata:
        input_path = encoding["input"]["local_path"]
        if not input_path or not os.path.exists(input_path):
            log.error(f"Input file not found: {input_path}")
            continue

        provider = encoding.get("provider", "unknown")

        log.info(f"\n{'=' * 60}")
        log.info(f"Provider: {provider}")
        log.info(f"Encoding: {encoding['encoding_name']}")
        log.info(f"Codec:    {encoding['codec']}")
        log.info(f"Input:    {encoding['input']['filename']}")
        log.info(f"{'=' * 60}")

        # Get video duration for sampling
        video_duration = get_video_duration(input_path)
        input_size = os.path.getsize(input_path)
        log.info(f"  Input duration: {video_duration:.2f}s")
        log.info(f"  Input size: {input_size / (1024 * 1024):.1f} MB")

        start_time = None
        eval_duration = None

        if args.duration is not None:
            if args.duration >= video_duration:
                log.warning(f"  Requested duration ({args.duration}s) >= video ({video_duration:.2f}s), evaluating full video")
            else:
                eval_duration = args.duration
                start_time = compute_start_time(video_duration, eval_duration, args.seed)
                log.info(f"  Sampling: {eval_duration}s starting at {start_time}s (seed={args.seed})")

        encoding_results = {
            "provider": provider,
            "encoding_id": encoding.get("encoding_id"),
            "encoding_name": encoding["encoding_name"],
            "codec": encoding["codec"],
            "input": encoding["input"]["filename"],
            "input_size_bytes": input_size,
            "input_duration_s": video_duration,
            "sample_start_s": start_time,
            "sample_duration_s": eval_duration,
            "seed": args.seed,
            "renditions": [],
        }

        for rendition in sorted(encoding["renditions"], key=lambda r: r.get("bitrate_bps", 0)):
            bitrate_kbps = rendition.get("bitrate_kbps")
            local_file = rendition.get("local_file")
            local_dir = rendition.get("local_dir")

            label = f"{bitrate_kbps} kbps" if bitrate_kbps else os.path.basename(local_file or "unknown")
            log.info(f"\n  Rendition: {label}")

            # Get the distorted MP4: either a single file or remux from fmp4 segments
            if local_file:
                distorted_mp4 = local_file
                if not os.path.exists(distorted_mp4):
                    log.error(f"    File not found: {distorted_mp4}")
                    continue
            elif local_dir:
                log.info(f"    Remuxing fmp4 segments...")
                try:
                    distorted_mp4 = remux_fmp4_to_mp4(local_dir)
                except Exception as e:
                    log.error(f"    Remux failed: {e}")
                    continue
            else:
                log.error(f"    No local_file or local_dir in rendition")
                continue

            rendition_size = os.path.getsize(distorted_mp4)
            compression_ratio = input_size / rendition_size if rendition_size > 0 else 0
            log.info(f"    Size: {rendition_size / (1024 * 1024):.2f} MB (compression: {compression_ratio:.1f}x)")

            # Step 2: Run VMAF
            vmaf_dir = local_dir or os.path.dirname(local_file)
            vmaf_output = os.path.join(vmaf_dir, "vmaf_result.json")
            log.info(f"    Running VMAF...")

            try:
                vmaf_json = run_vmaf(
                    reference_mp4=input_path,
                    distorted_mp4=distorted_mp4,
                    output_json=vmaf_output,
                    start_time=start_time,
                    duration=eval_duration,
                    threads=args.threads,
                    model=args.model,
                )
                vmaf_score = extract_vmaf_score(vmaf_json)
                log.info(f"    VMAF score: {vmaf_score:.4f}")

                frame_count = len(vmaf_json.get("frames", []))

                encoding_results["renditions"].append({
                    "bitrate_bps": rendition.get("bitrate_bps", 0),
                    "bitrate_kbps": bitrate_kbps,
                    "rendition_size_bytes": rendition_size,
                    "compression_ratio": round(compression_ratio, 2),
                    "vmaf_score": round(vmaf_score, 4),
                    "frame_count": frame_count,
                    "vmaf_detail_path": vmaf_output,
                })

            except Exception as e:
                log.error(f"    VMAF failed: {e}")
                encoding_results["renditions"].append({
                    "bitrate_bps": rendition.get("bitrate_bps", 0),
                    "bitrate_kbps": bitrate_kbps,
                    "rendition_size_bytes": rendition_size,
                    "compression_ratio": round(compression_ratio, 2),
                    "vmaf_score": None,
                    "error": str(e),
                })

        encoding_results["renditions"].sort(key=lambda r: r["bitrate_bps"])
        all_results.append(encoding_results)

    # Write results
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2)
    log.info(f"\nResults written to {RESULTS_FILE}")

    # Rate-distortion plot
    log.info(f"\nGenerating rate-distortion plots...")
    plot_rate_distortion(all_results, str(DATA_DIR))

    # Summary
    log.info(f"\n{'=' * 60}")
    log.info("VMAF RESULTS SUMMARY")
    log.info(f"{'=' * 60}")
    for enc in all_results:
        log.info(f"\n  [{enc['provider']}] {enc['encoding_name']} ({enc['codec']})")
        if enc["sample_duration_s"]:
            log.info(f"  Sample: {enc['sample_duration_s']}s @ {enc['sample_start_s']}s (seed={enc['seed']})")
        else:
            log.info(f"  Full video: {enc['input_duration_s']:.2f}s")

        # Sort by bitrate for display
        sorted_renditions = sorted(enc["renditions"], key=lambda r: r["bitrate_bps"])
        for r in sorted_renditions:
            score = r["vmaf_score"]
            ratio = r.get("compression_ratio", "?")
            kbps = r.get("bitrate_kbps") or "?"
            if score is not None:
                log.info(f"    {kbps:>8} kbps | {ratio:>6}x compression → VMAF {score:.4f}")
            else:
                log.info(f"    {kbps:>8} kbps | {ratio:>6}x compression → ERROR: {r.get('error', 'unknown')}")


def plot_rate_distortion(results, output_dir):
    """Plot rate-distortion curves (VMAF vs bitrate) grouped by input video."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not installed, skipping rate-distortion plot (pip install matplotlib)")
        return

    # Group renditions by input video
    by_input = {}
    for enc in results:
        input_name = enc["input"]
        if input_name not in by_input:
            by_input[input_name] = {}
        provider = enc["provider"]
        if provider not in by_input[input_name]:
            by_input[input_name][provider] = []
        for r in enc["renditions"]:
            if r["vmaf_score"] is not None:
                by_input[input_name][provider].append({
                    "bitrate_kbps": r["bitrate_kbps"] or r["bitrate_bps"] / 1000,
                    "vmaf": r["vmaf_score"],
                })

    markers = ["o", "s", "^", "D", "v", "P", "*"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

    for input_name, providers in by_input.items():
        fig, ax = plt.subplots(figsize=(10, 6))

        for i, (provider, points) in enumerate(sorted(providers.items())):
            points.sort(key=lambda p: p["bitrate_kbps"])
            bitrates = [p["bitrate_kbps"] for p in points]
            vmafs = [p["vmaf"] for p in points]
            color = colors[i % len(colors)]
            marker = markers[i % len(markers)]
            ax.plot(bitrates, vmafs, marker=marker, color=color, label=provider,
                    linewidth=2, markersize=8)
            for br, vm in zip(bitrates, vmafs):
                ax.annotate(f"{vm:.1f}", (br, vm), textcoords="offset points",
                            xytext=(5, 8), fontsize=8, color=color)

        ax.set_xlabel("Bitrate (kbps)", fontsize=12)
        ax.set_ylabel("VMAF Score", fontsize=12)
        ax.set_title(f"Rate-Distortion: {input_name}", fontsize=14)
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(bottom=max(0, ax.get_ylim()[0] - 5), top=min(100, ax.get_ylim()[1] + 2))

        plot_path = os.path.join(output_dir, f"rd_curve_{input_name.replace('.', '_')}.png")
        fig.tight_layout()
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)
        log.info(f"  Rate-distortion plot: {plot_path}")


if __name__ == "__main__":
    main()
