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
    """Compute BD-Rate between two sets of RD points using PCHIP interpolation.

    Follows the Bjontegaard (2001) method: integrate log-bitrate over the
    overlapping VMAF range using piecewise cubic Hermite interpolation.

    Each point needs 'vmaf_harmonic_mean' and 'bitrate_kbps'.
    Returns percentage: positive means test uses more bitrate, negative means test saves bitrate.
    Returns None if insufficient overlap.
    """
    from scipy.interpolate import PchipInterpolator

    def to_pairs(pts):
        pairs = [(p["vmaf_harmonic_mean"], p["bitrate_kbps"]) for p in pts
                 if p.get("vmaf_harmonic_mean") is not None and p.get("bitrate_kbps") is not None]
        pairs.sort(key=lambda x: x[0])
        # PCHIP requires strictly increasing x - deduplicate by averaging bitrates at same VMAF
        deduped = []
        for vmaf, br in pairs:
            if deduped and abs(vmaf - deduped[-1][0]) < 0.01:
                deduped[-1] = (deduped[-1][0], (deduped[-1][1] + br) / 2)
            else:
                deduped.append((vmaf, br))
        return deduped

    ref = to_pairs(ref_points)
    test = to_pairs(test_points)

    if len(ref) < 2 or len(test) < 2:
        return None

    import math
    import numpy as np

    ref_vmaf = np.array([p[0] for p in ref])
    ref_logbr = np.array([math.log(p[1]) for p in ref])
    test_vmaf = np.array([p[0] for p in test])
    test_logbr = np.array([math.log(p[1]) for p in test])

    # Overlapping VMAF range
    vmaf_lo = max(ref_vmaf[0], test_vmaf[0])
    vmaf_hi = min(ref_vmaf[-1], test_vmaf[-1])

    if vmaf_hi <= vmaf_lo:
        return None

    ref_interp = PchipInterpolator(ref_vmaf, ref_logbr)
    test_interp = PchipInterpolator(test_vmaf, test_logbr)

    # Integrate log-bitrate difference over the overlapping range
    ref_integral = float(ref_interp.integrate(vmaf_lo, vmaf_hi))
    test_integral = float(test_interp.integrate(vmaf_lo, vmaf_hi))

    avg_log_diff = (test_integral - ref_integral) / (vmaf_hi - vmaf_lo)
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
            elif v in ("True", "False"):
                row[k] = (v == "True")
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

    import statistics as _stats

    stats = {
        "n_clips": len(unique_clips),
        "n_providers": len(config["providers"]),
        "easy_clip": None,
        "hard_clip": None,
    }

    if not results:
        return stats

    vmaf_target = config.get("vmaf_transparent", 93)

    # Per-codec headline numbers on the apples-to-apples common subset:
    # clips × VMAF target combos that ALL providers tested for that codec.
    for codec in ("h265", "av1"):
        codec_rows = [r for r in results if r.get("codec") == codec]
        combos_by_provider = defaultdict(set)
        for r in codec_rows:
            combos_by_provider[r["provider"]].add((r["clip"], r["target_vmaf"]))
        if not combos_by_provider:
            continue
        common = set.intersection(*combos_by_provider.values())
        common_at_target = {(c, t) for (c, t) in common if t == vmaf_target}
        if not common_at_target:
            continue

        sizes = defaultdict(list)
        for r in codec_rows:
            if (r["clip"], r["target_vmaf"]) in common_at_target and r.get("file_size_bytes"):
                sizes[r["provider"]].append(r["file_size_bytes"])
        means = {p: sum(s) / len(s) for p, s in sizes.items() if s}
        if len(means) < 2:
            continue
        ranked = sorted(means.items(), key=lambda x: x[1])
        best_id, best_bytes = ranked[0]
        second_id, second_bytes = ranked[1]
        worst_id, worst_bytes = ranked[-1]
        stats[f"{codec}_n_combos"] = len(common_at_target)
        stats[f"{codec}_best_provider"] = provider_names.get(best_id, best_id)
        stats[f"{codec}_best_mb"] = best_bytes / (1024 * 1024)
        stats[f"{codec}_second_provider"] = provider_names.get(second_id, second_id)
        stats[f"{codec}_second_mb"] = second_bytes / (1024 * 1024)
        stats[f"{codec}_worst_provider"] = provider_names.get(worst_id, worst_id)
        stats[f"{codec}_worst_mb"] = worst_bytes / (1024 * 1024)
        stats[f"{codec}_second_vs_best_pct"] = (second_bytes - best_bytes) / best_bytes * 100
        stats[f"{codec}_worst_vs_best_pct"] = (worst_bytes - best_bytes) / best_bytes * 100

    # AV1 vs H.265 advantage, per-clip ratio within provider, geo-mean
    # (multiplicative metric → geometric mean is the right aggregator).
    by_pct = defaultdict(dict)
    for r in results:
        by_pct[(r["provider"], r["clip"], r["target_vmaf"])][r["codec"]] = r
    by_provider_ratios = defaultdict(list)
    all_ratios = []
    for k, v in by_pct.items():
        a = v.get("av1", {}).get("file_size_bytes")
        h = v.get("h265", {}).get("file_size_bytes")
        if a and h:
            ratio = a / h
            by_provider_ratios[k[0]].append(ratio)
            all_ratios.append(ratio)
    if all_ratios:
        stats["av1_vs_h265_savings_pct"] = (1 - _stats.geometric_mean(all_ratios)) * 100
    av1_h265_by_provider = {}
    for pid, rs in by_provider_ratios.items():
        if len(rs) >= 3:
            av1_h265_by_provider[provider_names.get(pid, pid)] = (1 - _stats.geometric_mean(rs)) * 100
    stats["av1_vs_h265_by_provider"] = av1_h265_by_provider

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

        # Group points by clip for per-clip BD-Rate
        points_by_clip = defaultdict(lambda: defaultdict(list))
        for r in codec_results:
            points_by_clip[r["clip"]][r["provider"]].append(r)

        for e in provider_entries:
            bdrate = None
            if ref_entry and e["pid"] != ref_entry["pid"]:
                per_clip = []
                for clip, provs in points_by_clip.items():
                    ref_clip = provs.get(ref_entry["pid"], [])
                    test_clip = provs.get(e["pid"], [])
                    if len(ref_clip) >= 2 and len(test_clip) >= 2:
                        bd = compute_bdrate(ref_clip, test_clip)
                        if bd is not None:
                            per_clip.append(bd)
                if per_clip:
                    bdrate = round(sum(per_clip) / len(per_clip), 1)

            summary[codec].append({
                "name": e["name"],
                "vmaf_avg": e["vmaf_avg"],
                "bitrate_at_target": f"{e['br_at_target']:.0f} kbps" if e["br_at_target"] else "-",
                "filesize_at_target": f"{e['fs_at_target'] / (1024*1024):.1f} MB" if e["fs_at_target"] else "-",
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
            "file_size_mb": r.get("file_size_bytes", 0) / (1024 * 1024),
            "vmaf_harmonic_mean": r.get("vmaf_harmonic_mean", 0),
            "vmaf_min": r.get("vmaf_min", 0),
            "vmaf_p01": r.get("vmaf_p01", 0),
            "compression_ratio": r.get("compression_ratio", 0),
        })

    return dict(data)


