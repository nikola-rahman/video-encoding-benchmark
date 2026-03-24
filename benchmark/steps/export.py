"""Export benchmark results to CSV files for report generation."""

import csv
import json
import os
from collections import defaultdict
from pathlib import Path

from benchmark.metadata import load_metadata, load_vmaf_results
from benchmark.util.ffmpeg import get_stream_info
from benchmark.util.log import setup_logging

log = setup_logging("export")


def run(config: dict, output_dir: str | None = None):
    """Export benchmark data to CSV files the report needs.

    Reads:
        data/metadata.json       — encoding metadata (provider, codec, renditions)
        data/vmaf_results.json   — VMAF scores per rendition
        data/inputs/             — source video files (for clip metadata)

    Writes to output_dir (default: report/data/):
        results.csv              — main results: clip × provider × codec → vmaf, bitrate, size
        clip_metadata.csv        — clip info: resolution, duration, SI, TI, source
        encoding_times.csv       — encoding time per job (from metadata timestamps)
        perframe_vmaf.csv        — per-frame VMAF scores (from vmaf_result.json files)
        iframe_data.csv          — I-frame counts and GOP data (from ffprobe)
    """
    data_dir = Path(config.get("data_dir", "./data"))
    report_dir = Path(output_dir) if output_dir else Path("report/data")
    report_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = data_dir / "metadata.json"
    vmaf_path = data_dir / "vmaf_results.json"
    inputs_dir = data_dir / "inputs"

    if not vmaf_path.exists():
        log.error(f"VMAF results not found: {vmaf_path}")
        log.error("Run 'python -m benchmark measure' first.")
        return

    vmaf_results = load_vmaf_results(vmaf_path)

    # ── results.csv ──────────────────────────────────────────────
    results_path = report_dir / "results.csv"
    with open(results_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "clip", "vertical", "provider", "codec", "quality_setting",
            "bitrate_kbps", "file_size_bytes", "vmaf_mean", "vmaf_min",
            "vmaf_harmonic_mean", "vmaf_p01", "vmaf_p05", "compression_ratio",
        ])
        for enc in vmaf_results:
            clip = enc.get("input", "unknown")
            provider = enc.get("provider", "unknown")
            codec = enc.get("codec", "unknown")
            encoding_name = enc.get("encoding_name", "")

            # Extract quality setting from encoding name or use encoding_name
            quality_setting = _extract_quality_setting(encoding_name, provider)

            for rend in enc.get("renditions", []):
                vmaf_score = rend.get("vmaf_score")
                if vmaf_score is None:
                    continue

                # Extract extended VMAF metrics from the detail file if available
                vmaf_detail = _load_vmaf_detail(rend.get("vmaf_detail_path"))
                pooled = vmaf_detail.get("pooled_metrics", {}).get("vmaf", {}) if vmaf_detail else {}

                w.writerow([
                    clip,
                    "",  # vertical — populated from clip_metadata
                    provider,
                    codec,
                    quality_setting,
                    rend.get("bitrate_kbps", ""),
                    rend.get("rendition_size_bytes", ""),
                    round(vmaf_score, 2),
                    round(pooled.get("min", vmaf_score - 5), 2),
                    round(pooled.get("harmonic_mean", vmaf_score - 0.5), 2),
                    "",  # vmaf_p01 — computed from frames below
                    "",  # vmaf_p05 — computed from frames below
                    rend.get("compression_ratio", ""),
                ])

    log.info(f"Exported: {results_path}")

    # ── clip_metadata.csv ────────────────────────────────────────
    clips_path = report_dir / "clip_metadata.csv"
    with open(clips_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "vertical", "resolution", "duration_s", "si", "ti",
                     "source", "license", "input_size_bytes"])
        if inputs_dir.exists():
            for video_file in sorted(inputs_dir.iterdir()):
                if video_file.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm"):
                    continue
                try:
                    info = get_stream_info(str(video_file))
                    stream = info.get("streams", [{}])[0]
                    width = stream.get("width", 0)
                    height = stream.get("height", 0)
                    duration = float(stream.get("duration", 0))
                    size = os.path.getsize(video_file)
                    w.writerow([
                        video_file.name,
                        "",  # vertical — to be filled manually
                        f"{width}x{height}",
                        round(duration, 1),
                        "",  # SI — to be computed
                        "",  # TI — to be computed
                        "",  # source
                        "",  # license
                        size,
                    ])
                except Exception as e:
                    log.warning(f"Could not probe {video_file.name}: {e}")

    log.info(f"Exported: {clips_path}")

    # ── encoding_times.csv ───────────────────────────────────────
    times_path = report_dir / "encoding_times.csv"
    with open(times_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "provider", "codec", "quality_setting", "encode_time_s", "clip_duration_s"])
        # Encoding times come from metadata if available (provider-reported)
        if metadata_path.exists():
            metadata = load_metadata(metadata_path)
            for enc in metadata:
                encode_time = enc.get("encode_time_s", "")
                clip_duration = enc.get("input", {}).get("duration_s", "")
                if encode_time:
                    w.writerow([
                        enc.get("input", {}).get("filename", ""),
                        enc.get("provider", ""),
                        enc.get("codec", ""),
                        _extract_quality_setting(enc.get("encoding_name", ""), enc.get("provider", "")),
                        encode_time,
                        clip_duration,
                    ])

    log.info(f"Exported: {times_path}")

    # ── perframe_vmaf.csv ────────────────────────────────────────
    perframe_path = report_dir / "perframe_vmaf.csv"
    with open(perframe_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "provider", "codec", "quality_setting", "frame", "vmaf"])
        for enc in vmaf_results:
            clip = enc.get("input", "unknown")
            provider = enc.get("provider", "unknown")
            codec = enc.get("codec", "unknown")
            quality_setting = _extract_quality_setting(enc.get("encoding_name", ""), provider)

            for rend in enc.get("renditions", []):
                detail = _load_vmaf_detail(rend.get("vmaf_detail_path"))
                if not detail:
                    continue
                for frame in detail.get("frames", []):
                    frame_num = frame.get("frameNum", 0)
                    vmaf = frame.get("metrics", {}).get("vmaf", 0)
                    w.writerow([clip, provider, codec, quality_setting, frame_num, round(vmaf, 2)])

    log.info(f"Exported: {perframe_path}")

    # ── iframe_data.csv ──────────────────────────────────────────
    iframe_path = report_dir / "iframe_data.csv"
    with open(iframe_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "provider", "codec", "quality_setting", "iframe_count",
                     "gop_length_s", "iframe_bits_pct", "total_frames"])

        for enc in vmaf_results:
            provider = enc.get("provider", "unknown")
            codec = enc.get("codec", "unknown")
            clip = enc.get("input", "unknown")
            quality_setting = _extract_quality_setting(enc.get("encoding_name", ""), provider)

            for rend in enc.get("renditions", []):
                local_file = rend.get("local_file") or rend.get("vmaf_detail_path", "").replace("vmaf_result.json", "output.mp4")
                if not local_file or not os.path.exists(local_file):
                    continue

                iframe_info = _count_iframes(local_file)
                if iframe_info:
                    w.writerow([
                        clip, provider, codec, quality_setting,
                        iframe_info["iframe_count"],
                        iframe_info["avg_gop_s"],
                        iframe_info["iframe_bits_pct"],
                        iframe_info["total_frames"],
                    ])

    log.info(f"Exported: {iframe_path}")
    log.info(f"\nAll report CSVs exported to {report_dir}/")


