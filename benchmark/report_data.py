#!/usr/bin/env python3
"""Generate report CSVs from JSONL run logs.

Reads all .jsonl files in the results directory. For duplicate
(provider, clip, codec, target_vmaf) results, uses the latest by timestamp.

Usage:
    python -m benchmark.report_data data/results/ report/data/
"""

import argparse
import csv
import json
from pathlib import Path


def load_events(results_dir: Path) -> list[dict]:
    events = []
    for f in sorted(results_dir.glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    return events


def extract_results(events: list[dict]) -> list[dict]:
    """Extract search_complete events, deduplicate by latest timestamp."""
    completes = [e for e in events if e["event"] == "search_complete"]

    # Deduplicate: keep latest by (provider, clip, codec, target_vmaf)
    best = {}
    for e in completes:
        key = (e["provider"], e["clip"], e["codec"], e["target_vmaf"])
        if key not in best or e["timestamp"] > best[key]["timestamp"]:
            best[key] = e

    return list(best.values())


def extract_probes(events: list[dict]) -> list[dict]:
    """Extract all search_probe events."""
    return [e for e in events if e["event"] == "search_probe"]


RESULTS_COLUMNS = [
    "provider", "clip", "codec", "target_vmaf", "quality_setting",
    "vmaf_harmonic_mean", "file_size_bytes", "bitrate_kbps",
    "input_size_bytes", "output_file", "vmaf_json",
    "converged", "steps", "timestamp",
]


def write_results_csv(results: list[dict], output_path: Path):
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULTS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def run(results_dir: Path, output_dir: Path):
    events = load_events(results_dir)
    if not events:
        print(f"No events found in {results_dir}")
        return

    results = extract_results(events)
    probes = extract_probes(events)

    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "results.csv"
    write_results_csv(results, results_path)
    print(f"Results: {len(results)} entries -> {results_path}")

    probes_path = output_dir / "probes.csv"
    probe_columns = ["provider", "clip", "codec", "target_vmaf", "quality_setting",
                     "vmaf_harmonic_mean", "encoding_name", "step", "timestamp"]
    with open(probes_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=probe_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(probes)
    print(f"Probes: {len(probes)} entries -> {probes_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate report CSVs from JSONL run logs")
    parser.add_argument("results_dir", type=Path, help="Directory with .jsonl run logs")
    parser.add_argument("output_dir", type=Path, help="Output directory for report CSVs")
    args = parser.parse_args()
    run(args.results_dir, args.output_dir)
