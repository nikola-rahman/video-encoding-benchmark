#!/usr/bin/env python3
"""Run binary quality search on one or more providers.

Usage:
    # Single provider
    python -m benchmark.run_search --provider mediaconvert --codec h265 --video ecom_watch.mp4 --vmaf 93

    # Multiple providers in parallel
    python -m benchmark.run_search --provider mediaconvert zencoder bitmovin --codec h265 --video ecom_watch.mp4 --vmaf 93

    # Limit VMAF threads
    python -m benchmark.run_search --provider mediaconvert --codec h265 --video ecom_watch.mp4 --vmaf 93 --threads 8
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from benchmark.config import load_config
from benchmark.providers import get_provider
from benchmark.util.ffmpeg import run_vmaf, extract_vmaf_score

load_dotenv()


def make_measure_vmaf(threads: int | None = None):
    def measure_vmaf(reference: Path, distorted: Path) -> float:
        output_json = distorted.parent / f"{distorted.stem}_vmaf.json"
        vmaf_json = run_vmaf(
            reference_mp4=str(reference),
            distorted_mp4=str(distorted),
            output_json=str(output_json),
            threads=threads,
        )
        return extract_vmaf_score(vmaf_json)
    return measure_vmaf


def run_provider(provider_name, config, input_file, codec, target_vmaf, measure_vmaf, tolerance, max_steps):
    provider = get_provider(provider_name, config)
    result, vmaf, history = provider.encode_to_target_vmaf(
        input_file=input_file,
        codec=codec,
        target_vmaf=target_vmaf,
        measure_vmaf=measure_vmaf,
        tolerance=tolerance,
        max_steps=max_steps,
    )
    return provider_name, result, vmaf, history


def print_result(provider_name, result, vmaf, history):
    print(f"\n{'=' * 60}")
    print(f"{provider_name.upper()}")
    print(f"{'=' * 60}")
    print(f"Best quality: {history[-1]['quality']}")
    print(f"Best VMAF: {vmaf:.2f}")
    print(f"Encodes: {len(history)}")
    for h in history:
        print(f"  quality={h['quality']}  vmaf={h['vmaf']:.2f}  {h['encoding_name']}")
    if result.renditions:
        r = result.renditions[0]
        print(f"Output: {r.local_file}")
        print(f"Size: {r.total_size_bytes / (1024*1024):.1f} MB")
        print(f"Bitrate: {r.bitrate_bps / 1000:.0f} kbps")


def main():
    parser = argparse.ArgumentParser(description="Run binary quality search")
    parser.add_argument("--provider", required=True, nargs="+", help="Provider name(s)")
    parser.add_argument("--codec", required=True, help="Codec (h265, av1)")
    parser.add_argument("--video", required=True, help="Video filename")
    parser.add_argument("--vmaf", type=float, required=True, help="Target VMAF score")
    parser.add_argument("--tolerance", type=float, default=1.0, help="VMAF tolerance (default: 1.0)")
    parser.add_argument("--max-steps", type=int, default=8, help="Max search steps (default: 8)")
    parser.add_argument("--threads", type=int, default=None, help="VMAF threads")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    inputs_dir = Path(config["inputs"]["dir"])
    input_file = inputs_dir / args.video

    if not input_file.exists():
        print(f"Input file not found: {input_file}")
        return

    measure_vmaf = make_measure_vmaf(threads=args.threads)

    print(f"Providers: {', '.join(args.provider)}")
    print(f"Codec:     {args.codec}")
    print(f"Video:     {input_file}")
    print(f"Target:    VMAF {args.vmaf}")
    print(f"Tolerance: +{args.tolerance}")
    print(f"Threads:   {args.threads or 'auto'}")
    print()

    if len(args.provider) == 1:
        name, result, vmaf, history = run_provider(
            args.provider[0], config, input_file, args.codec,
            args.vmaf, measure_vmaf, args.tolerance, args.max_steps,
        )
        print_result(name, result, vmaf, history)
    else:
        with ThreadPoolExecutor(max_workers=len(args.provider)) as pool:
            futures = {
                pool.submit(
                    run_provider, name, config, input_file, args.codec,
                    args.vmaf, measure_vmaf, args.tolerance, args.max_steps,
                ): name
                for name in args.provider
            }
            for future in as_completed(futures):
                name, result, vmaf, history = future.result()
                print_result(name, result, vmaf, history)


if __name__ == "__main__":
    main()
