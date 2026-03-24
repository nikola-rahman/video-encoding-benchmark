# Target VMAF Encoding — Market Gap Research

## What is Target VMAF Encoding?

Instead of guessing a CRF value, you set a desired VMAF score (e.g. 93) and the encoder automatically finds the CRF that achieves it, per scene. This produces the smallest possible file at a guaranteed perceptual quality level.

## Current State

### Open-source tools that implement it
- **Av1an** (8k+ GitHub stars) — `--vmaf_target 93`, per-scene CRF search. Most popular.
- **ab-av1** — `--min-vmaf 93`, binary search over CRF values using ffmpeg + svt-av1 + vmaf.
- **Auto-Target-Encoder** — ML model (RandomForest) predicts CRF for target VMAF/SSIMULACRA2.

### Who uses VMAF in production (custom-built, not target-VMAF-as-a-service)
- **Netflix** — invented VMAF, uses per-shot quality optimization internally.
- **Vimeo** — Thomas Daede integrated VMAF inline during encoding to target consistent quality across resolutions. (https://medium.com/vimeo-engineering-blog/vmaf-ftw-67c154424c0c)
- **Twitter/X** — uses VMAF percentiles to optimize encoding ladder, focuses on worst-frame quality. (https://blog.x.com/engineering/en_us/topics/infrastructure/2020/introducing-vmaf-percentiles-for-video-quality-measurements)

### Cloud APIs that exist today
- Bitmovin, AWS MediaConvert, Mux, Cloudflare Stream, api.video, Coconut, Transloadit, Qencode
- All optimized for **streaming** (ABR ladders, HLS/DASH)
- **None** offer target-VMAF encoding as a feature

## The Gap

**Demand exists** — open-source tools have thousands of stars, active development, feature requests.
**No cloud API offers it** — zero hosted services for target-VMAF encoding.
**Companies that need it build their own** — Netflix, Vimeo, Twitter all built custom pipelines.
**Smaller companies/creators can't** — they either use CLI tools or settle for CRF guessing.

## Market Size

- Global video transcoding market: **$3-7B in 2024-2025**, growing at **11-19% CAGR**
- Video processing platform market: projected to hit **$29.36B by 2033**
- Major players: AWS, Google Cloud, Microsoft Azure, Bitmovin, Brightcove, Encoding.com, Mux

Sources:
- https://www.coherentmarketinsights.com/market-insight/video-transcoding-market-3125
- https://www.globenewswire.com/news-release/2026/01/08/3215197/0/en/Video-Processing-Platform-Market-to-Hit-USD-29-36-Billion-by-2033

## Who Pays for Encoding APIs Today

- **Broadcasters/Media** — BBC, Globo, NY Times use Bitmovin
- **Sports** — OneFootball (live encoding)
- **OTT platforms** — smaller streaming services that can't build their own pipeline
- **E-commerce** — product videos where quality drives conversions
- **E-learning** — platforms hosting millions of hours of course content
- **UGC platforms** — apps handling user uploads at scale

Source: https://bitmovin.com/customer-showcase/

## Potential Paying Customers for Target-VMAF Service

### 1. E-commerce / Product Video Platforms
- Want consistent quality at minimum file size
- Storage and bandwidth are direct costs
- Don't need ABR streaming — just "encode this product video to look good at smallest size"

### 2. E-learning Platforms
- Millions of hours of course content
- Consistent quality matters, streaming ladders don't
- Storage costs are a real pain point (e.g. VdoCipher, Teachable, Thinkific)

### 3. Video Archives / Media Libraries
- Studios, news orgs archiving footage
- Want guaranteed quality floor with minimum storage
- Long-term storage costs compound

### 4. UGC Platforms
- Mux, api.video, Cloudflare Stream customers
- api.video charges $55/1,000 minutes encoded
- If target-VMAF produces 20-30% smaller files at same quality, that's real savings on storage + delivery at scale

### 5. Surveillance / Security
- Retain footage for compliance
- Lower file size at acceptable quality = direct cost savings
- Don't need streaming features

## Pricing Reference Points

- **Cloudflare Stream**: encoding free, storage $5/1,000 min, delivery $1/1,000 min
- **api.video**: $55/1,000 minutes encoded + storage + delivery
- **Bitmovin**: pay-per-output-minute, SD=1x, HD=2x, 4K=4x, 8K=120x
- **Mux**: usage-based per second, no round-ups

Sources:
- https://vocal.email/blog/api-video-vs-cloudflare-stream-pricing-comparison
- https://bitmovin.com/encoding-service/vod-encoding-pricing/
- https://foliovision.com/2021/09/video-encoding-prices-cost

## Why It Doesn't Exist Yet (Hypotheses — Unverified)

- Target-VMAF requires multiple encode attempts per video (3-5x cost)
- CRF works "well enough" for most users
- Biggest customers (Netflix, Vimeo) built their own
- Open-source tools serve hobbyist demand
- The intersection of "needs target-VMAF" AND "can't run ffmpeg locally" AND "will pay" may be small

## Key Technical Insight from Benchmark

Our Bitmovin vs Vidaio benchmark revealed:
- Bitmovin Per-Title uses shorter GOPs (4s, 19 I-frames/60s) optimized for streaming
- Vidaio uses longer GOPs (6.67s, 9 I-frames/60s) optimized for quality
- At same bitrate, vidaio scores ~1.5-3 VMAF points higher
- Per-Title ignores min_bitrate constraints when it decides content doesn't need it
- Streaming-optimized encoding trades quality for seekability/error recovery

This suggests a target-VMAF service could offer meaningfully better quality-per-bit than streaming-focused encoders for non-streaming use cases.

## VMAF Target Recommendations

- Premium content: VMAF 93-95
- UGC / social media: VMAF 84-92
- YouTube/Facebook produce at: VMAF 84-92
- Above 95: diminishing returns, wasting bandwidth

Sources:
- https://ottverse.com/top-rung-of-encoding-bitrate-ladder-abr-video-streaming/
- https://streaminglearningcenter.com/encoding/optimal_encoding_ladder_vmaf.html
