#!/usr/bin/env python3
"""Evaluate pre-encoded files against reference videos.

Scans an output directory for files matching the naming convention
<clip>_<codec>_vmaf<target>.mp4, measures VMAF and bitrate against
the prepared reference, and writes JSONL events compatible with
benchmark.encode output.

Usage:
    python -m benchmark.evaluate --provider vidaio --dir data/outputs/vidaio --vmaf-threads 8
"""

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from benchmark.config import load_config
from benchmark.encode import EventLog, make_measure_vmaf
from benchmark.samples.catalog import load_catalog
from benchmark.util.ffmpeg import get_actual_bitrate

load_dotenv()

FILENAME_PATTERN = re.compile(
    r"^(?P<clip>.+)_(?P<codec>h265|av1)_vmaf(?P<target>\d+)\.mp4$"
)


def parse_filename(path: Path) -> dict | None:
    m = FILENAME_PATTERN.match(path.name)
    if not m:
        return None
    return {
        "clip": m.group("clip"),
        "codec": m.group("codec"),
        "target_vmaf": float(m.group("target")),
    }


def find_reference(clip: str, inputs_dir: Path) -> Path:
    ref = inputs_dir / f"{clip}.mp4"
    if not ref.exists():
        raise FileNotFoundError(f"Reference not found: {ref}")
    return ref


def evaluate_file(provider_name, distorted, reference, parsed, measure_vmaf, event_log):
    clip = parsed["clip"]
    codec = parsed["codec"]
    target_vmaf = parsed["target_vmaf"]
    input_size = reference.stat().st_size
    file_size = distorted.stat().st_size
    bitrate_bps = get_actual_bitrate(str(distorted)) or 0
    bitrate_kbps = round(bitrate_bps / 1000, 1)

    event_log.log("eval_start",
                  provider=provider_name, clip=clip, codec=codec,
                  target_vmaf=target_vmaf, input_size_bytes=input_size)

    vmaf = measure_vmaf(reference, distorted)
    converged = vmaf >= target_vmaf

    vmaf_json_path = str(distorted.parent / f"{distorted.stem}_vmaf.json")

    event_log.log("search_complete",
                  provider=provider_name, clip=clip, codec=codec,
                  target_vmaf=target_vmaf, converged=converged,
                  quality_setting="provider_default",
                  vmaf_harmonic_mean=round(vmaf, 2),
                  output_file=str(distorted), vmaf_json=vmaf_json_path,
                  file_size_bytes=file_size, bitrate_kbps=bitrate_kbps,
                  input_size_bytes=input_size, steps=1)

    status = "CONVERGED" if converged else "NOT CONVERGED"
    print(f"  {provider_name} — {clip}: {status} VMAF {vmaf:.2f} | {bitrate_kbps} kbps | {file_size/(1024*1024):.1f} MB")


def main():
    parser = argparse.ArgumentParser(description="Evaluate pre-encoded files against references")
    parser.add_argument("--provider", required=True, help="Provider name (e.g. vidaio)")
    parser.add_argument("--dir", required=True, type=Path, help="Directory with encoded files")
    parser.add_argument("--vmaf-threads", type=int, default=None, help="VMAF threads per measurement")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml")
    parser.add_argument("--vertical", nargs="*", help="Filter to clips in these verticals (per catalog.yaml)")
    parser.add_argument("--id", nargs="*", help="Filter to these clip ids")
    args = parser.parse_args()

    config = load_config(args.config)
    inputs_dir = Path(config["inputs"]["dir"])

    files = sorted(args.dir.glob("*.mp4"))
    if not files:
        print(f"No .mp4 files in {args.dir}")
        return

    clip_vertical = {s["id"]: s["vertical"] for s in load_catalog()}
    catalog_clips = set(clip_vertical)

    allowed = catalog_clips
    if args.vertical or args.id:
        allowed = set()
        if args.vertical:
            verticals = set(args.vertical)
            allowed.update(cid for cid, v in clip_vertical.items() if v in verticals)
        if args.id:
            allowed.update(args.id)
        allowed &= catalog_clips

    parsed_files = []
    skipped_unlisted = 0
    for f in files:
        parsed = parse_filename(f)
        if parsed is None:
            print(f"  Skipping {f.name} — doesn't match <clip>_<codec>_vmaf<target>.mp4")
            continue
        if parsed["clip"] not in allowed:
            skipped_unlisted += 1
            continue
        parsed_files.append((f, parsed))

    if skipped_unlisted:
        print(f"  Skipped {skipped_unlisted} file(s) — clip not in catalog/filter")

    if not parsed_files:
        print("No files matched the naming convention")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = Path("data/results") / f"eval_{args.provider}_{timestamp}.jsonl"
    event_log = EventLog(log_path)

    measure_vmaf = make_measure_vmaf(vmaf_threads=args.vmaf_threads)

    event_log.log("eval_run_start",
                  provider=args.provider,
                  files=[f.name for f, _ in parsed_files])

    print(f"Provider:  {args.provider}")
    print(f"Files:     {len(parsed_files)}")
    print(f"Log:       {log_path}")
    print()

    for distorted, parsed in parsed_files:
        reference = find_reference(parsed["clip"], inputs_dir)
        evaluate_file(args.provider, distorted, reference, parsed, measure_vmaf, event_log)

    event_log.log("eval_run_complete", files=len(parsed_files))
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
