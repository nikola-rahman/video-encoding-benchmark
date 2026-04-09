#!/usr/bin/env python3
"""Render the benchmark report from CSV data and Jinja2 template."""

import argparse
import csv
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


REPORT_DIR = Path(__file__).parent
DEFAULT_CONFIG = REPORT_DIR / "report.yaml"
DEFAULT_TEMPLATE = REPORT_DIR / "template.md.j2"


# ── Interpolation helpers ────────────────────────────────────────


def interpolate_metric_at_vmaf(points: list[dict], target_vmaf: float, metric: str) -> float | None:
    """Linearly interpolate a metric (e.g. bitrate_kbps, file_size_bytes) at a target VMAF.

    Points must have 'vmaf_harmonic_mean' and the requested metric.
    Returns None if the target VMAF is outside the data range.
    """
    valid = [(p["vmaf_harmonic_mean"], p[metric]) for p in points
             if p.get("vmaf_harmonic_mean") is not None and p.get(metric) is not None]
    if len(valid) < 2:
        return None

    # Sort by VMAF ascending
    valid.sort(key=lambda x: x[0])
    vmafs = [v for v, _ in valid]
    metrics = [m for _, m in valid]

    if target_vmaf < vmafs[0] or target_vmaf > vmafs[-1]:
        return None

    # Find bracketing points
    for i in range(len(vmafs) - 1):
        if vmafs[i] <= target_vmaf <= vmafs[i + 1]:
            t = (target_vmaf - vmafs[i]) / (vmafs[i + 1] - vmafs[i]) if vmafs[i + 1] != vmafs[i] else 0
            return metrics[i] + t * (metrics[i + 1] - metrics[i])

    return None


def compute_bdrate(ref_points: list[dict], test_points: list[dict]) -> float | None:
    """Compute BD-Rate between two sets of RD points (simplified linear interpolation).

    Each point needs 'vmaf_harmonic_mean' and 'bitrate_kbps'.
    Returns percentage: positive means test uses more bitrate, negative means test saves bitrate.
    Returns None if insufficient overlap.
    """
    def to_pairs(pts):
        pairs = [(p["vmaf_harmonic_mean"], p["bitrate_kbps"]) for p in pts
                 if p.get("vmaf_harmonic_mean") is not None and p.get("bitrate_kbps") is not None]
        pairs.sort(key=lambda x: x[0])
        return pairs

    ref = to_pairs(ref_points)
    test = to_pairs(test_points)

    if len(ref) < 2 or len(test) < 2:
        return None

    # Find overlapping VMAF range
    vmaf_min = max(ref[0][0], test[0][0])
    vmaf_max = min(ref[-1][0], test[-1][0])

    if vmaf_max <= vmaf_min:
        return None

    # Sample at N points in the overlap range
    n_samples = 20
    step = (vmaf_max - vmaf_min) / n_samples

    def interp_bitrate(pairs, vmaf):
        for i in range(len(pairs) - 1):
            if pairs[i][0] <= vmaf <= pairs[i + 1][0]:
                t = (vmaf - pairs[i][0]) / (pairs[i + 1][0] - pairs[i][0]) if pairs[i + 1][0] != pairs[i][0] else 0
                return pairs[i][1] + t * (pairs[i + 1][1] - pairs[i][1])
        return None

    import math
    log_diff_sum = 0
    count = 0
    for i in range(n_samples + 1):
        vmaf = vmaf_min + i * step
        ref_br = interp_bitrate(ref, vmaf)
        test_br = interp_bitrate(test, vmaf)
        if ref_br and test_br and ref_br > 0 and test_br > 0:
            log_diff_sum += math.log(test_br) - math.log(ref_br)
            count += 1

    if count == 0:
        return None

    avg_log_diff = log_diff_sum / count
    bdrate_pct = (math.exp(avg_log_diff) - 1) * 100
    return round(bdrate_pct, 1)


# ── Data loading ─────────────────────────────────────────────────


