# Jan Ozer — Encoding Comparison Methodology Reference

## Who is Jan Ozer?
Leading independent expert on video encoding. Contributing editor to Streaming Media Magazine. Runs [Streaming Learning Center](https://streaminglearningcenter.com/about-jan-ozer). Has tested encoding quality across cloud providers, hardware transcoders, and codecs for 10+ years.

## His Most Comprehensive Comparison: Per-Title Quality & OPEX Reports (Aug 2022)

### Providers Tested
AWS Elemental MediaConvert, Bitmovin, Brightcove/Zencoder, Microsoft Azure Media Services, Tencent

### Test Content
- **23 test files**, 1-8 minutes each
- **4 genres**: entertainment, sports, animation, office/screen
- 1080p source material

### Codecs
- H.264 (High profile, 8-bit)
- HEVC (8-bit SDR)
- No AV1 in this report

### Quality Metrics (3 dimensions of VMAF)
| Metric | Purpose |
|--------|---------|
| **Overall VMAF** | Harmonic mean across all frames — general quality |
| **99th Percentile VMAF** | Quality consistency — what % of frames meet threshold |
| **Low-Frame VMAF** | Transient quality drops — worst-case viewer experience |

Rationale: "A file with an overall VMAF of 95 but many transient quality issues" differs significantly from one with fewer drops.

### Distribution Patterns (3 scenarios)
| Pattern | Description |
|---------|-------------|
| **Top-heavy** | Most viewers retrieve higher bitrate rungs |
| **Mobile** | Viewers concentrate on middle rungs |
| **IPTV** | Viewers watch only top two rungs |

Same encoding can score differently depending on which rungs viewers consume.

### Two Types of Tests
1. **Static encoding**: Identical ladder params across all services → isolates pure encoder quality
2. **Per-title encoding**: Each service uses its own ladder optimization → tests ladder + encoder combined

### Baseline: Convex Hull Method
For each of the 23 clips, brute-force encode at multiple resolutions/bitrates using FFmpeg + x264, measure VMAF, identify best resolution per bitrate. This creates a theoretical "perfect" ladder as the gold standard.

### Cost Analysis
Computed 3 cost dimensions per distribution pattern:
- Encoding cost
- Storage cost
- Streaming/delivery cost

### Key Findings
- Quality varied by up to **9.28 VMAF points** between best and worst providers
- Cost varied by up to **64%** for HEVC
- Brightcove and Bitmovin outperformed AWS and Azure
- Tencent beat AWS and Azure especially for HEVC
- AWS and Azure had "overly conservative ladders" limiting quality at lower bitrates

Source: https://streaminglearningcenter.com/encoding/slc-releases-cloud-based-hevc-and-h-264-per-title-quality-and-opex-reports.html

## Key Methodological Principles

### "There are no codec comparisons, only codec implementation comparisons"
- AV1 quality varies hugely between SVT-AV1, libaom, Tencent's encoder, hardware encoders
- MSU found Tencent's HEVC was 57% more efficient than x265
- "Unless the study's testing schema and codec selection aligns perfectly with yours, the results aren't likely to accurately predict actual savings"
- Organizations must test with their own content and distribution patterns

Source: https://streaminglearningcenter.com/codecs/there-are-no-codec-comparisons-there-are-only-codec-implementation-comparisons.html

### VMAF Targets
- **Top rung of encoding ladder**: VMAF 93-95
- **93**: "video service operator would be confident of optimally serving vast majority of audience with content either indistinguishable from original or with noticeable but not annoying distortion"
- **95**: "video signal is on average subjectively indistinguishable from the original"
- Above 95: diminishing returns

Source: https://streaminglearningcenter.com/encoding/optimal_encoding_ladder_vmaf.html

### Hardware Transcoder Comparison Method
1. Identify the most critical quality-related options for your application
2. Test across the spectrum from high quality/low throughput to low quality/high throughput
3. Compute cost per stream and watts per stream
4. Choose "operating point" for optimum quality/throughput blend
5. "Trust but verify" — don't rely on manufacturer claims

Source: https://streaminglearningcenter.com/learning/how-to-compare-hardware-transcoders.html

### Fairness Practices
- All services received reports pre-publication for verification
- Static and per-title tests separated to avoid conflating encoder quality with ladder optimization
- Multiple runs at different times of day (5-6 runs, averaged final 3)

## Earlier Work

### Buyer's Guide to Cloud Encoders (2014)
- Tested: Encoding.com, Elemental, Zencoder, Amazon
- Found minimal quality differences since most used x264
- Focused on speed, cost, features
- Amazon performed poorly on speed

Source: https://www.streamingmedia.com/Articles/Editorial/Featured-Articles/A-Buyers-Guide-to-Cloud-Encoders-95543.aspx

### Per-Title Encoding Buyer's Guide (2018)
- Tested 11 different per-title technologies
- Including Bitmovin, Mux, Elemental, Capped-CRF

Source: https://go.bitmovin.com/en/choosing-per-title-encoding-technology

### Cloud Encoding Pricing Comparison
- Compared: Amazon Elastic Transcoder, Azure, Bitmovin, Encoding.com, Hybrik, Telestream, Zencoder
- Based on 1-hour project, 10 layers, 2 formats (DASH + HLS)
- Hybrik was least expensive option

Source: https://streaminglearningcenter.com/encoding/cloud-encoding-pricing-comparison-reveals-dramatic-cost-differences-are-you-overpaying.html

## Gaps in Ozer's Work (Opportunities for Our Report)

1. **No AV1 cloud encoding comparison** — his per-title reports cover H.264 and HEVC only
2. **No target-VMAF comparison** — all work is streaming/ABR-focused
3. **No non-streaming use cases** — e-commerce, e-learning, archive, UGC single-file encoding
4. **No Vidaio coverage**

## Recommendations for Our Benchmark (Inspired by Ozer)

### What We Should Adopt
- [x] VMAF as primary metric (already doing this)
- [ ] Add 99th percentile and low-frame VMAF to catch quality inconsistency
- [ ] More test content — at least 4 genres (entertainment, sports, animation, office/screen)
- [ ] Convex hull baseline for each clip (brute-force ffmpeg encoding at multiple CRF/bitrate/resolution combos)
- [ ] Static encoding comparison (same bitrate targets) — already doing this
- [ ] Cost analysis per provider
- [ ] Pre-publication provider review

### What We Can Skip (Different Focus)
- Distribution pattern analysis (relevant for ABR streaming, not for our single-file comparison)
- Per-title ladder comparison (we're comparing single-rendition quality, not ladder optimization)
- Multiple resolution per bitrate tests (unless we expand scope)

### What We Add Beyond Ozer
- AV1 codec (first cloud AV1 comparison)
- Target-VMAF encoding (unique to Vidaio)
- Non-streaming use cases (e-commerce, e-learning, archive)
- GOP and frame-type analysis
- Bitrate accuracy analysis (does encoder respect targets?)
