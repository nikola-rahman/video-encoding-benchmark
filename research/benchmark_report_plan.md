# Video Encoding Provider Comparison Report — Plan

## Objective

Fair, reproducible comparison of video encoding quality across cloud providers at matched bitrates, with analysis relevant to different customer segments.

## Providers to Test

### Already Tested
- **Vidaio** — AV1 (basic, medium, hyper presets)
- **Bitmovin** — AV1, Per-Title encoding, VOD_STANDARD preset

### To Add
- **AWS Elemental MediaConvert** — largest market share
- **Google Cloud Transcoder API** — growing fast, Google-backed
- **Mux** — developer-focused, popular with startups
- **Brightcove/Zencoder** — established leader, 30%+ combined market share
- **Encoding.com** — long-established, reports VMAF scores
- **Cloudflare Stream** — free encoding, pay for storage/delivery

## Test Content

### Input Videos

**Principle: real-world representative content, not academic test sequences.** BBB/TOS are useful for tooling validation but the final report must use content that matches what paying customers actually encode. Nobody's production workload is a Blender demo reel.

#### Content Categories (sourced from real-world examples)

| # | Category | What It Represents | Target Source |
|---|----------|-------------------|---------------|
| 1 | **Product video** | E-commerce turntable/lifestyle shot | Real product listing or stock footage |
| 2 | **Screen recording + webcam** | E-learning course content | Record a real coding tutorial or slide deck |
| 3 | **Talking head (studio)** | Interviews, corporate video, YouTube | Clean studio setup, single speaker |
| 4 | **Talking head (casual)** | UGC vlogs, selfie video | Phone camera, indoor, variable lighting |
| 5 | **Handheld outdoor** | UGC, social media clips | Phone footage, walking, scene changes |
| 6 | **Sports / fast motion** | Highlights, action content | Licensed stock or CC sports footage |
| 7 | **Low-light / noisy** | Events, concerts, phone at night | Phone camera in dim environment |
| 8 | **Grainy cinematic** | Film archives, indie film | 35mm scan or grainy stock footage |
| 9 | **Dense detail / crowd** | Events, street scenes, travel | Busy street or market scene |
| 10 | **Mixed / montage** | Marketing video, social ad | Quick cuts, transitions, text overlays, mixed content |

Minimum 6 for a credible report, ideal 10. Each clip 30-60 seconds.

#### Why These Categories
- Categories 1-3 map directly to paying customer segments (e-commerce, e-learning, corporate)
- Categories 4-5 represent the largest volume of video encoded globally (UGC)
- Categories 6-9 stress different encoder weaknesses (motion, noise, grain, complexity)
- Category 10 tests scene detection and rate control adaptability

#### What We're NOT Using
- Synthetic test patterns (not representative of any real workload)
- Blender open movie project clips (good for tooling, not for the report)
- ITU/MPEG reference sequences (academic, not representative)
- Xiph.org derf collection (same — useful for research, not for a customer-facing report)

### Input Format
- Lossless H.264 (`-qp 0 -bf 0`) to eliminate reference quality issues
- Exact integer-second duration, no audio
- Validated with `preprocess_inputs.py`

## Codec Selection

- **AV1** — primary comparison (all providers that support it)
- **H.265/HEVC** — secondary (broader support across providers)
- **H.264** — baseline reference (universal support)

## What to Measure

### Core Metrics (per rendition)
| Metric | Description |
|--------|-------------|
| **VMAF** | Full-video perceptual quality score (0-100) |
| **Actual bitrate** | ffprobe measured, not provider-reported label |
| **File size** | Total bytes |
| **Compression ratio** | Input size / output size |

### Encoder Behavior Analysis
| Metric | Description |
|--------|-------------|
| **Bitrate accuracy** | Actual vs requested — does the encoder respect targets? |
| **GOP structure** | I-frame count, interval, regularity |
| **Frame types** | I/P/B frame distribution |
| **Rate control** | How well does bitrate track across scenes? |