def load_csv(path: Path) -> list[dict]:
    """Load a CSV file into a list of dicts, converting numeric fields."""
    if not path.exists():
        print(f"Warning: {path} not found, using empty data")
        return []
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for k, v in row.items():
            if v == "":
                row[k] = None
            else:
                try:
                    row[k] = int(v)
                except ValueError:
                    try:
                        row[k] = float(v)
                    except ValueError:
                        pass
    return rows


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ── Data processing ──────────────────────────────────────────────


def build_provider_name_map(config: dict) -> dict[str, str]:
    """Map provider ID → display name."""
    return {p["id"]: p["name"] for p in config["providers"]}


def compute_stats(results: list[dict], clips: list[dict], config: dict) -> dict:
    """Compute aggregate statistics from the results data."""
    provider_names = build_provider_name_map(config)
    unique_clips = set(r["clip"] for r in results) | set(c["clip"] for c in clips)
    unique_providers = set(r["provider"] for r in results)

    stats = {
        "n_clips": len(unique_clips),
        "n_providers": len(config["providers"]),
        # Placeholders — filled when enough data exists
        "max_size_spread_pct": 0,
        "best_provider_at_target": "TBD",
        "best_size_at_target_mb": 0,
        "second_size_at_target_mb": 0,
        "size_diff_pct": 0,
        "av1_h265_advantage_pct": 0,
        "av1_winner_note": "*To be computed from full results.*",
        "blackbox_position_note": "*To be computed from full results.*",
        "ease_efficiency_note": "*To be computed from full results.*",
        "easy_clip": None,
        "hard_clip": None,
    }

    if not results:
        return stats

    # File size at VMAF target, per provider (simple: closest point above threshold)
    vmaf_target = config.get("vmaf_transparent", 93)
    provider_sizes = defaultdict(list)
    for r in results:
        if r.get("vmaf_harmonic_mean") and r["vmaf_harmonic_mean"] >= vmaf_target:
            provider_sizes[r["provider"]].append(r["file_size_bytes"])

    if provider_sizes:
        avg_sizes = {
            p: sum(sizes) / len(sizes) for p, sizes in provider_sizes.items()
        }
        ranked = sorted(avg_sizes.items(), key=lambda x: x[1])
        if len(ranked) >= 2:
            best_id, best_size = ranked[0]
            second_id, second_size = ranked[1]
            worst_size = ranked[-1][1]
            stats["best_provider_at_target"] = provider_names.get(best_id, best_id)
            stats["best_size_at_target_mb"] = best_size / (1024 * 1024)
            stats["second_size_at_target_mb"] = second_size / (1024 * 1024)
            stats["size_diff_pct"] = ((second_size - best_size) / best_size) * 100
            stats["max_size_spread_pct"] = ((worst_size - best_size) / best_size) * 100
        elif len(ranked) == 1:
            best_id, best_size = ranked[0]
            stats["best_provider_at_target"] = provider_names.get(best_id, best_id)
            stats["best_size_at_target_mb"] = best_size / (1024 * 1024)

    # AV1 vs H.265 advantage
    codec_sizes = defaultdict(list)
    for r in results:
        if r.get("file_size_bytes"):
            codec_sizes[r["codec"]].append(r["file_size_bytes"])
    if codec_sizes.get("av1") and codec_sizes.get("h265"):
        avg_av1 = sum(codec_sizes["av1"]) / len(codec_sizes["av1"])
        avg_h265 = sum(codec_sizes["h265"]) / len(codec_sizes["h265"])
        if avg_h265 > 0:
            stats["av1_h265_advantage_pct"] = ((avg_h265 - avg_av1) / avg_h265) * 100

    # Easy/hard clips by TI (temporal information)
    if clips:
        by_ti = sorted([c for c in clips if c.get("ti")], key=lambda c: c["ti"])
        if by_ti:
            stats["easy_clip"] = by_ti[0]["clip"]
            stats["hard_clip"] = by_ti[-1]["clip"]

    return stats