VIDAIO_PER_PASS_S = 120.0


def _iqr_filter(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values
    import statistics as _stats
    qs = _stats.quantiles(values, n=4)
    q1, q3 = qs[0], qs[2]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [v for v in values if lo <= v <= hi]


def build_speed_summary(events: list[dict], config: dict) -> list[dict]:
    """Per-(provider, codec) wall-clock encoding speed from JSONL events.

    Pairs each converged search_complete with its preceding search_start,
    derives total search time and per-pass time, then trims outliers via
    1.5× IQR. Vidaio uses a fixed measured per-pass mean (single encode).
    """
    from datetime import datetime as _dt

    provider_names = build_provider_name_map(config)
    starts: dict = {}
    completes: dict = {}
    for e in events:
        if e.get("event") == "search_start":
            starts.setdefault((e["provider"], e["clip"], e["codec"], e["target_vmaf"]), []).append(e)
        elif e.get("event") == "search_complete":
            completes.setdefault((e["provider"], e["clip"], e["codec"], e["target_vmaf"]), []).append(e)

    rows = []
    for key, comps in completes.items():
        if key[0] == "vidaio":
            continue
        for c in comps:
            if not c.get("converged"):
                continue
            ct = _dt.fromisoformat(c["timestamp"])
            best_s, best_st = None, None
            for s in starts.get(key, []):
                st = _dt.fromisoformat(s["timestamp"])
                if st <= ct and (best_st is None or st > best_st):
                    best_s, best_st = s, st
            if best_s is None:
                continue
            elapsed = (ct - best_st).total_seconds()
            steps = max(c.get("steps", 1), 1)
            rows.append({
                "provider": key[0], "codec": key[2],
                "total_s": elapsed, "per_pass_s": elapsed / steps, "steps": steps,
            })

    by_pc: dict = defaultdict(list)
    for r in rows:
        by_pc[(r["provider"], r["codec"])].append(r)

    summary = []
    for (pid, codec), group in sorted(by_pc.items()):
        per_pass = _iqr_filter([r["per_pass_s"] for r in group])
        total = _iqr_filter([r["total_s"] for r in group])
        steps_vals = [r["steps"] for r in group]
        summary.append({
            "provider_id": pid,
            "name": provider_names.get(pid, pid),
            "codec": codec,
            "n": len(group),
            "n_clean": len(per_pass),
            "avg_per_pass_s": sum(per_pass) / len(per_pass) if per_pass else 0,
            "avg_total_s": sum(total) / len(total) if total else 0,
            "avg_steps": sum(steps_vals) / len(steps_vals) if steps_vals else 0,
        })

    for codec in ("h265", "av1"):
        summary.append({
            "provider_id": "vidaio",
            "name": provider_names.get("vidaio", "Vidaio"),
            "codec": codec,
            "n": None, "n_clean": None,
            "avg_per_pass_s": VIDAIO_PER_PASS_S,
            "avg_total_s": VIDAIO_PER_PASS_S,
            "avg_steps": 1.0,
        })

    return summary


def avg_iterations_by_provider_codec(events: list[dict]) -> dict:
    """Compute mean iteration count per (provider, codec) from JSONL events."""
    from collections import defaultdict
    latest = {}
    for e in events:
        if e.get("event") != "search_complete" or not e.get("converged"):
            continue
        key = (e["provider"], e["clip"], e["codec"], e["target_vmaf"])
        if key not in latest or e["timestamp"] > latest[key]["timestamp"]:
            latest[key] = e
    by_pc = defaultdict(list)
    for e in latest.values():
        by_pc[(e["provider"], e["codec"])].append(e.get("steps", 1))
    return {k: sum(v) / len(v) for k, v in by_pc.items()}


def _parse_price(s):
    if not s or s in ("TBD", "-", "n/a"):
        return None
    try:
        return float(str(s).replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def build_pricing_data(pricing_rows: list[dict], events: list[dict], config: dict) -> dict:
    """Build sticker pricing + effective cost per source minute (sticker × avg iterations)."""
    provider_names = build_provider_name_map(config)
    avg_iters = avg_iterations_by_provider_codec(events)

    sticker = []
    for r in pricing_rows:
        sticker.append({
            "name": provider_names.get(r["provider"], r["provider"]),
            "pricing_model": r.get("pricing_model", ""),
            "cost_per_min_1080p_h265": r.get("cost_per_min_1080p_h265", "-"),
            "cost_per_min_1080p_av1": r.get("cost_per_min_1080p_av1", "-"),
            "notes": r.get("notes", ""),
            "source": r.get("source", ""),
        })

    effective = []
    for r in pricing_rows:
        pid = r["provider"]
        iters_h265 = avg_iters.get((pid, "h265"))
        iters_av1 = avg_iters.get((pid, "av1"))
        h265_sticker = _parse_price(r.get("cost_per_min_1080p_h265"))
        av1_sticker = _parse_price(r.get("cost_per_min_1080p_av1"))

        def fmt(sticker, iters):
            if sticker is None or iters is None:
                return "-"
            return f"${sticker * iters:.3f}"

        effective.append({
            "name": provider_names.get(pid, pid),
            "iters_h265": f"{iters_h265:.1f}" if iters_h265 else "-",
            "iters_av1": f"{iters_av1:.1f}" if iters_av1 else "-",
            "effective_h265": fmt(h265_sticker, iters_h265),
            "effective_av1": fmt(av1_sticker, iters_av1),
        })

    return {"sticker": sticker, "effective": effective}


def build_storage_projection(results: list[dict], clips: list[dict], config: dict) -> dict:
    """Storage cost projection per (vertical, provider, codec) at one VMAF target.

    Apples-to-apples: per (vertical, codec), restrict to the set of clips
    covered by every provider, AND require each provider's actual VMAF
    on that clip to be >= target. Then mean compression ratio across that
    common set is applied to a representative source.
    """
    import numpy as np
    provider_names = build_provider_name_map(config)
    proj = config.get("projection", {})
    hours = proj.get("hours", 1000)
    source_bitrate_kbps = proj.get("source_bitrate_kbps", 5000)
    target_vmaf = float(proj.get("storage_target_vmaf", 93))
    cost_per_gb_month = config.get("storage_cost_per_gb_month", 0.023)

    source_bytes = source_bitrate_kbps * 1000 * (hours * 3600) / 8

    clip_vertical = {c["clip"]: c["vertical"] for c in clips}
    codecs = config.get("codecs", [])

    # Apples-to-apples filter: per (vertical, codec), find clips where
    # ALL providers tested for that (codec) actually hit the target VMAF.
    by_vertical = defaultdict(list)
    for vertical in {clip_vertical.get(r["clip"]) for r in results if clip_vertical.get(r["clip"])}:
        for codec in codecs:
            providers_attempted = {
                r["provider"] for r in results
                if clip_vertical.get(r["clip"]) == vertical and r["codec"] == codec
            }
            if not providers_attempted:
                continue

            # Per (clip, provider): does the provider hit target on this clip?
            hit_by_provider = defaultdict(set)  # provider -> set of clips that hit
            ratio_lookup = {}  # (provider, clip) -> ratio
            for r in results:
                if (clip_vertical.get(r["clip"]) != vertical or r["codec"] != codec
                        or r.get("target_vmaf") != target_vmaf):
                    continue
                if (r.get("vmaf_harmonic_mean") or 0) >= target_vmaf and r.get("compression_ratio"):
                    hit_by_provider[r["provider"]].add(r["clip"])
                    ratio_lookup[(r["provider"], r["clip"])] = r["compression_ratio"]

            # Common-hit clips: all attempted providers hit the target
            if not hit_by_provider:
                continue
            attempted_who_hit = set(hit_by_provider.keys())
            if attempted_who_hit != providers_attempted:
                # At least one provider attempted but never hit target on any clip;
                # they get excluded from this (vertical, codec) comparison
                pass
            common_clips = set.intersection(*hit_by_provider.values()) if hit_by_provider else set()
            if not common_clips:
                continue

            for pid in providers_attempted & attempted_who_hit:
                ratios = [ratio_lookup[(pid, c)] for c in common_clips
                          if (pid, c) in ratio_lookup]
                if not ratios:
                    continue
                avg_ratio = float(np.mean(ratios))
                output_bytes = source_bytes / avg_ratio
                total_gb = output_bytes / (1024 ** 3)
                annual_cost = total_gb * cost_per_gb_month * 12
                by_vertical[vertical].append({
                    "provider": provider_names.get(pid, pid),
                    "codec": "AV1" if codec == "av1" else "H.265",
                    "ratio": avg_ratio,
                    "total_gb": total_gb,
                    "total_tb": total_gb / 1024,
                    "annual_cost": annual_cost,
                    "n_clips": len(common_clips),
                })

    return {
        "by_vertical": dict(by_vertical),
        "target_vmaf": target_vmaf,
        "source_bitrate_kbps": source_bitrate_kbps,
        "hours": hours,
        "cost_per_gb_month": cost_per_gb_month,
    }


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
            r["savings"] = f"-${saving:,.0f}" if saving > 0 else "-"

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
            "cost_per_vmaf_point": f"${cost_per_vmaf:,.0f}" if cost_per_vmaf else "-",
            "cost_per_gb_saved": f"${cost_per_gb:,.2f}" if gb_saved > 0 else "- (baseline)",
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


def build_headline_ranking(results: list[dict], config: dict, codec: str) -> dict:
    """Build the headline findings table for one codec, restricted to the
    common subset of (clip, target) combos covered by all providers tested
    for this codec. Returns a dict with rows and the subset size.
    """
    provider_names = build_provider_name_map(config)

    codec_results = [r for r in results if r.get("codec") == codec]
    if not codec_results:
        return {"rows": [], "n_combos": 0}

    # Find (clip, target) combos covered by all providers (in this codec)
    combos_by_provider = defaultdict(set)
    for r in codec_results:
        combos_by_provider[r["provider"]].add((r["clip"], r["target_vmaf"]))
    if not combos_by_provider:
        return {"rows": [], "n_combos": 0}
    common_combos = set.intersection(*combos_by_provider.values())

    # Filter to common subset
    common = [r for r in codec_results if (r["clip"], r["target_vmaf"]) in common_combos]

    by_provider = defaultdict(list)
    for r in common:
        by_provider[r["provider"]].append(r)

    provider_data = []
    for pid, data in by_provider.items():
        vmaf_vals = [r["vmaf_harmonic_mean"] for r in data if r.get("vmaf_harmonic_mean")]
        cr_vals = [r["compression_ratio"] for r in data if r.get("compression_ratio")]
        provider_data.append({
            "pid": pid,
            "name": provider_names.get(pid, pid),
            "vmaf_avg": sum(vmaf_vals) / len(vmaf_vals) if vmaf_vals else None,
            "points": data,
            "compression_ratio": sum(cr_vals) / len(cr_vals) if cr_vals else None,
        })

    providers_with_cr = [p for p in provider_data if p["compression_ratio"] is not None]
    if providers_with_cr:
        best = max(providers_with_cr, key=lambda p: p["compression_ratio"])
        ref_pid = best["pid"]
    else:
        ref_pid = None

    points_by_clip = defaultdict(lambda: defaultdict(list))
    for r in common:
        points_by_clip[r["clip"]][r["provider"]].append(r)

    rows = []
    for p in provider_data:
        bdrate = None
        if ref_pid and p["pid"] != ref_pid:
            per_clip_bdrates = []
            for clip, provs in points_by_clip.items():
                ref_clip = provs.get(ref_pid, [])
                test_clip = provs.get(p["pid"], [])
                if len(ref_clip) >= 2 and len(test_clip) >= 2:
                    bd = compute_bdrate(ref_clip, test_clip)
                    if bd is not None:
                        per_clip_bdrates.append(bd)
            if per_clip_bdrates:
                bdrate = round(sum(per_clip_bdrates) / len(per_clip_bdrates), 1)

        cr = p["compression_ratio"]
        rows.append({
            "name": p["name"],
            "vmaf_avg": p["vmaf_avg"],
            "bdrate": f"+{bdrate}%" if bdrate and bdrate > 0 else f"{bdrate}%" if bdrate else "ref",
            "bdrate_value": bdrate,
            "compression_ratio": f"{cr:.1f}x" if cr else "-",
            "compression_ratio_value": cr,
            "rank": 0,
        })

    ranked = sorted(
        [r for r in rows if r["compression_ratio_value"] is not None],
        key=lambda r: -r["compression_ratio_value"],
    )
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    for r in rows:
        if r["rank"] == 0:
            r["rank"] = "-"

    existing = {r["name"] for r in rows}
    for p in config["providers"]:
        if p["name"] not in existing:
            rows.append({
                "name": p["name"],
                "vmaf_avg": None,
                "bdrate": "-",
                "compression_ratio": "-",
                "rank": "-",
            })

    return {"rows": rows, "n_combos": len(common_combos)}


def build_per_vertical_bdrate(all_results: list[dict], clips: list[dict], config: dict) -> dict:
    """BD-Rate vs Vidaio, grouped by (codec, vertical).

    Pass full `all_results` (not pre-filtered) so we can also surface providers
    that *failed to converge* in a given vertical.
    """
    provider_names = build_provider_name_map(config)
    clip_vertical = {c["clip"]: c["vertical"] for c in clips}

    out: dict = {}
    for codec in ("h265", "av1"):
        codec_rows = [r for r in all_results if r.get("codec") == codec]
        by_vert_all = defaultdict(list)
        for r in codec_rows:
            v = clip_vertical.get(r["clip"])
            if v:
                by_vert_all[v].append(r)

        per_vert = {}
        for vert, rows_all in by_vert_all.items():
            converged_rows = [r for r in rows_all if r.get("converged")]
            by_clip_prov = defaultdict(lambda: defaultdict(list))
            for r in converged_rows:
                by_clip_prov[r["clip"]][r["provider"]].append(r)

            bdrates_by_provider = defaultdict(list)
            for clip, provs in by_clip_prov.items():
                ref_points = provs.get("vidaio", [])
                if len(ref_points) < 2:
                    continue
                for pid, points in provs.items():
                    if pid == "vidaio" or len(points) < 2:
                        continue
                    bd = compute_bdrate(ref_points, points)
                    if bd is not None:
                        bdrates_by_provider[pid].append(bd)

            providers_in_vertical = {r["provider"] for r in rows_all}
            converged_providers = {r["provider"] for r in converged_rows}
            failed = providers_in_vertical - converged_providers

            per_vert[vert] = {
                "bdrate": {
                    provider_names.get(pid, pid): sum(v) / len(v)
                    for pid, v in bdrates_by_provider.items()
                },
                "n_clips": {
                    provider_names.get(pid, pid): len(v)
                    for pid, v in bdrates_by_provider.items()
                },
                "failed_providers": [provider_names.get(pid, pid) for pid in sorted(failed)],
            }
        out[codec] = per_vert
    return out


def build_providers_context(config: dict) -> list[dict]:
    """Build provider metadata for the template."""
    provider_meta = {
        "bitmovin": {
            "rate_control": "CRF",
            "quality_param": "crf (0-51 for H.265)",
            "codec_support": "H.265 (AV1 TODO)",
            "steps_to_optimal": "Binary search over CRF values to hit target VMAF",
            "quality_control": "CRF (single-pass)",
            "codec_selection": "Full control",
            "expertise": "High",
            "optimization_process": "Binary search over CRF, measure VMAF after each encode",
            "iteration_required": "Yes - ~5-6 encodes per clip",
            "sdk": "bitmovin-api-sdk (Python)",
            "auth_setup": "API key",
            "job_complexity": "Complex (input → encoding → stream → codec config → muxing → start)",
            "result_retrieval": "Poll + S3 download",
            "docs_quality": "Extensive",
        },
        "cloudflare": {
            "rate_control": "Not used",
            "quality_param": "Not used",
            "codec_support": "Not used (H.264 only, excluded from benchmark)",
            "steps_to_optimal": "Not used",
            "quality_control": "Not used",
            "codec_selection": "Not used",
            "expertise": "Not used",
            "optimization_process": "Not used",
            "iteration_required": "Not used",
            "sdk": "cloudflare (Python)",
            "auth_setup": "API token",
            "job_complexity": "Not used",
            "result_retrieval": "Not used",
            "docs_quality": "Not used",
        },
        "mediaconvert": {
            "rate_control": "QVBR",
            "quality_param": "QvbrQualityLevel (1-10) + fine-tune",
            "codec_support": "H.265 MULTI_PASS_HQ (AV1 TODO)",
            "steps_to_optimal": "Binary search over QVBR levels to hit target VMAF",
            "quality_control": "QVBR with fine-tune",
            "codec_selection": "Full control",
            "expertise": "High",
            "optimization_process": "Binary search over QVBR level, measure VMAF after each encode",
            "iteration_required": "Yes - ~3-5 encodes per clip",
            "sdk": "boto3",
            "auth_setup": "IAM role + endpoint discovery",
            "job_complexity": "Moderate (job JSON with nested settings)",
            "result_retrieval": "Poll + S3 download",
            "docs_quality": "Extensive",
        },
        "mux": {
            "rate_control": "Not used",
            "quality_param": "Not used",
            "codec_support": "Not used (H.264 only downloads, excluded from benchmark)",
            "steps_to_optimal": "Not used",
            "quality_control": "Not used",
            "codec_selection": "Not used",
            "expertise": "Not used",
            "optimization_process": "Not used",
            "iteration_required": "Not used",
            "sdk": "mux-python",
            "auth_setup": "Token ID + secret",
            "job_complexity": "Not used",
            "result_retrieval": "Not used",
            "docs_quality": "Not used",
        },
        "vidaio": {
            "rate_control": "VMAF-targeted",
            "quality_param": "Target VMAF (low/medium/high → 85/89/93)",
            "codec_support": "H.265, AV1",
            "steps_to_optimal": "Pick quality level, single encode",
            "quality_control": "Direct VMAF targeting",
            "codec_selection": "Full control",
            "expertise": "Low",
            "optimization_process": "Single encode - provider targets VMAF directly",
            "iteration_required": "No - 1 encode per clip",
            "sdk": "None (web UI)",
            "auth_setup": "Web UI account",
            "job_complexity": "Manual upload via web UI",
            "result_retrieval": "Provider-managed bucket",
            "docs_quality": "Limited public docs",
        },
        "zencoder": {
            "rate_control": "Quality",
            "quality_param": "quality (1-5)",
            "codec_support": "H.265 (AV1 TODO)",
            "steps_to_optimal": "Binary search over quality 1-5 to hit target VMAF",
            "quality_control": "Quality parameter + speed 1 (best)",
            "codec_selection": "Full control",
            "expertise": "Medium",
            "optimization_process": "Binary search over quality 1-5, measure VMAF after each encode",
            "iteration_required": "Yes - ~2-3 encodes per clip",
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
    all_results = load_csv(report_dir / config["data"]["results"])
    results = [r for r in all_results if r.get("converged")]
    clips = load_csv(report_dir / config["data"]["clip_metadata"])
    encoding_times = load_csv(report_dir / config["data"]["encoding_times"])
    pricing_rows = load_csv(report_dir / config["data"]["pricing"])

    # Load raw JSONL events to derive iteration counts
    import json, glob
    jsonl_dir = report_dir.parent / "data" / "results"
    jsonl_events = []
    for f in sorted(jsonl_dir.glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if line.strip():
                    jsonl_events.append(json.loads(line))

    providers = build_providers_context(config)

    # For headline ranking, only use results from benchmark codecs (av1, h265)
    # to avoid cross-codec comparisons with black-box H.264 providers
    benchmark_codecs = set(config.get("codecs", []))
    comparable_results = [r for r in results if r.get("codec") in benchmark_codecs]
    stats = compute_stats(comparable_results, clips, config)

    # Derive BD-Rate headline numbers from per-codec rankings (apples-to-apples).
    headline_h265 = build_headline_ranking(comparable_results, config, "h265")
    headline_av1 = build_headline_ranking(comparable_results, config, "av1")
    for codec, hr in (("h265", headline_h265), ("av1", headline_av1)):
        ref_row = next((r for r in hr["rows"] if r["bdrate"] == "ref"), None)
        if ref_row:
            stats[f"{codec}_bdrate_best_provider"] = ref_row["name"]
        gaps = sorted(
            [(r["name"], r["bdrate_value"]) for r in hr["rows"] if r.get("bdrate_value") is not None],
            key=lambda x: x[1],
        )
        if gaps:
            stats[f"{codec}_bdrate_second"] = gaps[0]
            stats[f"{codec}_bdrate_worst"] = gaps[-1]

    per_vertical_bdrate = build_per_vertical_bdrate(all_results, clips, config)

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
        "vmaf_targets": config.get("vmaf_targets", [85, 89, 93]),
        "storage_cost_per_gb_month": config.get("storage_cost_per_gb_month", 0.023),
        "projection": config.get("projection", {}),
        "stats": stats,
        "clips": clips,
        "codecs": config.get("codecs", []),
        "verticals": config.get("verticals", []),
        "providers": providers,
        "all_results": results,
        "headline_h265": headline_h265,
        "headline_av1": headline_av1,
        "codec_summary": build_codec_summary(results, config),
        "vertical_data": build_vertical_data(results, clips),
        "speed_summary": build_speed_summary(jsonl_events, config),
        "pricing": build_pricing_data(pricing_rows, jsonl_events, config),
        "per_vertical_bdrate": per_vertical_bdrate,
        "storage_projection": build_storage_projection(comparable_results, clips, config),
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
