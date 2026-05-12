#!/usr/bin/env python3
"""Generate all report figures from CSV data."""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import yaml

REPORT_DIR = Path(__file__).parent
DEFAULT_CONFIG = REPORT_DIR / "report.yaml"

# ── Style ────────────────────────────────────────────────────────

# Okabe-Ito colorblind-safe palette (alphabetical provider order)
PROVIDER_COLORS = {
    "AWS MediaConvert": "#E69F00",
    "Bitmovin": "#56B4E9",
    "Brightcove Zencoder": "#009E73",
    "Cloudflare Stream": "#F0E442",
    "Mux": "#0072B2",
    "Vidaio": "#D55E00",
}
PROVIDER_MARKERS = {
    "AWS MediaConvert": "o",
    "Bitmovin": "s",
    "Brightcove Zencoder": "^",
    "Cloudflare Stream": "D",
    "Mux": "D",
    "Vidaio": "v",
}

VMAF_TRANSPARENT = 93
VMAF_INDISTINGUISHABLE = 95

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
    "figure.dpi": 150,
})


def get_color(name):
    return PROVIDER_COLORS.get(name, "#888888")


def get_marker(name):
    return PROVIDER_MARKERS.get(name, "o")


# ── Data loading ─────────────────────────────────────────────────


def load_csv(path):
    if not path.exists():
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


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def provider_name(pid, config):
    for p in config["providers"]:
        if p["id"] == pid:
            return p["name"]
    return pid


def is_blackbox(pid, config):
    for p in config["providers"]:
        if p["id"] == pid:
            return p.get("blackbox", False)
    return False


# ── Chart helpers ────────────────────────────────────────────────


def add_vmaf_lines(ax, targets=None):
    """Add horizontal VMAF target lines."""
    if targets is None:
        targets = [85, 89, 93]
    for t in targets:
        ax.axhline(y=t, color="gray", linestyle="--", alpha=0.5, linewidth=1)
        ax.text(ax.get_xlim()[1], t + 0.3, f"VMAF {t}", ha="right",
                va="bottom", fontsize=8, color="gray")


def plot_rd_curves(data_by_provider, config, title, out_path, blackbox_ids=None):
    """Plot rate-distortion curves for multiple providers."""
    blackbox_ids = blackbox_ids or set()
    fig, ax = plt.subplots(figsize=(10, 6))

    for pname in sorted(data_by_provider.keys()):
        points = data_by_provider[pname]
        points.sort(key=lambda p: p["bitrate_kbps"])
        bitrates = [p["bitrate_kbps"] for p in points]
        vmafs = [p["vmaf_harmonic_mean"] for p in points]
        color = get_color(pname)
        marker = get_marker(pname)

        pid = None
        for p in config["providers"]:
            if p["name"] == pname:
                pid = p["id"]
        is_bb = pid in blackbox_ids

        if is_bb:
            ax.scatter(bitrates, vmafs, color=color, marker="D", s=120, zorder=5,
                       label=f"{pname} (single point)", edgecolors="black", linewidths=0.5)
        else:
            ax.plot(bitrates, vmafs, marker=marker, color=color, label=pname,
                    linewidth=2, markersize=7)

    ax.set_xlabel("Bitrate (kbps)")
    ax.set_ylabel("VMAF Score")
    ax.set_title(title)
    ax.legend(fontsize=9)
    add_vmaf_lines(ax)
    ax.set_ylim(bottom=max(75, ax.get_ylim()[0] - 2), top=min(100, ax.get_ylim()[1] + 1))
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  {out_path.name}")


def plot_bar(labels, values, title, ylabel, out_path, color_map=None, pct_labels=False):
    """Horizontal bar chart."""
    fig, ax = plt.subplots(figsize=(9, max(4, len(labels) * 0.8)))
    colors = [get_color(l) for l in labels] if color_map is None else [color_map.get(l, "#888") for l in labels]
    bars = ax.barh(labels, values, color=colors, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, values):
        label = f"{val:.1f}" if not pct_labels else f"{val:.0f}%"
        ax.text(bar.get_width() + max(values) * 0.02, bar.get_y() + bar.get_height() / 2,
                label, va="center", fontsize=9)

    ax.set_xlabel(ylabel)
    ax.set_title(title)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  {out_path.name}")


