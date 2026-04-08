#!/usr/bin/env python3
"""Run binary quality search across providers and videos.

Writes a JSONL audit log to data/results/run_<timestamp>.jsonl with every
event: search starts, encodes, VMAF measurements, convergence.

Usage:
    python -m benchmark.run_search --provider mediaconvert zencoder bitmovin --codec h265 --vertical ecommerce --vmaf 93
    python -m benchmark.run_search --provider mediaconvert --codec h265 --video ecom_watch.mp4 --vmaf 93 --vmaf-threads 8
"""

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from benchmark.config import load_config
from benchmark.providers import get_provider
from benchmark.samples.catalog import load_catalog, filter_catalog
from benchmark.util.ffmpeg import run_vmaf, extract_vmaf_score

load_dotenv()


class EventLog:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data):
        entry = {"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
        line = json.dumps(entry)
        with self._lock:
            with open(self._path, "a") as f:
                f.write(line + "\n")
        return entry


def make_measure_vmaf(vmaf_threads: int | None = None, semaphore: threading.Semaphore | None = None):
    def measure_vmaf(reference: Path, distorted: Path) -> float:
        output_json = distorted.parent / f"{distorted.stem}_vmaf.json"
        if semaphore:
            semaphore.acquire()
        try:
            vmaf_json = run_vmaf(
                reference_mp4=str(reference),
                distorted_mp4=str(distorted),
                output_json=str(output_json),
                threads=vmaf_threads,
            )
            return extract_vmaf_score(vmaf_json)
        finally:
            if semaphore:
                semaphore.release()
    return measure_vmaf


def run_one_search(provider_name, config, input_file, codec, target_vmaf, measure_vmaf, tolerance, max_steps, event_log):
    input_size = input_file.stat().st_size

    event_log.log("search_start",
                  provider=provider_name, clip=input_file.stem, codec=codec,
                  target_vmaf=target_vmaf, input_size_bytes=input_size)

    provider = get_provider(provider_name, config)
    result, vmaf, history = provider.encode_to_target_vmaf(
        input_file=input_file,
        codec=codec,
        target_vmaf=target_vmaf,
        measure_vmaf=measure_vmaf,
        tolerance=tolerance,
        max_steps=max_steps,
    )

    converged = vmaf >= target_vmaf
    output_file = ""
    vmaf_json_path = ""
    file_size = 0
    bitrate = 0

    if result and result.renditions:
        r = result.renditions[0]
        output_file = str(r.local_file)
        vmaf_json_path = str(r.local_file.parent / f"{r.local_file.stem}_vmaf.json")
        file_size = r.total_size_bytes
        bitrate = round(r.bitrate_bps / 1000, 1)

    for i, h in enumerate(history):
        event_log.log("search_probe",
                      provider=provider_name, clip=input_file.stem, codec=codec,
                      target_vmaf=target_vmaf, quality_setting=h["quality"],
                      vmaf_harmonic_mean=round(h["vmaf"], 2),
                      encoding_name=h["encoding_name"], step=i + 1)

    event_log.log("search_complete",
                  provider=provider_name, clip=input_file.stem, codec=codec,
                  target_vmaf=target_vmaf, converged=converged,
                  quality_setting=history[-1]["quality"] if history else None,
                  vmaf_harmonic_mean=round(vmaf, 2),
                  output_file=output_file, vmaf_json=vmaf_json_path,
                  file_size_bytes=file_size, bitrate_kbps=bitrate,
                  input_size_bytes=input_size, steps=len(history))

    status = "CONVERGED" if converged else "NOT CONVERGED"
    print(f"  {provider_name} — {input_file.name}: {status} VMAF {vmaf:.2f} | {bitrate} kbps | {file_size/(1024*1024):.1f} MB | {len(history)} steps")


def resolve_videos(args, config):
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
    parser.add_argument("--vmaf-threads", type=int, default=None, help="VMAF threads per measurement")
    parser.add_argument("--vmaf-workers", type=int, default=8, help="Max concurrent VMAF measurements (default: 8)")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    videos = resolve_videos(args, config)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = Path("data/results") / f"run_{timestamp}.jsonl"
    event_log = EventLog(log_path)

    semaphore = threading.Semaphore(args.vmaf_workers)
    measure_vmaf = make_measure_vmaf(vmaf_threads=args.vmaf_threads, semaphore=semaphore)

    tasks = [(p, v) for p in args.provider for v in videos]

    event_log.log("run_start",
                  providers=args.provider, codec=args.codec,
                  videos=[v.name for v in videos], target_vmaf=args.vmaf,
                  tolerance=args.tolerance, max_steps=args.max_steps,
                  vmaf_threads=args.vmaf_threads, vmaf_workers=args.vmaf_workers)

    print(f"Providers:    {', '.join(args.provider)}")
    print(f"Codec:        {args.codec}")
    print(f"Videos:       {len(videos)}")
    print(f"Tasks:        {len(tasks)}")
    print(f"Target:       VMAF {args.vmaf}")
    print(f"Log:          {log_path}")
    print()

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {
            pool.submit(
                run_one_search, pname, config, video, args.codec,
                args.vmaf, measure_vmaf, args.tolerance, args.max_steps, event_log,
            ): (pname, video.name)
            for pname, video in tasks
        }
        for future in as_completed(futures):
            pname, vname = futures[future]
            try:
                future.result()
            except Exception as e:
                event_log.log("search_error", provider=pname, clip=vname, error=str(e))
                print(f"  FAILED: {pname} — {vname}: {e}")

    event_log.log("run_complete", tasks=len(tasks))
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