def build_codec_summary(results: list[dict], config: dict) -> dict:
    """Build per-codec provider summary tables with computed metrics."""
    provider_names = build_provider_name_map(config)
    vmaf_target = config.get("vmaf_transparent", 93)
    summary = defaultdict(list)

    for codec in config.get("codecs", []):
        codec_results = [r for r in results if r.get("codec") == codec]
        by_provider = defaultdict(list)
        for r in codec_results:
            by_provider[r["provider"]].append(r)

        # Build per-provider data
        provider_entries = []
        for pid, rows in by_provider.items():
            vmaf_vals = [r["vmaf_harmonic_mean"] for r in rows if r.get("vmaf_harmonic_mean")]
            cr_vals = [r["compression_ratio"] for r in rows if r.get("compression_ratio")]
            br_at_target = interpolate_metric_at_vmaf(rows, vmaf_target, "bitrate_kbps")
            fs_at_target = interpolate_metric_at_vmaf(rows, vmaf_target, "file_size_bytes")
            provider_entries.append({
                "pid": pid,
                "name": provider_names.get(pid, pid),
                "vmaf_avg": round(sum(vmaf_vals) / len(vmaf_vals), 1) if vmaf_vals else None,
                "br_at_target": br_at_target,
                "fs_at_target": fs_at_target,
                "points": rows,
                "compression_ratio": (
                    "%.1f" % (sum(cr_vals) / len(cr_vals)) if cr_vals else None
                ),
            })

        # Find best provider for BD-Rate reference
        with_fs = [e for e in provider_entries if e["fs_at_target"] is not None]
        ref_entry = min(with_fs, key=lambda e: e["fs_at_target"]) if with_fs else None

        for e in provider_entries:
            bdrate = None
            if ref_entry and e["points"] is not ref_entry["points"]:
                bdrate = compute_bdrate(ref_entry["points"], e["points"])

            summary[codec].append({
                "name": e["name"],
                "vmaf_avg": e["vmaf_avg"],
                "bitrate_at_target": f"{e['br_at_target']:.0f} kbps" if e["br_at_target"] else "—",
                "filesize_at_target": f"{e['fs_at_target'] / (1024*1024):.1f} MB" if e["fs_at_target"] else "—",
                "bdrate": f"+{bdrate}%" if bdrate and bdrate > 0 else f"{bdrate}%" if bdrate else "ref",
                "compression_ratio": e["compression_ratio"],
            })

    return dict(summary)


def build_vertical_data(results: list[dict], clips: list[dict]) -> dict:
    """Group results by codec and vertical for per-vertical tables."""
    clip_vertical = {c["clip"]: c["vertical"] for c in clips}
    data = defaultdict(lambda: defaultdict(list))

    for r in results:
        vertical = clip_vertical.get(r["clip"])
        if not vertical:
            continue
        codec = r.get("codec", "unknown")
        data[codec][vertical].append({
            "clip": r["clip"],
            "provider": r["provider"],
            "bitrate_kbps": r.get("bitrate_kbps", 0),
            "file_size_mb": (r.get("file_size_bytes", 0) or 0) / (1024 * 1024),
            "vmaf_harmonic_mean": r.get("vmaf_harmonic_mean", 0),
            "vmaf_min": r.get("vmaf_min", 0),
            "vmaf_p01": r.get("vmaf_p01", 0),
            "compression_ratio": r.get("compression_ratio", 0),
        })

    return dict(data)


def build_speed_summary(encoding_times: list[dict], config: dict) -> list[dict]:
    """Build encoding speed summary per provider."""
    provider_names = build_provider_name_map(config)
    by_provider = defaultdict(list)
    for row in encoding_times:
        by_provider[row["provider"]].append(row)

    summary = []
    for pid, rows in by_provider.items():
        times = [r["encode_time_s"] for r in rows if r.get("encode_time_s")]
        durations = [r["clip_duration_s"] for r in rows if r.get("clip_duration_s")]
        if not times:
            continue
        avg_time = sum(times) / len(times)
        avg_duration = sum(durations) / len(durations) if durations else 60
        summary.append({
            "name": provider_names.get(pid, pid),
            "avg_time": avg_time,
            "avg_realtime": avg_time / avg_duration if avg_duration else 0,
            "min_time": min(times),
            "max_time": max(times),
        })

    return summary