def plot_placeholder(title, out_path):
    """Create a placeholder figure."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, f"[Placeholder]\n{title}", ha="center", va="center",
            fontsize=14, color="gray", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  {out_path.name} (placeholder)")


# ── Chart generators ─────────────────────────────────────────────


def gen_aggregate_rd(results, config, figures_dir):
    """Figure 1.1 - Average bitrate by VMAF target, one subplot per codec."""
    benchmark_codecs = sorted(config.get("codecs", []))
    codec_labels = {"av1": "AV1", "h265": "H.265"}

    # Group by (provider_name, codec, target_vmaf) → list of bitrates
    by_key = defaultdict(list)
    for r in results:
        if r.get("codec") not in benchmark_codecs:
            continue
        pname = provider_name(r["provider"], config)
        by_key[(pname, r["codec"], r["target_vmaf"])].append(r["bitrate_kbps"])

    avg = {k: np.mean(v) for k, v in by_key.items()}
    targets = sorted(set(t for _, _, t in avg.keys()))

    fig, axes = plt.subplots(1, len(benchmark_codecs), figsize=(6 * len(benchmark_codecs), 6), sharey=True)
    if len(benchmark_codecs) == 1:
        axes = [axes]

    for ax, codec in zip(axes, benchmark_codecs):
        providers = sorted(set(p for p, c, t in avg.keys() if c == codec))
        x = np.arange(len(targets))
        n = len(providers)
        width = 0.8 / max(n, 1)

        for i, pname in enumerate(providers):
            color = get_color(pname)
            vals = [avg.get((pname, codec, t), 0) for t in targets]
            offset = (i - n / 2 + 0.5) * width
            bars = ax.bar(x + offset, vals, width, label=pname, color=color)
            for bar, val in zip(bars, vals):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 10,
                            f"{val:.0f}", ha="center", va="bottom", fontsize=8)

        ax.set_xticks(x)
        ax.set_xticklabels([f"VMAF {int(t)}" for t in targets])
        ax.set_title(codec_labels.get(codec, codec))
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("Average Bitrate (kbps)")
    fig.suptitle("Average Bitrate by VMAF Target (lower is better)", fontsize=13)
    fig.tight_layout()
    fig.savefig(figures_dir / "aggregate_rd.png")
    plt.close(fig)
    print(f"  aggregate_rd.png")


def _plot_rd_with_failed(ax, by_pc_converged, by_pc_failed, config):
    """Plot RD curves with median+IQR for converged. Failures returned as annotation lines.

    Two annotation categories:
      - failures: converged=False rows (encoder couldn't reach target at all)
      - undershoots: converged=True but median achieved VMAF more than tolerance below target
    """
    tolerance = 1.0
    failure_notes = []
    for pname in sorted(set(by_pc_converged.keys()) | set(by_pc_failed.keys())):
        color = get_color(pname)

        for clip, points in by_pc_converged.get(pname, {}).items():
            points.sort(key=lambda p: p["bitrate_kbps"])
            ax.plot([p["bitrate_kbps"] for p in points],
                    [p["vmaf_harmonic_mean"] for p in points],
                    color=color, alpha=0.15, linewidth=0.8, marker="o", markersize=2)

        by_target = defaultdict(list)
        for clip, points in by_pc_converged.get(pname, {}).items():
            for p in points:
                by_target[p["target_vmaf"]].append((p["bitrate_kbps"], p["vmaf_harmonic_mean"]))

        med_x, med_y, lo_x, hi_x = [], [], [], []
        for t in sorted(by_target.keys()):
            br = [p[0] for p in by_target[t]]
            vm = [p[1] for p in by_target[t]]
            if len(br) < 2:
                continue
            med_x.append(np.median(br))
            med_y.append(np.median(vm))
            lo_x.append(np.percentile(br, 25))
            hi_x.append(np.percentile(br, 75))
            median_vmaf = float(np.median(vm))
            if median_vmaf < t - tolerance:
                failure_notes.append((pname, color, len(vm), median_vmaf, t, "undershoot"))

        if med_x:
            ax.fill_betweenx(med_y, lo_x, hi_x, color=color, alpha=0.18)
            ax.plot(med_x, med_y, color=color, linewidth=2.5,
                    marker="o", markersize=7, label=pname,
                    markeredgecolor="white", markeredgewidth=1)

        failed = by_pc_failed.get(pname, {})
        if failed:
            best_vmafs = []
            for clip, points in failed.items():
                if points:
                    best_vmafs.append(max(p["vmaf_harmonic_mean"] for p in points))
            if best_vmafs:
                avg_max = sum(best_vmafs) / len(best_vmafs)
                failure_notes.append((pname, color, len(best_vmafs), avg_max, None, "failure"))
    return failure_notes


def gen_codec_rd(results, config, figures_dir):
    """Figures 4.x - Per-codec RD: median+IQR + per-clip lines + X for failed attempts."""
    targets = config.get("vmaf_targets", [85, 89, 93])

    for codec in config.get("codecs", []):
        codec_label = "AV1" if codec == "av1" else "H.265"
        by_conv = defaultdict(lambda: defaultdict(list))
        by_failed = defaultdict(lambda: defaultdict(list))
        for r in results:
            if r.get("codec") != codec:
                continue
            pname = provider_name(r["provider"], config)
            target = (by_conv if r.get("converged") else by_failed)
            target[pname][r["clip"]].append(r)

        out_path = figures_dir / f"aggregate_rd_{codec}.png"
        if not by_conv and not by_failed:
            plot_placeholder(f"Rate-Distortion - {codec_label} (no data)", out_path)
            continue

        fig, ax = plt.subplots(figsize=(11, 7))
        failure_notes = _plot_rd_with_failed(ax, by_conv, by_failed, config)

        ax.set_xlabel("Bitrate (kbps)")
        ax.set_ylabel("VMAF (harmonic mean)")
        ax.set_title(f"Rate-Distortion - {codec_label}")
        ax.set_xscale("log")
        ax.legend(fontsize=10, loc="lower right")
        ax.grid(True, alpha=0.3, which="both")
        for target in targets:
            ax.axhline(y=target, color="gray", linestyle="--", alpha=0.4, linewidth=1)
            ax.text(ax.get_xlim()[1], target + 0.2, f"VMAF {target}", ha="right",
                    va="bottom", fontsize=8, color="gray")
        ax.set_ylim(min(targets) - 5, 96)
        if failure_notes:
            failures = [n for n in failure_notes if n[5] == "failure"]
            undershoots = [n for n in failure_notes if n[5] == "undershoot"]
            note_lines = []
            if failures:
                note_lines.append("Did not reach target VMAF (max achieved):")
                for pname, color, n, avg_max, _, _ in failures:
                    note_lines.append(f"  • {pname}: {avg_max:.0f} VMAF on {n} clip(s)")
            if undershoots:
                if note_lines:
                    note_lines.append("")
                note_lines.append("Converged below target (median achieved):")
                for pname, color, n, med, t, _ in undershoots:
                    note_lines.append(f"  • {pname}: target {t:.0f} -> median {med:.1f} on {n} clip(s)")
            ax.text(0.02, 0.02, "\n".join(note_lines),
                    transform=ax.transAxes, fontsize=8, color="#444",
                    verticalalignment="bottom",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                              edgecolor="#bbb", alpha=0.9))
        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        print(f"  {out_path.name}")


def gen_vertical_rd(results, clips, config, figures_dir):
    """Per-vertical per-codec RD with median+IQR + X markers for failed attempts."""
    clip_vertical = {c["clip"]: c["vertical"] for c in clips}
    targets = config.get("vmaf_targets", [85, 89, 93])

    for codec in config.get("codecs", []):
        codec_label = "AV1" if codec == "av1" else "H.265"
        for v in config.get("verticals", []):
            by_conv = defaultdict(lambda: defaultdict(list))
            by_failed = defaultdict(lambda: defaultdict(list))
            for r in results:
                if r.get("codec") != codec:
                    continue
                if clip_vertical.get(r["clip"]) != v["id"]:
                    continue
                pname = provider_name(r["provider"], config)
                target = (by_conv if r.get("converged") else by_failed)
                target[pname][r["clip"]].append(r)

            if not by_conv and not by_failed:
                continue

            fig, ax = plt.subplots(figsize=(11, 7))
            failure_notes = _plot_rd_with_failed(ax, by_conv, by_failed, config)
            ax.set_xlabel("Bitrate (kbps)")
            ax.set_ylabel("VMAF (harmonic mean)")
            ax.set_title(f"RD - {codec_label}, {v['name']}")
            ax.set_xscale("log")
            ax.legend(fontsize=10, loc="lower right")
            ax.grid(True, alpha=0.3, which="both")
            for target in targets:
                ax.axhline(y=target, color="gray", linestyle="--", alpha=0.4, linewidth=1)
                ax.text(ax.get_xlim()[1], target + 0.2, f"VMAF {target}", ha="right",
                        va="bottom", fontsize=8, color="gray")
            ax.set_ylim(min(targets) - 5, 96)
            if failure_notes:
                failures = [n for n in failure_notes if n[5] == "failure"]
                undershoots = [n for n in failure_notes if n[5] == "undershoot"]
                note_lines = []
                if failures:
                    note_lines.append("Did not reach target VMAF (max achieved):")
                    for pname, color, n, avg_max, _, _ in failures:
                        note_lines.append(f"  • {pname}: {avg_max:.0f} VMAF on {n} clip(s)")
                if undershoots:
                    if note_lines:
                        note_lines.append("")
                    note_lines.append("Converged below target (median achieved):")
                    for pname, color, n, med, t, _ in undershoots:
                        note_lines.append(f"  • {pname}: target {t:.0f} -> median {med:.1f} on {n} clip(s)")
                ax.text(0.02, 0.02, "\n".join(note_lines),
                        transform=ax.transAxes, fontsize=8, color="#444",
                        verticalalignment="bottom",
                        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                                  edgecolor="#bbb", alpha=0.9))
            fig.tight_layout()
            fig.savefig(figures_dir / f"rd_{codec}_{v['id']}.png")
            plt.close(fig)
            print(f"  rd_{codec}_{v['id']}.png")


def gen_per_clip_rd(results, config, figures_dir):
    """Appendix A - Per-clip RD curves."""
    by_clip = defaultdict(lambda: defaultdict(list))
    for r in results:
        pname = provider_name(r["provider"], config)
        by_clip[r["clip"]][pname].append(r)

    for clip_name, providers in by_clip.items():
        plot_rd_curves(providers, config, f"RD - {clip_name}",
                       figures_dir / f"rd_per_clip_{clip_name}.png")


def gen_storage_savings_bar(results, config, figures_dir):
    """Figure 1.2 / 5.1 - File size at VMAF target."""
    from report.generate import interpolate_metric_at_vmaf, build_provider_name_map
    vmaf_target = config.get("vmaf_transparent", VMAF_TRANSPARENT)
    benchmark_codecs = set(config.get("codecs", []))

    by_provider = defaultdict(list)
    for r in results:
        if r.get("codec") in benchmark_codecs:
            by_provider[r["provider"]].append(r)

    provider_fs = {}
    for pid, data in by_provider.items():
        fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        if fs:
            pname = provider_name(pid, config)
            provider_fs[pname] = fs / (1024 * 1024)

    if not provider_fs:
        return

    sorted_providers = sorted(provider_fs.items(), key=lambda x: x[1])
    labels = [p[0] for p in sorted_providers]
    values = [p[1] for p in sorted_providers]

    plot_bar(labels, values, f"File Size at VMAF ≥ {vmaf_target}", "File Size (MB)",
             figures_dir / "storage_savings_bar.png")
    plot_bar(labels, values, f"File Size at VMAF ≥ {vmaf_target}", "File Size (MB)",
             figures_dir / "filesize_at_vmaf_target.png")


def gen_bdrate_bars(results, config, figures_dir):
    """BD-Rate bar charts per codec, computed per-clip and averaged."""
    from report.generate import compute_bdrate

    for codec in config.get("codecs", []):
        codec_label = "AV1" if codec == "av1" else "H.265"
        by_provider = defaultdict(list)
        for r in results:
            if r.get("codec") == codec:
                by_provider[r["provider"]].append(r)

        # Reference = provider with smallest avg compression-ratio-equivalent
        # (use median bitrate at the highest common VMAF target as proxy)
        provider_avg_br = {}
        for pid, data in by_provider.items():
            brs = [r["bitrate_kbps"] for r in data if r.get("bitrate_kbps")]
            if brs:
                provider_avg_br[pid] = sum(brs) / len(brs)
        if not provider_avg_br:
            continue
        ref_pid = min(provider_avg_br, key=provider_avg_br.get)

        # Group by clip for per-clip BD-Rate
        points_by_clip = defaultdict(lambda: defaultdict(list))
        for r in results:
            if r.get("codec") == codec:
                points_by_clip[r["clip"]][r["provider"]].append(r)

        labels, values = [], []
        for pid, data in sorted(by_provider.items()):
            pname = provider_name(pid, config)
            if pid == ref_pid:
                labels.append(f"{pname} (ref)")
                values.append(0)
            else:
                per_clip = []
                for clip, provs in points_by_clip.items():
                    ref_clip = provs.get(ref_pid, [])
                    test_clip = provs.get(pid, [])
                    if len(ref_clip) >= 2 and len(test_clip) >= 2:
                        bd = compute_bdrate(ref_clip, test_clip)
                        if bd is not None:
                            per_clip.append(bd)
                if per_clip:
                    labels.append(pname)
                    values.append(round(sum(per_clip) / len(per_clip), 1))

        if labels:
            fig, ax = plt.subplots(figsize=(9, max(4, len(labels) * 0.8)))
            colors = ["#2ca02c" if v <= 0 else "#d62728" for v in values]
            bars = ax.barh(labels, values, color=colors, edgecolor="white")
            for bar, val in zip(bars, values):
                ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                        f"{val:+.1f}%", va="center", fontsize=9)
            ax.axvline(x=0, color="black", linewidth=0.8)
            ax.set_xlabel("BD-Rate (%)")
            ax.set_title(f"BD-Rate - {codec_label} (lower is better)")
            ax.invert_yaxis()
            fig.tight_layout()
            fig.savefig(figures_dir / f"bdrate_bar_{codec}.png")
            plt.close(fig)
            print(f"  bdrate_bar_{codec}.png")


def gen_si_ti_scatter(clips, config, figures_dir):
    """Figure 3.2 - SI vs TI scatter."""
    palette = ["#E69F00", "#56B4E9", "#009E73", "#D55E00", "#0072B2", "#CC79A7"]
    vertical_ids = [v["id"] for v in config.get("verticals", [])]
    vertical_colors = {vid: palette[i % len(palette)] for i, vid in enumerate(vertical_ids)}
    from adjustText import adjust_text

    fig, ax = plt.subplots(figsize=(8, 6))
    texts = []
    for c in clips:
        color = vertical_colors.get(c["vertical"], "#888")
        ax.scatter(c["si"], c["ti"], color=color, s=100, edgecolors="black", linewidths=0.5, zorder=5)
        texts.append(ax.text(c["si"], c["ti"], c["clip"], fontsize=7))

    adjust_text(texts, arrowprops=dict(arrowstyle="-", color="gray", alpha=0.5))

    # Legend
    vertical_names = {v["id"]: v["name"] for v in config.get("verticals", [])}
    for vid, color in vertical_colors.items():
        ax.scatter([], [], color=color, s=80, label=vertical_names.get(vid, vid), edgecolors="black", linewidths=0.5)
    ax.legend()
    ax.set_xlabel("Spatial Information (SI)")
    ax.set_ylabel("Temporal Information (TI)")
    ax.set_title("Test Content Complexity")
    fig.tight_layout()
    fig.savefig(figures_dir / "si_ti_scatter.png")
    plt.close(fig)
    print(f"  si_ti_scatter.png")


def gen_vmaf_percentiles(results, config, figures_dir):
    """Figure 6.1 - VMAF percentile comparison."""
    benchmark_codecs = set(config.get("codecs", []))
    by_provider = defaultdict(lambda: {"mean": [], "min": [], "p01": [], "p05": []})
    for r in results:
        if r.get("codec") not in benchmark_codecs:
            continue
        pname = provider_name(r["provider"], config)
        if r.get("vmaf_harmonic_mean"):
            by_provider[pname]["mean"].append(r["vmaf_harmonic_mean"])
        if r.get("vmaf_min"):
            by_provider[pname]["min"].append(r["vmaf_min"])
        if r.get("vmaf_p01"):
            by_provider[pname]["p01"].append(r["vmaf_p01"])
        if r.get("vmaf_p05"):
            by_provider[pname]["p05"].append(r["vmaf_p05"])

    labels = sorted(by_provider.keys())
    x = np.arange(len(labels))
    width = 0.2

    fig, ax = plt.subplots(figsize=(10, 6))
    metrics = [("mean", "Mean", 0), ("p05", "5th Percentile", 1), ("p01", "1st Percentile", 2), ("min", "Minimum", 3)]
    colors_m = ["#2ca02c", "#56B4E9", "#E69F00", "#D55E00"]

    for metric, label, i in metrics:
        vals = []
        for pname in labels:
            data = by_provider[pname][metric]
            vals.append(sum(data) / len(data) if data else 0)
        ax.bar(x + i * width, vals, width, label=label, color=colors_m[i], alpha=0.8)

    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("VMAF Score")
    ax.set_title("VMAF Percentile Comparison")
    ax.legend()
    ax.set_ylim(bottom=70)
    fig.tight_layout()
    fig.savefig(figures_dir / "vmaf_percentiles.png")
    plt.close(fig)
    print(f"  vmaf_percentiles.png")


def gen_encoding_speed(encoding_times, config, figures_dir):
    """Figure 10.1 - Encoding speed bar chart."""
    by_provider = defaultdict(list)
    for r in encoding_times:
        if r.get("encode_time_s") and r.get("clip_duration_s"):
            pname = provider_name(r["provider"], config)
            by_provider[pname].append(r["encode_time_s"] / r["clip_duration_s"])

    if not by_provider:
        return

    labels = sorted(by_provider.keys())
    values = [sum(by_provider[l]) / len(by_provider[l]) for l in labels]
    sorted_pairs = sorted(zip(labels, values), key=lambda x: x[1])
    labels = [p[0] for p in sorted_pairs]
    values = [p[1] for p in sorted_pairs]

    plot_bar(labels, values, "Encoding Speed (× real-time)", "Speed (× real-time)",
             figures_dir / "encoding_speed.png")


def gen_tco_stacked(results, pricing_rows, config, figures_dir):
    """Figure 9.1 - TCO stacked bar."""
    from report.generate import build_tco
    benchmark_codecs = set(config.get("codecs", []))
    comparable = [r for r in results if r.get("codec") in benchmark_codecs]
    tco_data = build_tco(comparable, pricing_rows, config)
    if not tco_data:
        return

    tco_data.sort(key=lambda x: x["total_cost"])
    labels = [d["name"] for d in tco_data]
    enc_costs = [d["encoding_cost"] for d in tco_data]
    stor_costs = [d["storage_cost"] for d in tco_data]

    fig, ax = plt.subplots(figsize=(9, max(4, len(labels) * 0.8)))
    y = np.arange(len(labels))
    ax.barh(y, enc_costs, color="#56B4E9", label="Encoding Cost")
    ax.barh(y, stor_costs, left=enc_costs, color="#E69F00", label="Annual Storage Cost")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Cost (USD)")
    ax.set_title("Total Cost of Ownership: Encoding + Storage")
    ax.legend()
    ax.invert_yaxis()

    for i, d in enumerate(tco_data):
        ax.text(d["total_cost"] + max(d["total_cost"] for d in tco_data) * 0.02, i,
                f"${d['total_cost']:,.0f}", va="center", fontsize=9)

    fig.tight_layout()
    fig.savefig(figures_dir / "tco_stacked_bar.png")
    plt.close(fig)
    print(f"  tco_stacked_bar.png")


def gen_codec_comparison(results, config, figures_dir):
    """Figure 4.3.1 - AV1 vs H.265 overlay using median curves per provider/codec."""
    codecs = config.get("codecs", [])
    if len(codecs) < 2:
        return

    targets = config.get("vmaf_targets", [85, 89, 93])

    fig, ax = plt.subplots(figsize=(11, 7))
    for p in config["providers"]:
        for codec in codecs:
            codec_label = "AV1" if codec == "av1" else "H.265"
            linestyle = "-" if codec == "av1" else "--"
            points = [r for r in results
                      if r["provider"] == p["id"] and r.get("codec") == codec]
            if not points:
                continue
            by_target = defaultdict(list)
            for r in points:
                by_target[r["target_vmaf"]].append((r["bitrate_kbps"], r["vmaf_harmonic_mean"]))

            med_x, med_y = [], []
            for t in sorted(by_target.keys()):
                br = [v[0] for v in by_target[t]]
                vm = [v[1] for v in by_target[t]]
                if len(br) < 2:
                    continue
                med_x.append(np.median(br))
                med_y.append(np.median(vm))

            if med_x:
                ax.plot(med_x, med_y,
                        marker=get_marker(p["name"]), color=get_color(p["name"]),
                        linestyle=linestyle, linewidth=2, markersize=7,
                        markeredgecolor="white", markeredgewidth=1,
                        label=f"{p['name']} ({codec_label})")

    ax.set_xlabel("Median Bitrate (kbps)")
    ax.set_ylabel("Median VMAF (harmonic mean)")
    ax.set_title("AV1 vs. H.265 - Codec Comparison")
    ax.set_xscale("log")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3, which="both")
    for target in targets:
        ax.axhline(y=target, color="gray", linestyle="--", alpha=0.4, linewidth=1)
        ax.text(ax.get_xlim()[1], target + 0.2, f"VMAF {target}", ha="right",
                va="bottom", fontsize=8, color="gray")
    fig.tight_layout()
    fig.savefig(figures_dir / "codec_comparison_overlay.png")
    plt.close(fig)
    print(f"  codec_comparison_overlay.png")




def gen_perframe_traces(perframe, clips, config, figures_dir):
    """Figures 6.2, 6.3 - Per-frame VMAF traces for easy and hard clips."""
    # Sort clips by TI to find easy (low TI) and hard (high TI)
    by_ti = sorted([c for c in clips if c.get("ti")], key=lambda c: c["ti"])
    if not by_ti:
        return

    easy_clip = by_ti[0]["clip"]
    hard_clip = by_ti[-1]["clip"]

    for clip_name, out_name, title_suffix in [
        (easy_clip, "perframe_easy", f"Easy Clip ({easy_clip})"),
        (hard_clip, "perframe_hard", f"Hard Clip ({hard_clip})"),
    ]:
        clip_frames = [r for r in perframe if r["clip"] == clip_name]
        by_provider = defaultdict(list)
        for r in clip_frames:
            pname = provider_name(r["provider"], config)
            by_provider[pname].append(r)

        fig, ax = plt.subplots(figsize=(12, 5))
        # Plot max 4 providers to avoid clutter
        for pname in sorted(by_provider.keys())[:4]:
            frames = sorted(by_provider[pname], key=lambda r: r["frame"])
            xs = [r["frame"] for r in frames]
            ys = [r["vmaf"] for r in frames]
            ax.plot(xs, ys, color=get_color(pname), alpha=0.7, linewidth=0.5, label=pname)

        ax.set_xlabel("Frame")
        ax.set_ylabel("VMAF Score")
        ax.set_title(f"Per-Frame VMAF - {title_suffix}")
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=60, top=100)
        add_vmaf_lines(ax)
        fig.tight_layout()
        fig.savefig(figures_dir / f"{out_name}.png")
        plt.close(fig)
        print(f"  {out_name}.png")


def gen_consistency_matrix(perframe, clips, config, figures_dir):
    """Figure 6.4 - Quality consistency matrix (sparkline grid)."""
    clip_names = sorted(set(r["clip"] for r in perframe))
    provider_names_list = sorted(set(provider_name(r["provider"], config) for r in perframe))[:5]

    # Build lookup
    data = defaultdict(lambda: defaultdict(list))
    for r in perframe:
        pname = provider_name(r["provider"], config)
        if pname in provider_names_list:
            data[r["clip"]][pname].append((r["frame"], r["vmaf"]))

    n_clips = len(clip_names)
    n_providers = len(provider_names_list)

    fig, axes = plt.subplots(n_clips, n_providers, figsize=(n_providers * 2.5, n_clips * 1.2),
                              sharex=True, sharey=True)
    if n_clips == 1:
        axes = [axes]
    if n_providers == 1:
        axes = [[ax] for ax in axes]

    for i, clip in enumerate(clip_names):
        for j, pname in enumerate(provider_names_list):
            ax = axes[i][j]
            frames = sorted(data[clip].get(pname, []))
            if frames:
                xs = [f[0] for f in frames]
                ys = [f[1] for f in frames]
                ax.plot(xs, ys, color=get_color(pname), linewidth=0.3, alpha=0.8)
                ax.fill_between(xs, ys, alpha=0.1, color=get_color(pname))
            ax.set_ylim(70, 100)
            ax.set_xticks([])
            ax.set_yticks([])
            if i == 0:
                ax.set_title(pname, fontsize=8)
            if j == 0:
                short_name = clip.split("_")[0]
                ax.set_ylabel(short_name, fontsize=7, rotation=0, ha="right", va="center")

    fig.suptitle("Quality Consistency Matrix - Per-Frame VMAF", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(figures_dir / "consistency_matrix.png")
    plt.close(fig)
    print(f"  consistency_matrix.png")


def gen_iframe_charts(iframe_data, config, figures_dir):
    """Figures 7.1, 7.2 - I-frame count and bit allocation."""
    by_provider = defaultdict(list)
    for r in iframe_data:
        pname = provider_name(r["provider"], config)
        by_provider[pname].append(r)

    # Figure 7.1 - I-frame count per minute
    labels, values = [], []
    for pname in sorted(by_provider.keys()):
        rows = by_provider[pname]
        counts = []
        for r in rows:
            dur = r.get("total_frames", 1800) / 30  # assume 30fps
            iframes_per_min = (r["iframe_count"] / dur) * 60 if dur > 0 else 0
            counts.append(iframes_per_min)
        labels.append(pname)
        values.append(sum(counts) / len(counts) if counts else 0)

    sorted_pairs = sorted(zip(labels, values), key=lambda x: x[1])
    plot_bar([p[0] for p in sorted_pairs], [p[1] for p in sorted_pairs],
             "I-Frames per Minute", "I-Frames / min",
             figures_dir / "iframe_count.png")

    # Figure 7.2 - Bit allocation (I-frame % vs inter-frame %)
    fig, ax = plt.subplots(figsize=(9, max(4, len(by_provider) * 0.8)))
    labels_sorted = sorted(by_provider.keys())
    iframe_pcts = []
    for pname in labels_sorted:
        rows = by_provider[pname]
        pcts = [r["iframe_bits_pct"] for r in rows if r.get("iframe_bits_pct")]
        iframe_pcts.append(sum(pcts) / len(pcts) if pcts else 0)

    inter_pcts = [100 - p for p in iframe_pcts]
    y = np.arange(len(labels_sorted))
    ax.barh(y, iframe_pcts, color="#D55E00", label="I-Frames")
    ax.barh(y, inter_pcts, left=iframe_pcts, color="#56B4E9", label="P/B-Frames")
    ax.set_yticks(y)
    ax.set_yticklabels(labels_sorted)
    ax.set_xlabel("% of Total Bits")
    ax.set_title("Bit Allocation: I-Frames vs. Inter-Frames")
    ax.legend()
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(figures_dir / "bit_allocation.png")
    plt.close(fig)
    print(f"  bit_allocation.png")


def gen_ease_vs_efficiency(results, config, figures_dir):
    """Figure 8.1 - Ease of use vs compression efficiency scatter."""
    from report.generate import interpolate_metric_at_vmaf
    vmaf_target = config.get("vmaf_transparent", 93)
    benchmark_codecs = set(config.get("codecs", []))

    # Ease scores (qualitative: 1=hardest, 5=easiest)
    ease_scores = {
        "bitmovin": 2, "mediaconvert": 2, "zencoder": 3,
        "cloudflare": 5, "mux": 5, "vidaio": 4,
    }

    by_provider = defaultdict(list)
    for r in results:
        if r.get("codec") in benchmark_codecs:
            by_provider[r["provider"]].append(r)

    fig, ax = plt.subplots(figsize=(8, 6))
    for pid, data in by_provider.items():
        fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        if fs is None:
            continue
        fs_mb = fs / (1024 * 1024)
        ease = ease_scores.get(pid, 3)
        pname = provider_name(pid, config)
        ax.scatter(fs_mb, ease, color=get_color(pname), s=150, edgecolors="black",
                   linewidths=0.5, zorder=5)
        ax.annotate(pname, (fs_mb, ease), textcoords="offset points",
                    xytext=(8, 0), fontsize=9, va="center")

    ax.set_xlabel(f"File Size at VMAF {vmaf_target} (MB)")
    ax.set_ylabel("Ease of Use (1=hardest, 5=easiest)")
    ax.set_title("Ease of Use vs. Compression Efficiency")
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1 - Expert", "2 - High", "3 - Medium", "4 - Low", "5 - None"])
    fig.tight_layout()
    fig.savefig(figures_dir / "ease_vs_efficiency.png")
    plt.close(fig)
    print(f"  ease_vs_efficiency.png")


def gen_breakeven(results, pricing_rows, config, figures_dir):
    """Figure 9.2 - Break-even analysis."""
    from report.generate import interpolate_metric_at_vmaf
    vmaf_target = config.get("vmaf_transparent", 93)
    benchmark_codecs = set(config.get("codecs", []))
    cost_per_gb_month = config.get("storage_cost_per_gb_month", 0.023)
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
        if r.get("codec") in benchmark_codecs:
            by_provider[r["provider"]].append(r)

    # Compute per-provider: encoding cost and monthly storage savings vs worst
    provider_data = {}
    for pid, data in by_provider.items():
        fs = interpolate_metric_at_vmaf(data, vmaf_target, "file_size_bytes")
        if fs and pid in pricing_map:
            total_minutes = num_videos * duration_s / 60
            enc_cost = total_minutes * pricing_map[pid]
            monthly_storage = (fs * num_videos / (1024 ** 3)) * cost_per_gb_month
            provider_data[pid] = {"enc_cost": enc_cost, "monthly_storage": monthly_storage}

    if len(provider_data) < 2:
        plot_placeholder("Break-Even Analysis", figures_dir / "breakeven.png")
        return

    # Worst storage (most expensive provider)
    worst_pid = max(provider_data, key=lambda p: provider_data[p]["monthly_storage"])
    worst_monthly = provider_data[worst_pid]["monthly_storage"]
    worst_enc = provider_data[worst_pid]["enc_cost"]

    labels, months = [], []
    for pid, d in sorted(provider_data.items()):
        if pid == worst_pid:
            continue
        pname = provider_name(pid, config)
        monthly_saving = worst_monthly - d["monthly_storage"]
        enc_premium = d["enc_cost"] - worst_enc
        if monthly_saving > 0 and enc_premium > 0:
            breakeven = enc_premium / monthly_saving
            labels.append(pname)
            months.append(breakeven)
        elif enc_premium <= 0:
            labels.append(pname)
            months.append(0)  # cheaper encoding AND better compression

    if labels:
        plot_bar(labels, months,
                 f"Break-Even: Months for Compression Savings to Offset Encoding Premium\n(vs. {provider_name(worst_pid, config)})",
                 "Months", figures_dir / "breakeven.png")
    else:
        plot_placeholder("Break-Even Analysis", figures_dir / "breakeven.png")


def gen_rate_control_accuracy(results, config, figures_dir):
    """Figure 7.3 - Requested quality vs actual VMAF."""
    # Map quality settings to a numeric "requested quality" scale
    quality_map = {
        "crf20": 80, "crf22": 78, "crf25": 75, "crf26": 74, "crf30": 70,
        "crf34": 66, "crf35": 65, "crf40": 60,
        "qvbr3": 65, "qvbr5": 75, "qvbr7": 85, "qvbr9": 92,
        "q2": 65, "q3": 75, "q4": 85, "q5": 92,
        "basic": 80, "medium": 87, "hyper": 93,
    }

    fig, ax = plt.subplots(figsize=(8, 6))
    benchmark_codecs = set(config.get("codecs", []))

    for r in results:
        if r.get("codec") not in benchmark_codecs:
            continue
        qs = r.get("quality_setting", "")
        if qs not in quality_map:
            continue
        requested = quality_map[qs]
        actual = r.get("vmaf_harmonic_mean", 0)
        pname = provider_name(r["provider"], config)
        ax.scatter(requested, actual, color=get_color(pname), s=20, alpha=0.4)

    # Reference line y=x
    ax.plot([55, 100], [55, 100], "k--", alpha=0.3, linewidth=1)

    # Legend with one point per provider
    seen = set()
    for r in results:
        pname = provider_name(r["provider"], config)
        if pname not in seen:
            ax.scatter([], [], color=get_color(pname), s=50, label=pname)
            seen.add(pname)
    ax.legend(fontsize=8, markerscale=1.5)

    ax.set_xlabel("Requested Quality (mapped to VMAF scale)")
    ax.set_ylabel("Actual VMAF")
    ax.set_title("Rate Control Accuracy: Requested vs. Actual Quality")
    fig.tight_layout()
    fig.savefig(figures_dir / "rate_control_accuracy.png")
    plt.close(fig)
    print(f"  rate_control_accuracy.png")


def gen_content_gallery(config, figures_dir):
    """Content gallery - one thumbnail per vertical from report/assets/thumbs."""
    import matplotlib.image as mpimg

    thumbs_dir = REPORT_DIR / "assets" / "thumbs"

    verticals = config.get("verticals", [])
    # Count clips per vertical from catalog
    from benchmark.samples.catalog import load_catalog
    catalog = load_catalog()
    clip_counts = defaultdict(int)
    for s in catalog:
        clip_counts[s["vertical"]] += 1

    import math
    n = len(verticals)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    axes_flat = np.array(axes).flatten() if n > 1 else [axes]

    for i, v in enumerate(verticals):
        ax = axes_flat[i]
        vid = v["id"]
        name = v["name"]
        count = clip_counts.get(vid, 0)
        thumb_name = v.get("thumb")
        thumb = thumbs_dir / thumb_name if thumb_name else None

        if thumb and thumb.exists():
            img = mpimg.imread(str(thumb))
            ax.imshow(img)
        else:
            ax.set_facecolor("#f0f0f0")
            ax.text(0.5, 0.5, "MISSING", ha="center", va="center",
                    fontsize=14, color="red", fontweight="bold", transform=ax.transAxes)

        ax.set_title(f"{name}\n{count} clips", fontsize=11, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_linewidth(0.5)
            spine.set_color("#ccc")

    # Hide unused subplots
    for j in range(len(verticals), len(axes_flat)):
        axes_flat[j].set_visible(False)

    total_clips = sum(clip_counts.values())
    fig.suptitle(f"Test Content: {total_clips} clips across {len([v for v in verticals if clip_counts.get(v['id'], 0) > 0])} verticals", fontsize=13)
    fig.tight_layout()
    fig.savefig(figures_dir / "content_gallery.png")
    plt.close(fig)
    print(f"  content_gallery.png")


def gen_storage_projection(results, clips, config, figures_dir):
    """Storage cost chart per vertical at fixed VMAF target."""
    from report.generate import build_storage_projection
    proj = build_storage_projection(results, clips, config)
    by_vertical = proj["by_vertical"]
    if not by_vertical:
        return

    # Baseline: cost of storing the raw source without re-encoding
    source_bytes = proj["source_bitrate_kbps"] * 1000 * (proj["hours"] * 3600) / 8
    baseline_gb = source_bytes / (1024 ** 3)
    baseline_cost = baseline_gb * proj["cost_per_gb_month"] * 12
    baseline_tb = baseline_gb / 1024

    vertical_order = [v["id"] for v in config.get("verticals", [])]
    vertical_names = {v["id"]: v["name"] for v in config.get("verticals", [])}
    vids = [v for v in vertical_order if v in by_vertical]

    import math
    n = len(vids)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 4.5 * rows), squeeze=False)

    for i, vid in enumerate(vids):
        ax = axes[i // cols][i % cols]
        entries = sorted(by_vertical[vid], key=lambda e: (e["provider"], e["codec"]))
        labels = [f"{e['provider']}\n{e['codec']}" for e in entries]
        costs = [e["annual_cost"] for e in entries]
        colors = [get_color(e["provider"]) for e in entries]
        bars = ax.bar(range(len(entries)), costs, color=colors, edgecolor="white", linewidth=0.5)
        for bar, e in zip(bars, entries):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"${e['annual_cost']:,.0f}\n({e['total_tb']:.1f} TB)",
                    ha="center", va="bottom", fontsize=8)
        ax.axhline(y=baseline_cost, color="#888", linestyle="--", linewidth=1.2)
        ax.text(len(entries) - 0.5, baseline_cost,
                f"  no re-encoding: ${baseline_cost:,.0f} ({baseline_tb:.1f} TB)",
                color="#444", fontsize=8, va="center", ha="right",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                          edgecolor="#bbb", alpha=0.9))
        ax.set_xticks(range(len(entries)))
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(vertical_names.get(vid, vid), fontweight="bold")
        ax.set_ylabel("Annual S3 cost ($)")
        ax.grid(axis="y", alpha=0.3)
        if costs:
            ax.set_ylim(0, max(max(costs), baseline_cost) * 1.3)

    for j in range(len(vids), rows * cols):
        axes[j // cols][j % cols].set_visible(False)

    fig.suptitle(f"Annual storage cost at VMAF {int(proj['target_vmaf'])}", fontsize=13)
    fig.tight_layout()
    fig.savefig(figures_dir / "storage_projection.png")
    plt.close(fig)
    print(f"  storage_projection.png")


# ── Main ─────────────────────────────────────────────────────────


def generate_all(config_path=DEFAULT_CONFIG):
    config = load_config(config_path)
    report_dir = config_path.parent
    figures_dir = report_dir / config.get("figures_dir", "figures")
    if figures_dir.exists():
        for f in figures_dir.glob("*.png"):
            f.unlink()
    figures_dir.mkdir(parents=True, exist_ok=True)

    all_results = load_csv(report_dir / config["data"]["results"])
    results = [r for r in all_results if r.get("converged")]
    clips = load_csv(report_dir / config["data"]["clip_metadata"])
    encoding_times = load_csv(report_dir / config["data"]["encoding_times"])
    pricing_rows = load_csv(report_dir / config["data"]["pricing"])

    global VMAF_TRANSPARENT, VMAF_INDISTINGUISHABLE
    VMAF_TRANSPARENT = config.get("vmaf_transparent", 93)
    VMAF_INDISTINGUISHABLE = config.get("vmaf_indistinguishable", 95)

    print("Generating figures...")

    # Data-driven charts
    gen_aggregate_rd(results, config, figures_dir)
    gen_codec_rd(all_results, config, figures_dir)
    gen_vertical_rd(all_results, clips, config, figures_dir)
    gen_per_clip_rd(results, config, figures_dir)
    gen_bdrate_bars(results, config, figures_dir)
    gen_si_ti_scatter(clips, config, figures_dir)
    gen_vmaf_percentiles(results, config, figures_dir)
    gen_encoding_speed(encoding_times, config, figures_dir)
    gen_tco_stacked(results, pricing_rows, config, figures_dir)
    gen_codec_comparison(results, config, figures_dir)
    gen_storage_projection(results, clips, config, figures_dir)

    # Charts from extended data (per-frame VMAF, iframe)
    perframe_path = report_dir / config["data"].get("perframe_vmaf", "data/perframe_vmaf.csv")
    iframe_path = report_dir / config["data"].get("iframe_data", "data/iframe_data.csv")
    perframe = load_csv(perframe_path)
    iframe_data = load_csv(iframe_path)

    if perframe:
        gen_perframe_traces(perframe, clips, config, figures_dir)
        gen_consistency_matrix(perframe, clips, config, figures_dir)
    else:
        plot_placeholder("Per-Frame VMAF - Easy Clip", figures_dir / "perframe_easy.png")
        plot_placeholder("Per-Frame VMAF - Hard Clip", figures_dir / "perframe_hard.png")
        plot_placeholder("Quality Consistency Matrix", figures_dir / "consistency_matrix.png")

    if iframe_data:
        gen_iframe_charts(iframe_data, config, figures_dir)
    else:
        plot_placeholder("I-Frame Count per Minute", figures_dir / "iframe_count.png")
        plot_placeholder("Bit Allocation: I vs P/B Frames", figures_dir / "bit_allocation.png")

    gen_ease_vs_efficiency(results, config, figures_dir)
    gen_breakeven(results, pricing_rows, config, figures_dir)
    gen_rate_control_accuracy(results, config, figures_dir)

    gen_content_gallery(config, figures_dir)

    print(f"\nDone. {len(list(figures_dir.glob('*.png')))} figures in {figures_dir}/")


if __name__ == "__main__":
    generate_all()