### Rate-Distortion Curves
- Multiple bitrate points per provider per video
- X-axis: actual bitrate (kbps), Y-axis: VMAF
- Provider that is higher-left wins (better quality, less bitrate)

## Bitrate Test Points

To ensure fair comparison, encode each video at matched bitrate targets:

### BigBuckBunny (720p)
- ~350 kbps (low)
- ~550 kbps (medium)
- ~700 kbps (high)
- ~1000 kbps (generous)

### TearsOfSteel (1080p)
- ~1000 kbps (low)
- ~2000 kbps (medium)
- ~2700 kbps (high)
- ~4000 kbps (generous)

Exact values may vary per provider based on what rate control options they expose.

## Analysis by Customer Segment

### 1. Streaming / OTT Platforms
**What they care about:** ABR ladder quality, Per-Title optimization, adaptive bitrate support, encoding speed
**Key metrics:** VMAF across full ladder, bitrate efficiency at each rung, how smart is the auto ladder generation
**Relevant providers:** Bitmovin, AWS, Brightcove, Mux

### 2. E-commerce / Product Video
**What they care about:** Single-file quality at minimum size, fast page load, consistent look across products
**Key metrics:** VMAF at low-medium bitrates (500-2000 kbps), file size for equivalent quality, encoding cost per minute
**Relevant providers:** Cloudflare Stream, Mux, Coconut
**Why vidaio wins here:** No ABR overhead, longer GOPs = better quality-per-bit

### 3. E-learning / Course Platforms
**What they care about:** Consistent quality for screen recordings + talking head, storage cost at scale, text legibility
**Key metrics:** VMAF on screen recording content, compression ratio, cost per hour of content
**Relevant providers:** Mux, Cloudflare Stream, api.video
**Why vidaio wins here:** Target quality means consistent results across diverse content

### 4. UGC Platforms
**What they care about:** Handle diverse input quality, encoding speed at scale, cost per upload, storage + CDN cost
**Key metrics:** Quality on noisy/low-quality inputs, encoding throughput, cost per 1000 minutes
**Relevant providers:** Cloudflare Stream, Mux, api.video
**Why vidaio wins here:** Better quality-per-bit means lower storage/bandwidth costs at scale

### 5. Video Archive / Media Libraries
**What they care about:** Maximum compression at guaranteed quality floor, long-term storage cost, format longevity
**Key metrics:** File size at VMAF ≥ 93, compression ratio, codec choice
**Relevant providers:** AWS, Encoding.com
**Why vidaio wins here:** Quality-driven encoding = smallest file at guaranteed quality

### 6. Surveillance / Security
**What they care about:** Acceptable quality at minimum bitrate, retention period cost, compliance
**Key metrics:** VMAF at very low bitrates (200-500 kbps), file size per hour of footage
**Relevant providers:** Not typically cloud API users, but cost comparison still relevant

## Streaming-Focused vs Non-Streaming Comparison

### The Current Landscape