def build_pricing_data(pricing_rows: list[dict], config: dict) -> list[dict]:
    """Build pricing table data."""
    provider_names = build_provider_name_map(config)
    return [
        {
            "name": provider_names.get(r["provider"], r["provider"]),
            "pricing_model": r.get("pricing_model", ""),
            "cost_per_min_1080p": r.get("cost_per_min_1080p", "TBD"),
            "cost_per_min_4k": r.get("cost_per_min_4k", "TBD"),
            "notes": r.get("notes", ""),
        }
        for r in pricing_rows
    ]


def build_storage_projection(results: list[dict], config: dict) -> list[dict]:
    """Build storage cost projection table."""
    provider_names = build_provider_name_map(config)
    vmaf_target = config.get("vmaf_transparent", 93)
    proj = config.get("projection", {})
    num_videos = proj.get("num_videos", 1_000_000)
    cost_per_gb_month = config.get("storage_cost_per_gb_month", 0.023)

    by_provider = defaultdict(list)
    for r in results:
        by_provider[r["provider"]].append(r)

    rows = []
    for pid, data in by_provider.items():
        fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        if fs is None:
            # Use average file size of points above target as fallback
            above = [r["file_size_bytes"] for r in data
                     if r.get("vmaf_harmonic_mean") and r["vmaf_harmonic_mean"] >= vmaf_target and r.get("file_size_bytes")]
            fs = sum(above) / len(above) if above else None

        if fs is None:
            continue

        total_bytes = fs * num_videos
        total_tb = total_bytes / (1024 ** 4)
        total_gb = total_bytes / (1024 ** 3)
        annual_cost = total_gb * cost_per_gb_month * 12

        rows.append({
            "name": provider_names.get(pid, pid),
            "total_tb": total_tb,
            "annual_cost": annual_cost,
        })

    return rows


def build_tco(results: list[dict], pricing_rows: list[dict], config: dict) -> list[dict]:
    """Build total cost of ownership table (encoding + storage)."""
    provider_names = build_provider_name_map(config)
    vmaf_target = config.get("vmaf_transparent", 93)
    proj = config.get("projection", {})
    num_videos = proj.get("num_videos", 1_000_000)
    duration_s = proj.get("duration_s", 60)
    cost_per_gb_month = config.get("storage_cost_per_gb_month", 0.023)

    # Build pricing lookup
    pricing_map = {}
    for r in pricing_rows:
        cost = r.get("cost_per_min_1080p")
        if cost and cost != "TBD":
            try:
                pricing_map[r["provider"]] = float(cost)
            except (ValueError, TypeError):
                pass

    by_provider = defaultdict(list)
    for r in results:
        by_provider[r["provider"]].append(r)

    rows = []
    for pid, data in by_provider.items():
        fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        if fs is None:
            above = [r["file_size_bytes"] for r in data
                     if r.get("vmaf_harmonic_mean") and r["vmaf_harmonic_mean"] >= vmaf_target and r.get("file_size_bytes")]
            fs = sum(above) / len(above) if above else None

        if fs is None:
            continue

        total_storage_gb = (fs * num_videos) / (1024 ** 3)
        storage_cost = total_storage_gb * cost_per_gb_month * 12

        total_minutes = num_videos * duration_s / 60
        cost_per_min = pricing_map.get(pid, 0)
        encoding_cost = total_minutes * cost_per_min

        rows.append({
            "name": provider_names.get(pid, pid),
            "encoding_cost": encoding_cost,
            "storage_cost": storage_cost,
            "total_cost": encoding_cost + storage_cost,
            "savings": "",  # filled below
        })

    if rows:
        max_cost = max(r["total_cost"] for r in rows)
        for r in rows:
            saving = max_cost - r["total_cost"]
            r["savings"] = f"-${saving:,.0f}" if saving > 0 else "—"

    return rows


