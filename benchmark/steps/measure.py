"""VMAF calculation (provider-agnostic)."""

import os
import sys
from pathlib import Path

from benchmark.metadata import load_metadata, save_vmaf_results
from benchmark.util.ffmpeg import (
    get_video_duration, remux_fmp4_to_mp4, compute_start_time,
    run_vmaf, extract_vmaf_score,
)
from benchmark.util.log import setup_logging

log = setup_logging("measure")


def run(config: dict, seed: int | None = None, duration: float | None = None,
        threads: int | None = None, model: str | None = None):
    """Run the measure (VMAF) step."""
    data_dir = Path(config["data_dir"])
    metadata_path = data_dir / "metadata.json"
    results_path = data_dir / "vmaf_results.json"

    vmaf_config = config.get("vmaf", {})
    threads = threads or vmaf_config.get("threads")
    model = model or vmaf_config.get("model")

    if duration is not None and seed is None:
        log.error("--duration requires --seed to pick a deterministic start point")
        sys.exit(1)

    if not metadata_path.exists():
        log.error(f"Metadata file not found: {metadata_path}")
        log.error("Run download or scan first.")
        sys.exit(1)

    metadata = load_metadata(metadata_path)
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

        video_duration = get_video_duration(input_path)
        input_size = os.path.getsize(input_path)
        log.info(f"  Input duration: {video_duration:.2f}s")
        log.info(f"  Input size: {input_size / (1024 * 1024):.1f} MB")

        start_time = None
        eval_duration = None

        if duration is not None:
            if duration >= video_duration:
                log.warning(f"  Requested duration ({duration}s) >= video ({video_duration:.2f}s), evaluating full video")
            else:
                eval_duration = duration
                start_time = compute_start_time(video_duration, eval_duration, seed)
                log.info(f"  Sampling: {eval_duration}s starting at {start_time}s (seed={seed})")

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
            "seed": seed,
            "renditions": [],
        }

        for rendition in sorted(encoding["renditions"], key=lambda r: r.get("bitrate_bps", 0)):
            bitrate_kbps = rendition.get("bitrate_kbps")
            local_file = rendition.get("local_file")
            local_dir = rendition.get("local_dir")

            label = f"{bitrate_kbps} kbps" if bitrate_kbps else os.path.basename(local_file or "unknown")
            log.info(f"\n  Rendition: {label}")

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
                    threads=threads,
                    model=model,
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

    save_vmaf_results(results_path, all_results)
    log.info(f"\nResults written to {results_path}")

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

        for r in enc["renditions"]:
            score = r["vmaf_score"]
            ratio = r.get("compression_ratio", "?")
            kbps = r.get("bitrate_kbps") or "?"
            if score is not None:
                log.info(f"    {kbps:>8} kbps | {ratio:>6}x compression -> VMAF {score:.4f}")
            else:
                log.info(f"    {kbps:>8} kbps | {ratio:>6}x compression -> ERROR: {r.get('error', 'unknown')}")
