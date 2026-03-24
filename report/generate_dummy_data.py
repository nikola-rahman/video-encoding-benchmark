#!/usr/bin/env python3
"""Generate realistic dummy CSV data for testing end-to-end report rendering."""

import csv
import random
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent / "data"

CLIPS = [
    ("ProductTurntable_1080p_30s", "ecommerce", "1920x1080", 30, 42.1, 8.3, "Pexels", "Pexels License", 89_400_000),
    ("UnboxingReview_1080p_45s", "ecommerce", "1920x1080", 45, 38.5, 15.2, "Pexels", "Pexels License", 134_100_000),
    ("PhoneVlog_720p_60s", "ugc", "1280x720", 60, 29.8, 21.7, "Creative Commons", "CC-BY-4.0", 54_000_000),
    ("ScreenRecording_1080p_30s", "ugc", "1920x1080", 30, 55.2, 5.1, "Self-captured", "CC0", 89_400_000),
    ("FilmScan_1080p_60s", "archive", "1920x1080", 60, 44.7, 18.9, "Internet Archive", "Public Domain", 178_800_000),
    ("DocumentaryClip_1080p_45s", "archive", "1920x1080", 45, 36.3, 14.6, "Prelinger Archives", "Public Domain", 134_100_000),
    ("LectureSlides_1080p_30s", "education", "1920x1080", 30, 52.8, 3.2, "MIT OCW", "CC-BY-NC-SA", 89_400_000),
    ("CodingTutorial_1080p_45s", "education", "1920x1080", 45, 58.1, 6.8, "Self-captured", "CC0", 134_100_000),
]

# Provider encoding configs: (provider_id, codec, quality_settings, base_efficiency)
# Higher efficiency = lower bitrate for same VMAF
PROVIDER_CONFIGS = {
    "bitmovin": {
        "av1": [("crf20", 0.88), ("crf25", 0.92), ("crf30", 0.95), ("crf35", 0.97), ("crf40", 0.99)],
        "h265": [("crf18", 0.82), ("crf22", 0.87), ("crf26", 0.91), ("crf30", 0.94), ("crf34", 0.97)],
    },
    "mediaconvert": {
        "av1": [("qvbr3", 0.86), ("qvbr5", 0.90), ("qvbr7", 0.94), ("qvbr9", 0.97)],
        "h265": [("qvbr3", 0.80), ("qvbr5", 0.85), ("qvbr7", 0.90), ("qvbr9", 0.95)],
    },
    "zencoder": {
        "av1": [("q2", 0.85), ("q3", 0.90), ("q4", 0.94), ("q5", 0.98)],
        "h265": [("q2", 0.79), ("q3", 0.85), ("q4", 0.90), ("q5", 0.95)],
    },
    "mux": {
        "h264": [("auto", 0.83)],
    },
    "cloudflare": {
        "h264": [("auto", 0.80)],
    },
    "vidaio": {
        "av1": [("basic", 0.91), ("medium", 0.95), ("hyper", 0.98)],
        "h265": [("basic", 0.85), ("medium", 0.90), ("hyper", 0.95)],
    },
}

# Per-clip complexity affects how much bitrate is needed
CLIP_COMPLEXITY = {
    "ProductTurntable_1080p_30s": 0.6,
    "UnboxingReview_1080p_45s": 0.75,
    "PhoneVlog_720p_60s": 0.85,
    "ScreenRecording_1080p_30s": 0.4,
    "FilmScan_1080p_60s": 0.9,
    "DocumentaryClip_1080p_45s": 0.7,
    "LectureSlides_1080p_30s": 0.3,
    "CodingTutorial_1080p_45s": 0.45,
}

# Encoding speed multipliers (higher = slower)
SPEED_MULT = {
    "bitmovin": 2.5,
    "mediaconvert": 1.8,
    "zencoder": 2.0,
    "mux": 1.5,
    "cloudflare": 1.3,
    "vidaio": 4.5,
}