def build_cost_per_quality(results: list[dict], pricing_rows: list[dict], config: dict) -> list[dict]:
    """Build cost per VMAF point and cost per GB saved."""
    provider_names = build_provider_name_map(config)
    vmaf_target = config.get("vmaf_transparent", 93)
    proj = config.get("projection", {})
    num_videos = proj.get("num_videos", 1_000_000)
    duration_s = proj.get("duration_s", 60)

    pricing_map = {}
    for r in pricing_rows:
        cost = r.get("cost_per_min_1080p")
        if cost and cost != "TBD":
            try:
                pricing_map[r["provider"]] = float(cost)
            except (ValueError, TypeError):
                pass

    by_provider = defaultdict(list)
    for r in results:
        by_provider[r["provider"]].append(r)

    # Find baseline (worst provider by file size at target)
    provider_fs = {}
    for pid, data in by_provider.items():
        fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        if fs:
            provider_fs[pid] = fs

    if not provider_fs:
        return []

    baseline_fs = max(provider_fs.values())
    total_minutes = num_videos * duration_s / 60

    rows = []
    for pid, data in by_provider.items():
        vmaf_vals = [r["vmaf_harmonic_mean"] for r in data if r.get("vmaf_harmonic_mean")]
        avg_vmaf = sum(vmaf_vals) / len(vmaf_vals) if vmaf_vals else 0
        cost_per_min = pricing_map.get(pid, 0)
        total_encoding_cost = total_minutes * cost_per_min

        fs = provider_fs.get(pid)
        if fs is None or avg_vmaf == 0:
            continue

        cost_per_vmaf = total_encoding_cost / avg_vmaf if avg_vmaf > 0 else 0

        gb_saved = (baseline_fs - fs) * num_videos / (1024 ** 3)
        cost_per_gb = total_encoding_cost / gb_saved if gb_saved > 0 else 0

        rows.append({
            "name": provider_names.get(pid, pid),
            "cost_per_vmaf_point": f"${cost_per_vmaf:,.0f}" if cost_per_vmaf else "—",
            "cost_per_gb_saved": f"${cost_per_gb:,.2f}" if gb_saved > 0 else "— (baseline)",
        })

    return rows


def build_rec_matrix(results: list[dict], pricing_rows: list[dict], clips: list[dict], config: dict) -> dict:
    """Build recommendation matrix: best provider per use case × dimension."""
    provider_names = build_provider_name_map(config)
    vmaf_target = config.get("vmaf_transparent", 93)
    clip_vertical = {c["clip"]: c["vertical"] for c in clips}

    pricing_map = {}
    for r in pricing_rows:
        cost = r.get("cost_per_min_1080p")
        if cost and cost != "TBD":
            try:
                pricing_map[r["provider"]] = float(cost)
            except (ValueError, TypeError):
                pass

    blackbox_ids = {p["id"] for p in config["providers"] if p.get("blackbox")}

    matrix = {}
    for v in config.get("verticals", []):
        vid = v["id"]
        vertical_results = [r for r in results if clip_vertical.get(r["clip"]) == vid]

        by_provider = defaultdict(list)
        for r in vertical_results:
            by_provider[r["provider"]].append(r)

        # Best for quality: smallest file at VMAF target
        provider_fs = {}
        for pid, data in by_provider.items():
            fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
            if fs:
                provider_fs[pid] = fs
        best_quality = min(provider_fs, key=provider_fs.get) if provider_fs else None

        # Best for simplicity: black-box or fewest config steps
        simplicity_order = ["cloudflare", "mux", "vidaio", "zencoder", "mediaconvert", "bitmovin"]
        best_simplicity = None
        for pid in simplicity_order:
            if pid in by_provider:
                best_simplicity = pid
                break

        # Best for cost: lowest encoding cost per minute
        provider_costs = {pid: pricing_map[pid] for pid in by_provider if pid in pricing_map}
        best_cost = min(provider_costs, key=provider_costs.get) if provider_costs else None

        matrix[vid] = {
            "quality": provider_names.get(best_quality, "TBD") if best_quality else "TBD",
            "simplicity": provider_names.get(best_simplicity, "TBD") if best_simplicity else "TBD",
            "cost": provider_names.get(best_cost, "TBD") if best_cost else "TBD",
        }

    return matrix