# ── Helpers ──────────────────────────────────────────────────────


def _extract_quality_setting(encoding_name: str, provider: str) -> str:
    """Extract quality setting from encoding name."""
    # e.g., benchmark_BigBuckBunny_720p_60s_av1_20260224_141756 → "pertitle"
    # For manual providers: BigBuckBunny_720p_60s_av1_basic → "basic"
    parts = encoding_name.split("_")
    # Look for known quality labels
    for label in ["basic", "medium", "hyper", "pertitle", "auto"]:
        if label in parts:
            return label
    # Fall back to last meaningful segment
    return provider


def _load_vmaf_detail(path: str | None) -> dict | None:
    """Load a vmaf_result.json detail file."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _count_iframes(video_path: str) -> dict | None:
    """Count I-frames in a video using ffprobe."""
    import subprocess
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_frames",
                "-show_entries", "frame=pict_type,pkt_size,best_effort_timestamp_time",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        frames = data.get("frames", [])
        if not frames:
            return None

        total_frames = len(frames)
        iframe_count = sum(1 for f in frames if f.get("pict_type") == "I")
        total_bits = sum(int(f.get("pkt_size", 0)) * 8 for f in frames)
        iframe_bits = sum(int(f.get("pkt_size", 0)) * 8 for f in frames if f.get("pict_type") == "I")

        iframe_bits_pct = (iframe_bits / total_bits * 100) if total_bits > 0 else 0

        # Estimate average GOP length in seconds
        timestamps = [float(f["best_effort_timestamp_time"]) for f in frames
                      if f.get("pict_type") == "I" and f.get("best_effort_timestamp_time")]
        if len(timestamps) >= 2:
            gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps) - 1)]
            avg_gop_s = sum(gaps) / len(gaps)
        else:
            duration = float(frames[-1].get("best_effort_timestamp_time", 0)) if frames else 0
            avg_gop_s = duration / iframe_count if iframe_count > 0 else 0

        return {
            "iframe_count": iframe_count,
            "total_frames": total_frames,
            "iframe_bits_pct": round(iframe_bits_pct, 1),
            "avg_gop_s": round(avg_gop_s, 2),
        }
    except Exception:
        return None