Every existing cloud encoding comparison (including Jan Ozer's comprehensive 2022 per-title reports) evaluates providers through a **streaming lens**: ABR ladder quality, per-title ladder optimization, distribution pattern analysis, HLS/DASH packaging. This makes sense — streaming is the dominant use case, and these providers are built for it.

But this means a **huge category of video encoding is completely unbenchmarked**: single-file, quality-optimized encoding for non-streaming delivery.

### Who Needs Non-Streaming Encoding?

| Use Case | Volume | Why Not Streaming |
|----------|--------|-------------------|
| **E-commerce product video** | Billions of product listings | Progressive download on stable connections. Single file works. Pain point = page load speed + storage cost. |
| **E-learning courses** | Millions of hours (Udemy, Coursera, Teachable) | Learners watch on laptops with stable wifi. Storage cost at scale is the real problem, not bitrate switching. |
| **Video archives** | Petabytes (studios, news, compliance) | Long-term storage. Need guaranteed quality floor at minimum file size. ABR ladders multiply storage cost. |
| **UGC platforms** | Billions of uploads/year | Many short clips served as single files (think product reviews, social clips). ABR overhead not worth it for 30-second videos. |
| **Internal/corporate video** | Large enterprises | Training videos, town halls on corporate networks. Stable bandwidth, single rendition. |

### Why Streaming-Optimized Encoding Hurts These Use Cases

Streaming encoders make tradeoffs that **waste bits** for non-streaming delivery:

1. **Short GOPs (2-4s)** — Required for ABR segment boundaries and fast seeking. But each I-frame costs 10-50x more bits than a P-frame. For a single file with no segment switching, longer GOPs (6-10s) give better quality per bit.

2. **Per-Title ladder optimization** — Computes optimal bitrate *per resolution rung*. Irrelevant if you only need one rendition. The compute cost of ladder optimization is wasted.

3. **Segment packaging overhead** — fmp4/CMAF segments add container overhead and prevent optimal rate control across segment boundaries.

4. **Conservative rate control** — Streaming encoders target stable bitrate per segment for buffer management. Single-file encoding can use more aggressive VBR for better overall quality.

Our Bitmovin vs Vidaio benchmark already shows this: Bitmovin uses 4s GOPs with 19 I-frames/60s (optimized for streaming), Vidaio uses 6.67s GOPs with 9 I-frames/60s (optimized for quality). At matched bitrates, Vidaio scores 1.5-3 VMAF points higher.

### The Market Gap

- **Ozer's reports** compare providers on streaming metrics. No independent benchmark exists for single-file encoding quality.
- **Cloud APIs** expose ABR-focused features (per-title ladders, HLS/DASH output, DRM). Single-file quality encoding is an afterthought.
- **Target-VMAF encoding** ("encode to VMAF 93 at smallest possible size") exists in open-source tools (Av1an, ab-av1) but **zero cloud APIs offer it** (see `research/target_vmaf_market_gap.md`).

### Our Report's Angle

We compare providers on **both** dimensions:

1. **Standard streaming comparison** (fair, apples-to-apples): matched bitrate targets, same codec, RD curves — this is what everyone expects and gives credibility.

2. **Non-streaming quality analysis** (novel, differentiating): single-file encoding efficiency, GOP overhead analysis, quality-per-bit without ABR constraints, cost per hour of stored video at equivalent quality.

This positions the report as both a fair industry comparison *and* an argument for why non-streaming encoding deserves its own category — and its own optimized tooling.



### 1. Executive Summary
- Key finding: which provider gives best quality-per-bit
- Summary table: provider / codec / avg VMAF at matched bitrate

### 2. Methodology
- Input preparation (lossless, preprocessed)
- Encoding settings per provider (document exactly what API calls were made)
- VMAF measurement (full video, libvmaf, no sampling)
- Bitrate verification (ffprobe actual vs provider-reported)

### 3. Results by Video
- Rate-distortion curves per video
- Summary tables: provider / bitrate / file size / compression / VMAF
- GOP analysis and frame type breakdown

### 4. Analysis by Customer Segment
- Which provider wins for each use case
- Cost-adjusted analysis where pricing is available

### 5. Deep Dive: Why Quality Differs
- GOP structure impact (shorter GOPs = more I-frames = wasted bits)
- Rate control accuracy (does encoder hit the target?)
- Encoder implementation (libaom vs SVT-AV1 vs proprietary)
- Multi-pass vs single-pass

### 6. Conclusions and Recommendations

## Known Issues from Current Benchmark

- Bitmovin Per-Title ignores min_bitrate on "easy" content (TOS capped at ~2475k despite 2700k+ target)
- Bitmovin uses shorter GOPs (4s + scene detect) vs Vidaio (6.67s regular) — 2x more I-frames
- Lossless inputs inflate VMAF scores for high-bitrate encodes (TOS vidaio at 99.78)
- Need non-lossless reference or more diverse content to differentiate at high bitrates

## Next Steps

1. Sign up for / get API access to remaining providers
2. Add 3 more input videos (UGC, sports, screen recording)
3. Submit encoding jobs per provider with matched settings
4. Download results, verify actual bitrates
5. Run VMAF on all
6. Generate RD curves and comparison tables
7. Write report