def build_headline_ranking(results: list[dict], config: dict) -> list[dict]:
    """Build the headline findings table with computed BD-Rate, file size at target, and rank."""
    provider_names = build_provider_name_map(config)
    vmaf_target = config.get("vmaf_transparent", 93)
    by_provider = defaultdict(list)
    for r in results:
        by_provider[r["provider"]].append(r)

    # Compute file size at VMAF target and avg VMAF for each provider
    provider_data = []
    for pid, data in by_provider.items():
        vmaf_vals = [r["vmaf_harmonic_mean"] for r in data if r.get("vmaf_harmonic_mean")]
        fs_at_target = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        provider_data.append({
            "pid": pid,
            "name": provider_names.get(pid, pid),
            "vmaf_avg": sum(vmaf_vals) / len(vmaf_vals) if vmaf_vals else None,
            "points": data,
            "filesize_at_target_bytes": fs_at_target,
        })

    # Find the best provider (smallest file at target VMAF) as BD-Rate reference
    providers_with_fs = [p for p in provider_data if p["filesize_at_target_bytes"] is not None]
    if providers_with_fs:
        best = min(providers_with_fs, key=lambda p: p["filesize_at_target_bytes"])
        ref_points = best["points"]
    else:
        ref_points = None

    # Build rows with BD-Rate
    rows = []
    for p in provider_data:
        bdrate = None
        if ref_points and p["points"] is not ref_points:
            bdrate = compute_bdrate(ref_points, p["points"])

        fs = p["filesize_at_target_bytes"]
        rows.append({
            "name": p["name"],
            "vmaf_avg": p["vmaf_avg"],
            "bdrate": f"+{bdrate}%" if bdrate and bdrate > 0 else f"{bdrate}%" if bdrate else "ref",
            "filesize_at_target": f"{fs / (1024*1024):.1f} MB" if fs else "—",
            "filesize_at_target_bytes": fs,
            "rank": 0,
        })

    # Compute rank by file size at target (smallest = rank 1)
    ranked = sorted(
        [r for r in rows if r["filesize_at_target_bytes"] is not None],
        key=lambda r: r["filesize_at_target_bytes"],
    )
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    for r in rows:
        if r["rank"] == 0:
            r["rank"] = "—"

    # Add providers with no results yet
    existing = {r["name"] for r in rows}
    for p in config["providers"]:
        if p["name"] not in existing:
            rows.append({
                "name": p["name"],
                "vmaf_avg": None,
                "bdrate": "—",
                "filesize_at_target": "—",
                "rank": "—",
            })

    return rows


