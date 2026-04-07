#!/usr/bin/env python3
"""Run binary quality search on a single video with a single provider.

Usage:
    python -m benchmark.run_search --provider mediaconvert --codec h265 --video ecom_watch.mp4 --vmaf 93
"""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from benchmark.config import load_config
from benchmark.providers import get_provider
from benchmark.util.ffmpeg import run_vmaf, extract_vmaf_score

load_dotenv()


def measure_vmaf(reference: Path, distorted: Path) -> float:
    """Measure VMAF between two files."""
    output_json = distorted.parent / f"{distorted.stem}_vmaf.json"
    vmaf_json = run_vmaf(
        reference_mp4=str(reference),
        distorted_mp4=str(distorted),
        output_json=str(output_json),
    )
    return extract_vmaf_score(vmaf_json)


def main():
    parser = argparse.ArgumentParser(description="Run binary quality search on a single video")
    parser.add_argument("--provider", required=True, help="Provider name (e.g. mediaconvert)")
    parser.add_argument("--codec", required=True, help="Codec (h265, av1)")
    parser.add_argument("--video", required=True, help="Video filename (e.g. ecom_watch.mp4)")
    parser.add_argument("--vmaf", type=float, required=True, help="Target VMAF score")
    parser.add_argument("--tolerance", type=float, default=1.0, help="VMAF tolerance (default: 1.0)")
    parser.add_argument("--max-steps", type=int, default=8, help="Max binary search steps (default: 8)")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    provider = get_provider(args.provider, config)

    inputs_dir = Path(config["inputs"]["dir"])
    input_file = inputs_dir / args.video

    if not input_file.exists():
        print(f"Input file not found: {input_file}")
        return

    print(f"Provider:  {args.provider}")
    print(f"Codec:     {args.codec}")
    print(f"Video:     {input_file}")
    print(f"Target:    VMAF {args.vmaf}")
    print(f"Tolerance: +{args.tolerance}")
    print(f"Max steps: {args.max_steps}")
    print()

    result, vmaf, history = provider.encode_to_target_vmaf(
        input_file=input_file,
        codec=args.codec,
        target_vmaf=args.vmaf,
        measure_vmaf=measure_vmaf,
        tolerance=args.tolerance,
        max_steps=args.max_steps,
    )

    print(f"\n{'=' * 60}")
    print(f"RESULT")
    print(f"{'=' * 60}")
    print(f"Best quality setting: {history[-1]['quality']:.2f}")
    print(f"Best VMAF: {vmaf:.2f}")
    print(f"Encodes used: {len(history)}")
    print(f"\nHistory:")
    for h in history:
        print(f"  quality={h['quality']:.2f}  vmaf={h['vmaf']:.2f}  {h['encoding_name']}")

    if result.renditions:
        r = result.renditions[0]
        print(f"\nOutput: {r.local_file}")
        print(f"Size: {r.total_size_bytes / (1024*1024):.1f} MB")
        print(f"Bitrate: {r.bitrate_bps / 1000:.0f} kbps")


if __name__ == "__main__":
    main()
