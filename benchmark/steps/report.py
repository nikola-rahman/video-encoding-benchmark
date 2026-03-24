"""Rate-distortion plots and summary tables."""

import os
from pathlib import Path

from benchmark.metadata import load_vmaf_results
from benchmark.util.log import setup_logging

log = setup_logging("report")


def run(config: dict):
    """Generate rate-distortion plots from VMAF results."""
    data_dir = Path(config.get("data_dir", "./data"))
    results_path = data_dir / "vmaf_results.json"

    if not results_path.exists():
        log.error(f"VMAF results not found: {results_path}")
        log.error("Run 'python -m benchmark measure' first.")
        return

    results = load_vmaf_results(results_path)
    if not results:
        log.info("No results to plot.")
        return

    plot_rate_distortion(results, str(data_dir))

    # Print summary table
    log.info(f"\n{'=' * 60}")
    log.info("VMAF RESULTS SUMMARY")
    log.info(f"{'=' * 60}")
    for enc in results:
        log.info(f"\n  [{enc['provider']}] {enc['encoding_name']} ({enc['codec']})")
        for r in enc.get("renditions", []):
            score = r.get("vmaf_score")
            kbps = r.get("bitrate_kbps") or "?"
            ratio = r.get("compression_ratio", "?")
            if score is not None:
                log.info(f"    {kbps:>8} kbps | {ratio:>6}x compression -> VMAF {score:.4f}")
            else:
                log.info(f"    {kbps:>8} kbps | ERROR: {r.get('error', 'unknown')}")


def plot_rate_distortion(results: list[dict], output_dir: str):
    """Plot rate-distortion curves (VMAF vs bitrate) grouped by input video."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not installed, skipping rate-distortion plot (pip install matplotlib)")
        return

    by_input = {}
    for enc in results:
        input_name = enc["input"]
        if input_name not in by_input:
            by_input[input_name] = {}
        provider = enc["provider"]
        if provider not in by_input[input_name]:
            by_input[input_name][provider] = []
        for r in enc.get("renditions", []):
            if r.get("vmaf_score") is not None:
                by_input[input_name][provider].append({
                    "bitrate_kbps": r.get("bitrate_kbps") or r["bitrate_bps"] / 1000,
                    "vmaf": r["vmaf_score"],
                })

    markers = ["o", "s", "^", "D", "v", "P", "*"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

    for input_name, providers in by_input.items():
        fig, ax = plt.subplots(figsize=(10, 6))

        for i, (provider, points) in enumerate(sorted(providers.items())):
            points.sort(key=lambda p: p["bitrate_kbps"])
            bitrates = [p["bitrate_kbps"] for p in points]
            vmafs = [p["vmaf"] for p in points]
            color = colors[i % len(colors)]
            marker = markers[i % len(markers)]
            ax.plot(bitrates, vmafs, marker=marker, color=color, label=provider,
                    linewidth=2, markersize=8)
            for br, vm in zip(bitrates, vmafs):
                ax.annotate(f"{vm:.1f}", (br, vm), textcoords="offset points",
                            xytext=(5, 8), fontsize=8, color=color)

        ax.set_xlabel("Bitrate (kbps)", fontsize=12)
        ax.set_ylabel("VMAF Score", fontsize=12)
        ax.set_title(f"Rate-Distortion: {input_name}", fontsize=14)
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(bottom=max(0, ax.get_ylim()[0] - 5), top=min(100, ax.get_ylim()[1] + 2))

        plot_path = os.path.join(output_dir, f"rd_curve_{input_name.replace('.', '_')}.png")
        fig.tight_layout()
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)
        log.info(f"  Rate-distortion plot: {plot_path}")