def build_providers_context(config: dict) -> list[dict]:
    """Build provider metadata for the template."""
    provider_meta = {
        "bitmovin": {
            "rate_control": "CRF",
            "quality_param": "crf (0-51 / 0-63)",
            "codec_support": "AV1, H.265",
            "sweep_points": "8-12",
            "steps_to_optimal": "Configure CRF, preset, Per-Title params, codec config",
            "quality_control": "Manual CRF tuning or Per-Title",
            "codec_selection": "Full control",
            "expertise": "High",
            "optimization_process": "Sweep CRF values, encode each, measure VMAF, pick the CRF that hits target",
            "iteration_required": "Yes — multiple encodes per clip",
            "sdk": "bitmovin-api-sdk (Python)",
            "auth_setup": "API key",
            "job_complexity": "Complex (input → encoding → stream → codec config → muxing → start)",
            "result_retrieval": "Poll + S3 download",
            "docs_quality": "Extensive",
        },
        "cloudflare": {
            "rate_control": "Automatic",
            "quality_param": "None",
            "codec_support": "H.264 only",
            "sweep_points": "1",
            "steps_to_optimal": "Upload video",
            "quality_control": "Fully automatic",
            "codec_selection": "No control (H.264 only)",
            "expertise": "None",
            "sdk": "cloudflare (Python)",
            "auth_setup": "API token",
            "job_complexity": "Simple (POST with URL)",
            "result_retrieval": "Webhook or poll",
            "docs_quality": "Good",
        },
        "mediaconvert": {
            "rate_control": "QVBR",
            "quality_param": "QvbrQualityLevel (1-10)",
            "codec_support": "AV1, H.265",
            "sweep_points": "8-10",
            "steps_to_optimal": "Configure QVBR level (1-10), fine-tune, codec settings, IAM role",
            "quality_control": "Manual QVBR tuning",
            "codec_selection": "Full control",
            "expertise": "High",
            "optimization_process": "Sweep QVBR levels 1-10, encode each, measure VMAF, pick level closest to target",
            "iteration_required": "Yes — up to 10 encodes per clip",
            "sdk": "boto3",
            "auth_setup": "IAM role + endpoint discovery",
            "job_complexity": "Moderate (job JSON with nested settings)",
            "result_retrieval": "Poll + S3 download",
            "docs_quality": "Extensive",
        },
        "mux": {
            "rate_control": "Automatic",
            "quality_param": "None",
            "codec_support": "Automatic",
            "sweep_points": "1",
            "steps_to_optimal": "Upload video",
            "quality_control": "Fully automatic",
            "codec_selection": "No control",
            "expertise": "None",
            "optimization_process": "Upload video; no controls available",
            "iteration_required": "No — single output, no tuning possible",
            "sdk": "mux-python",
            "auth_setup": "Token ID + secret",
            "job_complexity": "Simple (POST asset with URL)",
            "result_retrieval": "Webhook or poll",
            "docs_quality": "Good",
        },
        "vidaio": {
            "rate_control": "Quality-optimized",
            "quality_param": "Preset (basic/medium/hyper)",
            "codec_support": "AV1, H.265",
            "sweep_points": "3",
            "steps_to_optimal": "Select preset (basic/medium/hyper)",
            "quality_control": "Automatic",
            "codec_selection": "Choose AV1 or H.265",
            "expertise": "Low",
            "optimization_process": "Select quality preset; encoder optimizes automatically",
            "iteration_required": "No — preset determines quality/size tradeoff",
            "sdk": "TBD",
            "auth_setup": "TBD",
            "job_complexity": "TBD",
            "result_retrieval": "TBD",
            "docs_quality": "TBD",
        },
        "zencoder": {
            "rate_control": "CRF / Quality",
            "quality_param": "crf (0-51) or quality (1-5)",
            "codec_support": "AV1, H.265",
            "sweep_points": "5-8",
            "steps_to_optimal": "Set quality (1-5) or CRF, speed, codec",
            "quality_control": "Manual tuning",
            "codec_selection": "Full control",
            "expertise": "Medium",
            "optimization_process": "Sweep quality 1-5 or CRF values, encode, measure VMAF, pick best",
            "iteration_required": "Yes — 5+ encodes per clip",
            "sdk": "zencoder (Python)",
            "auth_setup": "API key",
            "job_complexity": "Simple (POST with input + outputs)",
            "result_retrieval": "Poll + download URL",
            "docs_quality": "Adequate",
        },
    }

    providers = []
    for p in config["providers"]:
        meta = provider_meta.get(p["id"], {})
        providers.append({
            "id": p["id"],
            "name": p["name"],
            "blackbox": p.get("blackbox", False),
            **meta,
        })

    return providers


# ── Rendering ────────────────────────────────────────────────────