def generate_encoding(clip_name, clip_dur, input_size, complexity, provider, codec, quality, efficiency):
    """Generate a single realistic encoding result."""
    # Base bitrate depends on complexity and quality setting efficiency
    # Lower efficiency = higher quality = higher bitrate
    base_bitrate_kbps = 800 + complexity * 3000
    # AV1 is ~30% more efficient than H.265, H.264 is ~40% less efficient
    codec_mult = {"av1": 0.70, "h265": 1.0, "h264": 1.40}[codec]
    # Quality setting: lower efficiency number = higher quality = higher bitrate
    quality_mult = 2.2 - (efficiency * 1.8)

    bitrate = base_bitrate_kbps * codec_mult * quality_mult
    bitrate *= random.uniform(0.92, 1.08)  # noise
    bitrate = max(100, bitrate)

    file_size = int(bitrate * 1000 / 8 * clip_dur)

    # VMAF: higher efficiency = higher VMAF at same bitrate
    base_vmaf = 75 + efficiency * 22
    # More complex content is harder to encode well
    vmaf_penalty = complexity * 8
    vmaf_mean = base_vmaf - vmaf_penalty + random.uniform(-1.5, 1.5)
    vmaf_mean = min(99.9, max(60, vmaf_mean))

    vmaf_min = vmaf_mean - random.uniform(3, 12)
    vmaf_min = max(40, vmaf_min)
    vmaf_hmean = vmaf_mean - random.uniform(0.3, 1.5)
    vmaf_p01 = vmaf_min + random.uniform(0.5, 3)
    vmaf_p05 = vmaf_p01 + random.uniform(1, 4)

    compression_ratio = input_size / file_size if file_size > 0 else 1

    return {
        "clip": clip_name,
        "vertical": next(c[1] for c in CLIPS if c[0] == clip_name),
        "provider": provider,
        "codec": codec,
        "quality_setting": quality,
        "bitrate_kbps": round(bitrate, 1),
        "file_size_bytes": file_size,
        "vmaf_mean": round(vmaf_mean, 2),
        "vmaf_min": round(vmaf_min, 2),
        "vmaf_harmonic_mean": round(vmaf_hmean, 2),
        "vmaf_p01": round(vmaf_p01, 2),
        "vmaf_p05": round(vmaf_p05, 2),
        "compression_ratio": round(compression_ratio, 2),
    }


