#!/usr/bin/env python3
"""Run binary quality search across providers and videos.

Usage:
    # Single video, single provider
    python -m benchmark.run_search --provider mediaconvert --codec h265 --video ecom_watch.mp4 --vmaf 93

    # Single video, multiple providers in parallel
    python -m benchmark.run_search --provider mediaconvert zencoder bitmovin --codec h265 --video ecom_watch.mp4 --vmaf 93

    # All videos in a vertical, multiple providers
    python -m benchmark.run_search --provider mediaconvert zencoder bitmovin --codec h265 --vertical ecommerce --vmaf 93

    # Limit VMAF threads
    python -m benchmark.run_search --provider mediaconvert --codec h265 --vertical ecommerce --vmaf 93 --threads 8
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from benchmark.config import load_config
from benchmark.providers import get_provider
from benchmark.samples.catalog import load_catalog, filter_catalog
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
    return provider_name, input_file.name, result, vmaf, history


def print_result(provider_name, video_name, result, vmaf, history):
    print(f"\n{'=' * 60}")
    print(f"{provider_name.upper()} — {video_name}")
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


def resolve_videos(args, config):
    """Resolve video files from --video or --vertical arguments."""
    inputs_dir = Path(config["inputs"]["dir"])

    if args.video:
        files = [inputs_dir / v for v in args.video]
        for f in files:
            if not f.exists():
                raise FileNotFoundError(f"Input file not found: {f}")
        return files

    if args.vertical:
        catalog = filter_catalog(load_catalog(), verticals=args.vertical)
        files = []
        for source in catalog:
            f = inputs_dir / f"{source['id']}.mp4"
            if f.exists():
                files.append(f)
            else:
                print(f"Warning: {f} not found, skipping")
        if not files:
            raise FileNotFoundError(f"No prepared videos found for verticals: {args.vertical}")
        return files

    raise ValueError("Either --video or --vertical is required")


def main():
    parser = argparse.ArgumentParser(description="Run binary quality search")
    parser.add_argument("--provider", required=True, nargs="+", help="Provider name(s)")
    parser.add_argument("--codec", required=True, help="Codec (h265, av1)")
    video_group = parser.add_mutually_exclusive_group(required=True)
    video_group.add_argument("--video", nargs="+", help="Video filename(s)")
    video_group.add_argument("--vertical", nargs="+", help="Vertical(s) from catalog")
    parser.add_argument("--vmaf", type=float, required=True, help="Target VMAF score")
    parser.add_argument("--tolerance", type=float, default=1.0, help="VMAF tolerance (default: 1.0)")
    parser.add_argument("--max-steps", type=int, default=8, help="Max search steps (default: 8)")
    parser.add_argument("--threads", type=int, default=None, help="VMAF threads")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    videos = resolve_videos(args, config)
    measure_vmaf = make_measure_vmaf(threads=args.threads)

    print(f"Providers: {', '.join(args.provider)}")
    print(f"Codec:     {args.codec}")
    print(f"Videos:    {len(videos)}")
    for v in videos:
        print(f"  {v.name}")
    print(f"Target:    VMAF {args.vmaf}")
    print(f"Tolerance: +{args.tolerance}")
    print(f"Threads:   {args.threads or 'auto'}")
    print()

    # Build all (provider, video) combinations
    tasks = [(p, v) for v in videos for p in args.provider]

    with ThreadPoolExecutor(max_workers=len(args.provider)) as pool:
        futures = {
            pool.submit(
                run_provider, provider_name, config, video, args.codec,
                args.vmaf, measure_vmaf, args.tolerance, args.max_steps,
            ): (provider_name, video.name)
            for provider_name, video in tasks
        }
        for future in as_completed(futures):
            try:
                name, video_name, result, vmaf, history = future.result()
                print_result(name, video_name, result, vmaf, history)
            except Exception as e:
                pname, vname = futures[future]
                print(f"\nFAILED: {pname} — {vname}: {e}")


if __name__ == "__main__":
    main()