def build_context(config: dict, report_dir: Path) -> dict:
    """Build the full Jinja2 template context from config and CSV data."""
    # Paths in config are relative to the config file's directory
    results = load_csv(report_dir / config["data"]["results"])
    clips = load_csv(report_dir / config["data"]["clip_metadata"])
    encoding_times = load_csv(report_dir / config["data"]["encoding_times"])
    pricing_rows = load_csv(report_dir / config["data"]["pricing"])

    stats = compute_stats(results, clips, config)
    providers = build_providers_context(config)

    # For headline ranking, only use results from benchmark codecs (av1, h265)
    # to avoid cross-codec comparisons with black-box H.264 providers
    benchmark_codecs = set(config.get("codecs", []))
    comparable_results = [r for r in results if r.get("codec") in benchmark_codecs]

    proj = config.get("projection", {})
    num_videos = proj.get("num_videos", 1_000_000)
    duration_s = proj.get("duration_s", 60)
    resolution = proj.get("resolution", "1080p")
    tco_scenario = f"{num_videos:,} videos × {duration_s}s × {resolution}"

    config["date"] = datetime.now().strftime("%Y-%m-%d")

    return {
        "config": config,
        "vmaf_transparent": config.get("vmaf_transparent", 93),
        "vmaf_indistinguishable": config.get("vmaf_indistinguishable", 95),
        "storage_cost_per_gb_month": config.get("storage_cost_per_gb_month", 0.023),
        "projection": config.get("projection", {}),
        "stats": stats,
        "clips": clips,
        "codecs": config.get("codecs", []),
        "verticals": config.get("verticals", []),
        "providers": providers,
        "all_results": results,
        "headline_ranking": build_headline_ranking(comparable_results, config),
        "codec_summary": build_codec_summary(results, config),
        "vertical_data": build_vertical_data(results, clips),
        "speed_summary": build_speed_summary(encoding_times, config),
        "pricing": build_pricing_data(pricing_rows, config),
        "storage_projection": build_storage_projection(comparable_results, config),
        "tco_scenario": tco_scenario,
        "tco": build_tco(comparable_results, pricing_rows, config),
        "cost_per_quality": build_cost_per_quality(comparable_results, pricing_rows, config),
        "rec_matrix": build_rec_matrix(comparable_results, pricing_rows, clips, config),
        # Placeholders for sections that need manual input
        "narratives": defaultdict(lambda: defaultdict(str)),
        "recommendations": {},
        "conclusions": {},
        "generation_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def render(config_path: Path, template_path: Path, output_dir: Path):
    """Render the report template with data."""
    config = load_config(config_path)
    report_dir = config_path.parent

    env = Environment(
        loader=FileSystemLoader(str(report_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)

    context = build_context(config, report_dir)

    rendered = template.render(**context)

    # Versioned output
    version = config.get("version", "dev")
    date = config.get("date", datetime.now().strftime("%Y-%m-%d"))
    version_dir = output_dir / f"v{version}_{date}"
    version_dir.mkdir(parents=True, exist_ok=True)

    md_path = version_dir / "report.md"
    md_path.write_text(rendered)
    print(f"Rendered: {md_path}")

    # Also write a "latest" symlink/copy
    latest_path = output_dir / "latest"
    if latest_path.is_symlink() or latest_path.exists():
        if latest_path.is_symlink():
            latest_path.unlink()
        elif latest_path.is_dir():
            shutil.rmtree(latest_path)
    latest_path.symlink_to(version_dir.name)
    print(f"Latest:   {latest_path} -> {version_dir.name}")

    # Copy figures if they exist
    figures_src = report_dir / "figures"
    if figures_src.exists():
        figures_dst = version_dir / "figures"
        if figures_dst.exists():
            shutil.rmtree(figures_dst)
        shutil.copytree(figures_src, figures_dst)
        print(f"Figures:  {figures_dst}")

    return md_path


# ── CLI ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark report from CSV data")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="report.yaml path")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="Jinja2 template")
    parser.add_argument("--output", type=Path, default=REPORT_DIR / "output", help="Output directory")
    parser.add_argument("--skip-charts", action="store_true", help="Skip chart generation")
    args = parser.parse_args()

    if not args.skip_charts:
        from report.charts import generate_all
        generate_all(args.config)

    render(args.config, args.template, args.output)


if __name__ == "__main__":
    main()
