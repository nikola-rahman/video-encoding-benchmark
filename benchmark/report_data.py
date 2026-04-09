#!/usr/bin/env python3
"""Generate report CSVs from JSONL run logs.

Reads all .jsonl files in the results directory. For duplicate
(provider, clip, codec, target_vmaf) results, uses the latest by timestamp.
Enriches with vertical from catalog and VMAF detail metrics from JSON files.

Usage:
    python -m benchmark.report_data data/results/ report/data/
"""

import argparse
import csv
import json
from pathlib import Path

from benchmark.samples.catalog import load_catalog


def load_events(results_dir: Path) -> list[dict]:
    events = []
    for f in sorted(results_dir.glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    return events


def build_clip_vertical_map() -> dict[str, str]:
    catalog = load_catalog()
    return {s["id"]: s["vertical"] for s in catalog}


def extract_vmaf_detail(vmaf_json_path: str) -> dict:
    """Extract min, p01, p05 from a VMAF JSON file."""
    path = Path(vmaf_json_path)
    if not path.exists():
        return {}

    with open(path) as f:
        data = json.load(f)

    pooled = data.get("pooled_metrics", {}).get("vmaf", {})
    result = {
        "vmaf_min": pooled.get("min"),
        "vmaf_harmonic_mean": pooled.get("harmonic_mean"),
    }

    frames = data.get("frames", [])
    if frames:
        scores = sorted(f["metrics"]["vmaf"] for f in frames if "vmaf" in f.get("metrics", {}))
        n = len(scores)
        if n > 0:
            result["vmaf_p01"] = scores[max(0, int(n * 0.01))]
            result["vmaf_p05"] = scores[max(0, int(n * 0.05))]

    return result


def extract_results(events: list[dict]) -> list[dict]:
    completes = [e for e in events if e["event"] == "search_complete"]

    best = {}
    for e in completes:
        key = (e["provider"], e["clip"], e["codec"], e["target_vmaf"])
        if key not in best or e["timestamp"] > best[key]["timestamp"]:
            best[key] = e

    return list(best.values())


def enrich_result(result: dict, clip_vertical: dict) -> dict:
    clip = result["clip"]
    vertical = clip_vertical.get(clip, "")

    input_size = result.get("input_size_bytes", 0)
    file_size = result.get("file_size_bytes", 0)
    compression_ratio = round(input_size / file_size, 2) if file_size > 0 else 0

    vmaf_detail = extract_vmaf_detail(result.get("vmaf_json", ""))

    return {
        "clip": clip,
        "vertical": vertical,
        "provider": result["provider"],
        "codec": result["codec"],
        "quality_setting": result["quality_setting"],
        "bitrate_kbps": result["bitrate_kbps"],
        "file_size_bytes": file_size,
        "vmaf_harmonic_mean": vmaf_detail.get("vmaf_harmonic_mean", result.get("vmaf_harmonic_mean")),
        "vmaf_min": vmaf_detail.get("vmaf_min", ""),
        "vmaf_p01": vmaf_detail.get("vmaf_p01", ""),
        "vmaf_p05": vmaf_detail.get("vmaf_p05", ""),
        "compression_ratio": compression_ratio,
    }


RESULTS_COLUMNS = [
    "clip", "vertical", "provider", "codec", "quality_setting",
    "bitrate_kbps", "file_size_bytes",
    "vmaf_harmonic_mean", "vmaf_min", "vmaf_p01", "vmaf_p05",
    "compression_ratio",
]


def run(results_dir: Path, output_dir: Path):
    events = load_events(results_dir)
    if not events:
        print(f"No events found in {results_dir}")
        return

    results = extract_results(events)
    clip_vertical = build_clip_vertical_map()

    enriched = [enrich_result(r, clip_vertical) for r in results if r.get("converged")]

    if output_dir.exists():
        for f in output_dir.glob("*.csv"):
            f.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "results.csv"
    with open(results_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULTS_COLUMNS)
        writer.writeheader()
        writer.writerows(enriched)

    print(f"Results: {len(enriched)} entries -> {results_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate report CSVs from JSONL run logs")
    parser.add_argument("results_dir", type=Path, help="Directory with .jsonl run logs")
    parser.add_argument("output_dir", type=Path, help="Output directory for report CSVs")
    args = parser.parse_args()
    run(args.results_dir, args.output_dir)