def main():
    DATA_DIR.mkdir(exist_ok=True)

    # -- clip_metadata.csv --
    with open(DATA_DIR / "clip_metadata.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "vertical", "resolution", "duration_s", "si", "ti", "source", "license", "input_size_bytes"])
        for c in CLIPS:
            w.writerow(c)

    # -- results.csv --
    results = []
    for clip_name, vertical, res, dur, si, ti, source, lic, input_size in CLIPS:
        complexity = CLIP_COMPLEXITY[clip_name]
        for provider, codecs in PROVIDER_CONFIGS.items():
            for codec, settings in codecs.items():
                for quality, efficiency in settings:
                    row = generate_encoding(clip_name, dur, input_size, complexity, provider, codec, quality, efficiency)
                    results.append(row)

    with open(DATA_DIR / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "clip", "vertical", "provider", "codec", "quality_setting",
            "bitrate_kbps", "file_size_bytes", "vmaf_mean", "vmaf_min",
            "vmaf_harmonic_mean", "vmaf_p01", "vmaf_p05", "compression_ratio",
        ])
        w.writeheader()
        w.writerows(results)

    # -- encoding_times.csv --
    with open(DATA_DIR / "encoding_times.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "provider", "codec", "quality_setting", "encode_time_s", "clip_duration_s"])
        for r in results:
            speed = SPEED_MULT[r["provider"]]
            clip_dur = next(c[3] for c in CLIPS if c[0] == r["clip"])
            encode_time = clip_dur * speed * random.uniform(0.8, 1.2)
            w.writerow([r["clip"], r["provider"], r["codec"], r["quality_setting"],
                        round(encode_time, 1), clip_dur])

    # -- pricing.csv --
    with open(DATA_DIR / "pricing.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["provider", "pricing_model", "cost_per_min_1080p", "cost_per_min_4k", "notes"])
        w.writerow(["bitmovin", "per-minute codec-dependent", "0.012", "0.024", "AV1 premium applies"])
        w.writerow(["mediaconvert", "per-minute tier-dependent", "0.015", "0.030", "AV1 requires Professional tier"])
        w.writerow(["zencoder", "per-minute output-based", "0.010", "0.020", ""])
        w.writerow(["mux", "per-minute ingested+stored+delivered", "0.007", "0.014", "encoding bundled with storage"])
        w.writerow(["cloudflare", "per-1K-min stored+delivered", "0.005", "0.005", "no separate encoding fee"])
        w.writerow(["vidaio", "per-minute quality-optimized", "0.018", "0.036", "includes quality optimization"])

    # -- perframe_vmaf.csv --
    # Generate per-frame VMAF scores for a subset of results (one quality setting per provider per clip)
    with open(DATA_DIR / "perframe_vmaf.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "provider", "codec", "quality_setting", "frame", "vmaf"])
        seen = set()
        for r in results:
            key = (r["clip"], r["provider"], r["codec"])
            if key in seen:
                continue
            seen.add(key)
            clip_dur = next(c[3] for c in CLIPS if c[0] == r["clip"])
            fps = 30
            n_frames = clip_dur * fps
            vmaf_mean = r["vmaf_mean"]
            vmaf_min = r["vmaf_min"]
            # Generate realistic per-frame scores: mostly near mean with occasional dips
            for frame in range(n_frames):
                base = vmaf_mean + random.gauss(0, 1.5)
                # Scene change dips every ~5 seconds
                if frame % (fps * 5) < 3:
                    base -= random.uniform(3, vmaf_mean - vmaf_min)
                score = min(100, max(vmaf_min - 2, base))
                w.writerow([r["clip"], r["provider"], r["codec"], r["quality_setting"],
                            frame, round(score, 2)])

    # -- iframe_data.csv --
    # I-frame counts and GOP structure per provider per clip
    IFRAME_INTERVALS = {
        "bitmovin": 4.0,      # streaming-optimized: 4s GOPs
        "mediaconvert": 3.0,  # streaming-optimized: 3s GOPs
        "zencoder": 4.0,      # streaming-optimized: 4s GOPs
        "mux": 4.0,           # black-box, assumed streaming
        "cloudflare": 2.0,    # black-box, short GOPs
        "vidaio": 8.0,        # quality-optimized: longer GOPs
    }
    with open(DATA_DIR / "iframe_data.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip", "provider", "codec", "quality_setting", "iframe_count",
                     "gop_length_s", "iframe_bits_pct", "total_frames"])
        seen = set()
        for r in results:
            key = (r["clip"], r["provider"], r["codec"])
            if key in seen:
                continue
            seen.add(key)
            clip_dur = next(c[3] for c in CLIPS if c[0] == r["clip"])
            fps = 30
            total_frames = clip_dur * fps
            gop_s = IFRAME_INTERVALS.get(r["provider"], 4.0) * random.uniform(0.9, 1.1)
            iframe_count = max(1, int(clip_dur / gop_s) + 1)
            # I-frames use 10-30% of total bits depending on how many there are
            iframe_ratio = iframe_count / total_frames
            iframe_bits_pct = round(iframe_ratio * random.uniform(800, 1500), 1)
            iframe_bits_pct = min(45, max(5, iframe_bits_pct))
            w.writerow([r["clip"], r["provider"], r["codec"], r["quality_setting"],
                        iframe_count, round(gop_s, 2), iframe_bits_pct, total_frames])

    print(f"Generated {len(results)} result rows across {len(CLIPS)} clips")
    print(f"Files written to {DATA_DIR}/")


if __name__ == "__main__":
    main()
