# Video Encoding for Storage and Quality: A Multi-Provider Benchmark

**Comparing compression efficiency across cloud encoding providers for archival, e-commerce, UGC, and education workloads**

| | |
|------|------|
| **Author** | Nikola Rahman |
| **Commissioned by** | Vidaio |
| **Date** | {{DATE}} |
| **Version** | {{VERSION}} |
| **Data repository** | {{REPO_URL}} |

---

## About This Report

This report was commissioned by Vidaio and produced by Nikola Rahman, an independent video engineering consultant. All methodology, test content, analysis, and conclusions are the author's own.

- All providers were tested using publicly available APIs with their best available quality settings.
- Provider-specific configuration details are documented in the [Methodology](#3-methodology) section.
- The complete raw data and measurement code are available at {{REPO_URL}}.
- Draft results were shared with all tested providers prior to publication for factual accuracy review.

---

## 1. Executive Summary

### The gap

Existing video encoding benchmarks evaluate providers through a streaming lens — adaptive bitrate ladders, segment-based delivery, and startup latency. No benchmark exists for **quality-optimized single-file encoding**: the use case that matters for archival storage, e-commerce product videos, UGC platforms, and online education.

### What we tested

{{N_CLIPS}} video clips across four industry verticals, encoded through {{N_PROVIDERS}} providers using AV1 and H.265, measured on VMAF perceptual quality, file size, and compression efficiency.

### Headline findings

1. **Compression efficiency varies significantly across providers.** At equivalent quality (VMAF 93), file sizes differ by up to {{MAX_SIZE_SPREAD_PCT}}% between the most and least efficient provider.
2. **{{BEST_PROVIDER_VMAF93}} produces the smallest files at VMAF 93**, averaging {{BEST_SIZE_AT_93}} MB across all test clips. The next-closest provider requires {{SECOND_SIZE_AT_93}} MB — a {{SIZE_DIFF_PCT}}% difference.
3. **AV1 delivers {{AV1_H265_ADVANTAGE}}% better compression than H.265** across all providers. {{AV1_WINNER_NOTE}}.
4. **Black-box providers (Mux, Cloudflare) trade configurability for simplicity.** Their single operating points {{BLACKBOX_POSITION_NOTE}}.
5. **Ease of use and compression efficiency present different tradeoffs.** {{EASE_EFFICIENCY_TRADEOFF_NOTE}}.

### Headline findings table

| Provider | Avg VMAF (matched bitrate) | BD-Rate vs. Best | File Size at VMAF 93 | Rank |
|----------|---------------------------|-----------------|----------------------|------|
| AWS MediaConvert | {{MEDIACONVERT_VMAF}} | {{MEDIACONVERT_BDRATE}}% | {{MEDIACONVERT_SIZE}} | {{MEDIACONVERT_RANK}} |
| Bitmovin | {{BITMOVIN_VMAF}} | {{BITMOVIN_BDRATE}}% | {{BITMOVIN_SIZE}} | {{BITMOVIN_RANK}} |
| Brightcove Zencoder | {{ZENCODER_VMAF}} | {{ZENCODER_BDRATE}}% | {{ZENCODER_SIZE}} | {{ZENCODER_RANK}} |
| Cloudflare Stream | {{CLOUDFLARE_VMAF}} | {{CLOUDFLARE_BDRATE}}% | {{CLOUDFLARE_SIZE}} | {{CLOUDFLARE_RANK}} |
| Mux | {{MUX_VMAF}} | {{MUX_BDRATE}}% | {{MUX_SIZE}} | {{MUX_RANK}} |
| Vidaio | {{VIDAIO_VMAF}} | {{VIDAIO_BDRATE}}% | {{VIDAIO_SIZE}} | {{VIDAIO_RANK}} |

> **Figure 1.1 — Aggregate Rate-Distortion Summary**
> {{FIGURE_1_1_AGGREGATE_RD_CURVE}}
> *All providers, averaged across {{N_CLIPS}} clips. Horizontal lines at VMAF 93 (visually transparent) and VMAF 95 (indistinguishable). Black-box providers shown as single points.*

> **Figure 1.2 — Storage Savings at Matched Quality**
> {{FIGURE_1_2_STORAGE_SAVINGS_BAR}}
> *Average file size required to achieve VMAF ≥ 93, by provider. Percentage labels show savings relative to the largest file.*

---

## 2. Why This Benchmark Exists

### The streaming assumption

All major cloud encoding benchmarks — Ozer (2022), MSU (2020, 2022) — evaluate providers through a streaming lens: ABR ladders, segment-based delivery, per-title optimization for adaptive playback. This methodology makes sense for OTT delivery, but it ignores a large and growing category of customers.

### Who needs single-file encoding

| Segment | Use case | Why streaming benchmarks don't apply |
|---------|----------|--------------------------------------|
| **E-commerce** | Product videos as progressive downloads | Millions of short clips; ABR overhead exceeds the video itself |
| **UGC platforms** | Ingest, transcode, store uploaded video | Storage cost is the dominant concern, not adaptive playback |
| **Video archives** | Long-term preservation at minimum cost | Every byte saved compounds over years and petabytes |
| **Online education** | Lecture and tutorial content at scale | Text-heavy content with consistent quality requirements |

### How streaming-optimized encoding differs from single-file encoding

Streaming encoders typically use short GOPs (2-4 seconds) to enable segment-based switching. Each GOP starts with an I-frame — a full-frame image that costs 10-50x more bits than a P-frame. For single-file delivery where segment switching is not needed, these additional I-frames consume bits without a corresponding benefit to the viewer.

> **Figure 2.1 — The Benchmark Landscape**
> {{FIGURE_2_1_BENCHMARK_LANDSCAPE_MATRIX}}
> *Coverage comparison across published benchmarks. This report uniquely covers single-file, quality-optimized encoding.*

> **Figure 2.2 — Why GOPs Matter**
> {{FIGURE_2_2_GOP_DIAGRAM}}
> *Streaming-optimized GOP structure (short, many I-frames) vs. quality-optimized (longer, fewer I-frames). I-frame overhead directly reduces the bit budget available for quality.*

---

## 3. Methodology

### 3.1 Test Content

{{N_CLIPS}} source videos selected to represent the range of content complexity encountered in production:

| Clip | Vertical | Resolution | Duration | SI | TI | Source | License |
|------|----------|------------|----------|----|----|--------|---------|
| {{CLIP_1_NAME}} | {{CLIP_1_VERTICAL}} | {{CLIP_1_RES}} | {{CLIP_1_DUR}} | {{CLIP_1_SI}} | {{CLIP_1_TI}} | {{CLIP_1_SOURCE}} | {{CLIP_1_LICENSE}} |
| {{CLIP_2_NAME}} | {{CLIP_2_VERTICAL}} | {{CLIP_2_RES}} | {{CLIP_2_DUR}} | {{CLIP_2_SI}} | {{CLIP_2_TI}} | {{CLIP_2_SOURCE}} | {{CLIP_2_LICENSE}} |
| ... | ... | ... | ... | ... | ... | ... | ... |

**Selection criteria:** Clips were chosen to cover a diverse range of spatial and temporal complexity across each vertical. Synthetic test sequences (ITU reference clips, Blender demos) were avoided in favor of content representative of real production workloads.

**Input preparation:** All source files were validated and preprocessed to ensure consistent input quality: lossless H.264 (QP 0, no B-frames), no audio tracks, integer-second durations.

> **Figure 3.1 — Test Content Gallery**
> {{FIGURE_3_1_CONTENT_GALLERY}}
> *Representative frame from each test clip, organized by vertical.*

> **Figure 3.2 — Spatial-Temporal Complexity Scatter**
> {{FIGURE_3_2_SI_TI_SCATTER}}
> *Each point is one test clip, color-coded by vertical. The test corpus covers a diverse range of content complexity.*

### 3.2 Providers and Configuration

| Provider | Rate Control | Quality Parameter | Codec Support | Sweep Points per Clip | Black-box? |
|----------|-------------|-------------------|---------------|----------------------|------------|
| AWS MediaConvert | QVBR | QvbrQualityLevel (1-10) | AV1, H.265 | {{MC_SWEEP_N}} | No |
| Bitmovin | CRF | crf (0-51 / 0-63) | AV1, H.265 | {{BITMOVIN_SWEEP_N}} | No |
| Brightcove Zencoder | CRF / Quality | crf (0-51) or quality (1-5) | AV1, H.265 | {{ZC_SWEEP_N}} | No |
| Cloudflare Stream | Automatic | None | H.264 only | 1 | Yes |
| Mux | Automatic | None | Automatic | 1 | Yes |
| Vidaio | Quality-optimized | Preset (basic/medium/hyper) | AV1, H.265 | 3 | Partially |

**Fairness statement:** Each provider was configured to produce the best possible quality for a given file size. For providers with quality controls, multiple encoding passes were performed at different quality levels to map the full rate-distortion curve. For providers without quality controls, the single output represents the provider's best-effort encoding.

**Configurable providers:** CRF/QVBR values were selected to produce data points spanning the range from low bitrate (~200 kbps) to high bitrate (~5,000+ kbps), ensuring sufficient density to fit accurate RD curves.

**Black-box providers:** Mux and Cloudflare Stream produce one output per input with no quality controls. Their single operating point is plotted against other providers' RD curves. See [Section 3.4](#34-handling-black-box-providers) for details.

### 3.3 Quality Measurement

- **VMAF model:** vmaf_v0.6.1 (Netflix default model)
- **Evaluation:** Full-video, frame-by-frame (no temporal sampling)
- **Bitrate:** Measured via ffprobe on the actual output file (not provider-reported labels)
- **Metrics extracted per rendition:**
  - VMAF mean, VMAF minimum, VMAF harmonic mean
  - VMAF 1st percentile, VMAF 5th percentile
  - Per-frame VMAF scores (for consistency analysis)
- **Compression ratio:** Input file size ÷ output file size
- **BD-Rate:** Bjontegaard Delta Rate computed between each provider's RD curve and the best-performing provider as reference, using piecewise cubic interpolation over the overlapping bitrate range

**Why percentiles matter:** A file with VMAF mean 95 but a 1st-percentile of 72 has severe transient quality drops that a viewer will notice. Mean VMAF alone is insufficient for quality assessment.

### 3.4 Handling Black-Box Providers

Mux and Cloudflare Stream do not expose quality controls. This creates an asymmetry:

- **On RD curve charts:** Configurable providers appear as curves. Black-box providers appear as single labeled points (diamond markers).
- **On "file size at VMAF 93" charts:** If the black-box provider's output exceeds VMAF 93, its actual file size is used. If it falls below VMAF 93, it is marked as "did not achieve target" with the actual VMAF annotated.
- **On BD-Rate rankings:** Black-box providers are excluded from BD-Rate computation (which requires multiple points) and ranked separately.
- **Cloudflare codec note:** Cloudflare Stream outputs H.264 only. It appears in cross-codec comparisons with a clear annotation that the codec differs.

**Fairness note:** Black-box simplicity is a feature for many customers. Where ease-of-use may outweigh raw compression efficiency, this is noted in the [Recommendations](#9-recommendations-by-use-case) section.

---

## 4. Results by Codec

### 4.1 AV1 Results

#### 4.1.1 Aggregate AV1 Rate-Distortion

> **Figure 4.1 — Aggregate RD Curves, AV1**
> {{FIGURE_4_1_AV1_AGGREGATE_RD}}
> *All providers, AV1 encoding, averaged across all test clips. Configurable providers shown as curves; black-box providers as single points. Horizontal lines at VMAF 93 and 95.*

| Provider | Avg VMAF (median bitrate) | Avg Bitrate at VMAF 93 | Avg File Size at VMAF 93 | BD-Rate vs. Best | Avg Compression Ratio |
|----------|--------------------------|------------------------|--------------------------|-----------------|----------------------|
| AWS MediaConvert | {{AV1_MC_VMAF}} | {{AV1_MC_BR93}} | {{AV1_MC_FS93}} | {{AV1_MC_BDRATE}}% | {{AV1_MC_CR}} |
| Bitmovin | {{AV1_BITMOVIN_VMAF}} | {{AV1_BITMOVIN_BR93}} | {{AV1_BITMOVIN_FS93}} | {{AV1_BITMOVIN_BDRATE}}% | {{AV1_BITMOVIN_CR}} |
| Brightcove Zencoder | {{AV1_ZC_VMAF}} | {{AV1_ZC_BR93}} | {{AV1_ZC_FS93}} | {{AV1_ZC_BDRATE}}% | {{AV1_ZC_CR}} |
| Cloudflare Stream | — | — | — | — | — |
| Mux | {{AV1_MUX_VMAF}} | — | {{AV1_MUX_FS}} | — | {{AV1_MUX_CR}} |
| Vidaio | {{AV1_VIDAIO_VMAF}} | {{AV1_VIDAIO_BR93}} | {{AV1_VIDAIO_FS93}} | {{AV1_VIDAIO_BDRATE}}% | {{AV1_VIDAIO_CR}} |

> **Figure 4.2 — BD-Rate Summary, AV1**
> {{FIGURE_4_2_AV1_BDRATE_BAR}}
> *Percentage bitrate difference relative to the most efficient provider. Negative = saves bitrate at equivalent quality.*

#### 4.1.2 AV1 Results — E-Commerce

{{ECOM_AV1_NARRATIVE}}

> **Figure 4.3 — RD Curves, AV1, E-Commerce Clips**
> {{FIGURE_4_3_AV1_ECOM_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{ECOM_AV1_DATA_ROWS}} |

#### 4.1.3 AV1 Results — UGC

{{UGC_AV1_NARRATIVE}}

> **Figure 4.4 — RD Curves, AV1, UGC Clips**
> {{FIGURE_4_4_AV1_UGC_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{UGC_AV1_DATA_ROWS}} |

#### 4.1.4 AV1 Results — Archives

{{ARCHIVE_AV1_NARRATIVE}}

> **Figure 4.5 — RD Curves, AV1, Archive Clips**
> {{FIGURE_4_5_AV1_ARCHIVE_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{ARCHIVE_AV1_DATA_ROWS}} |

#### 4.1.5 AV1 Results — Education

{{EDUCATION_AV1_NARRATIVE}}

> **Figure 4.6 — RD Curves, AV1, Education Clips**
> {{FIGURE_4_6_AV1_EDUCATION_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{EDUCATION_AV1_DATA_ROWS}} |

### 4.2 H.265 Results

#### 4.2.1 Aggregate H.265 Rate-Distortion

> **Figure 4.7 — Aggregate RD Curves, H.265**
> {{FIGURE_4_7_H265_AGGREGATE_RD}}

| Provider | Avg VMAF (median bitrate) | Avg Bitrate at VMAF 93 | Avg File Size at VMAF 93 | BD-Rate vs. Best | Avg Compression Ratio |
|----------|--------------------------|------------------------|--------------------------|-----------------|----------------------|
| AWS MediaConvert | {{H265_MC_VMAF}} | {{H265_MC_BR93}} | {{H265_MC_FS93}} | {{H265_MC_BDRATE}}% | {{H265_MC_CR}} |
| Bitmovin | {{H265_BITMOVIN_VMAF}} | {{H265_BITMOVIN_BR93}} | {{H265_BITMOVIN_FS93}} | {{H265_BITMOVIN_BDRATE}}% | {{H265_BITMOVIN_CR}} |
| Brightcove Zencoder | {{H265_ZC_VMAF}} | {{H265_ZC_BR93}} | {{H265_ZC_FS93}} | {{H265_ZC_BDRATE}}% | {{H265_ZC_CR}} |
| Cloudflare Stream | {{H265_CF_VMAF}} | — | {{H265_CF_FS}} | — | {{H265_CF_CR}} |
| Mux | {{H265_MUX_VMAF}} | — | {{H265_MUX_FS}} | — | {{H265_MUX_CR}} |
| Vidaio | {{H265_VIDAIO_VMAF}} | {{H265_VIDAIO_BR93}} | {{H265_VIDAIO_FS93}} | {{H265_VIDAIO_BDRATE}}% | {{H265_VIDAIO_CR}} |

> **Figure 4.8 — BD-Rate Summary, H.265**
> {{FIGURE_4_8_H265_BDRATE_BAR}}

#### 4.2.2 H.265 Results — E-Commerce

{{ECOM_H265_NARRATIVE}}

> **Figure 4.9 — RD Curves, H.265, E-Commerce Clips**
> {{FIGURE_4_9_H265_ECOM_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{ECOM_H265_DATA_ROWS}} |

#### 4.2.3 H.265 Results — UGC

{{UGC_H265_NARRATIVE}}

> **Figure 4.10 — RD Curves, H.265, UGC Clips**
> {{FIGURE_4_10_H265_UGC_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{UGC_H265_DATA_ROWS}} |

#### 4.2.4 H.265 Results — Archives

{{ARCHIVE_H265_NARRATIVE}}

> **Figure 4.11 — RD Curves, H.265, Archive Clips**
> {{FIGURE_4_11_H265_ARCHIVE_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{ARCHIVE_H265_DATA_ROWS}} |

#### 4.2.5 H.265 Results — Education

{{EDUCATION_H265_NARRATIVE}}

> **Figure 4.12 — RD Curves, H.265, Education Clips**
> {{FIGURE_4_12_H265_EDUCATION_RD}}

| Clip | Provider | Bitrate (kbps) | File Size (MB) | VMAF Mean | VMAF Min | VMAF P1 | Compression Ratio |
|------|----------|---------------|----------------|-----------|----------|---------|-------------------|
| {{EDUCATION_H265_DATA_ROWS}} |

### 4.3 AV1 vs. H.265 Comparison

> **Figure 4.13 — Codec Comparison Overlay**
> {{FIGURE_4_13_CODEC_COMPARISON}}
> *AV1 vs. H.265 RD curves overlaid for 3 representative providers. Shows the magnitude of codec-generation improvement and whether it varies by provider.*

> **Figure 4.14 — Codec × Provider Heatmap**
> {{FIGURE_4_14_CODEC_PROVIDER_HEATMAP}}
> *Average VMAF at a reference bitrate. Color intensity indicates compression efficiency. Rows: providers (alphabetical). Columns: AV1, H.265.*

---

## 5. Storage Efficiency Analysis

This section translates rate-distortion data into the metrics that storage-cost buyers care about.

### File size at matched quality

> **Figure 5.1 — File Size at VMAF 93, by Provider**
> {{FIGURE_5_1_FILESIZE_AT_VMAF93}}
> *Average file size required to achieve VMAF ≥ 93 across all clips, using AV1. Percentage labels show savings relative to the largest provider.*

### Storage cost projection

| Scenario: 1,000,000 videos × 60 seconds × 1080p | | |
|---|---|---|
| Provider | Total Storage (TB) | Annual S3 Cost (at $0.023/GB/mo) |
| AWS MediaConvert | {{PROJ_MC_TB}} | {{PROJ_MC_COST}} |
| Bitmovin | {{PROJ_BITMOVIN_TB}} | {{PROJ_BITMOVIN_COST}} |
| Brightcove Zencoder | {{PROJ_ZC_TB}} | {{PROJ_ZC_COST}} |
| Cloudflare Stream | {{PROJ_CF_TB}} | {{PROJ_CF_COST}} |
| Mux | {{PROJ_MUX_TB}} | {{PROJ_MUX_COST}} |
| Vidaio | {{PROJ_VIDAIO_TB}} | {{PROJ_VIDAIO_COST}} |

### Quality floor guarantee

> **Figure 5.2 — Quality Floor: % of Clips Meeting VMAF Thresholds**
> {{FIGURE_5_2_QUALITY_FLOOR}}
> *For each provider at their typical operating point: percentage of clips achieving VMAF ≥ 85, ≥ 90, ≥ 93, ≥ 95.*

### Compression ratio distribution

> **Figure 5.3 — Compression Ratio Distribution**
> {{FIGURE_5_3_COMPRESSION_RATIO_BOXPLOT}}
> *Box plot showing compression ratio spread per provider. Tighter distributions indicate more predictable file sizes.*

---

## 6. Quality Consistency

Mean VMAF hides transient quality drops. A file scoring VMAF 95 overall but dropping to 72 on scene changes will produce visible artifacts. This section examines quality stability.

### VMAF percentile comparison

> **Figure 6.1 — VMAF Percentile Comparison**
> {{FIGURE_6_1_VMAF_PERCENTILES}}
> *For each provider at matched bitrate: VMAF mean, 5th percentile, 1st percentile, and minimum. Providers with smaller gaps between mean and minimum deliver more consistent quality.*

### Per-frame VMAF traces

> **Figure 6.2 — Per-Frame VMAF Trace (Representative Easy Clip)**
> {{FIGURE_6_2_PERFRAME_EASY}}
> *Clip: {{EASY_CLIP_NAME}}. Per-frame VMAF for 3-4 providers overlaid. Shows quality stability on low-complexity content.*

> **Figure 6.3 — Per-Frame VMAF Trace (Representative Hard Clip)**
> {{FIGURE_6_3_PERFRAME_HARD}}
> *Clip: {{HARD_CLIP_NAME}}. Per-frame VMAF for 3-4 providers overlaid. Shows how providers handle difficult content (high motion, scene changes).*

### Quality consistency matrix

> **Figure 6.4 — Quality Consistency Matrix**
> {{FIGURE_6_4_CONSISTENCY_MATRIX}}
> *Grid of mini sparklines. Rows: test clips. Columns: providers. Each cell shows the per-frame VMAF trace at a glance.*

---

## 7. Encoder Behavior Deep Dive

### 7.1 GOP Structure Analysis

Streaming-optimized encoders typically use short GOPs (2-4 seconds) with frequent I-frames to enable segment-based adaptive switching. For single-file delivery, these additional I-frames are not required.

> **Figure 7.1 — I-Frame Count per Minute**
> {{FIGURE_7_1_IFRAME_COUNT}}
> *Average I-frames per minute of encoded video, by provider. Fewer I-frames = more bits available for quality.*

> **Figure 7.2 — Bit Allocation: I-Frames vs. P/B-Frames**
> {{FIGURE_7_2_BIT_ALLOCATION}}
> *For a representative clip: percentage of total bits allocated to I-frames vs. inter-frames. Streaming-optimized encoders spend a larger fraction on I-frames.*

### 7.2 Rate Control Accuracy

For providers that accept quality targets: how well does the encoder hit the requested quality level?

> **Figure 7.3 — Requested vs. Actual Quality**
> {{FIGURE_7_3_RATE_CONTROL_ACCURACY}}
> *Scatter plot of requested CRF/QVBR level vs. actual output VMAF. Points close to the trend line indicate predictable quality control.*

---

## 8. Ease of Use

Compression efficiency matters, but so does how much effort it takes to achieve it. This section evaluates each provider on what it takes to get optimal quality-per-bit results.

### Configuration complexity

| Provider | Steps to Optimal Quality | Quality Control | Codec Selection | Expertise Required |
|----------|--------------------------|----------------|-----------------|-------------------|
| AWS MediaConvert | Configure QVBR level (1-10), fine-tune, codec settings, IAM role | Manual QVBR tuning | Full control | High |
| Bitmovin | Configure CRF, preset, Per-Title params, codec config | Manual CRF tuning or Per-Title | Full control | High |
| Brightcove Zencoder | Set quality (1-5) or CRF, speed, codec | Manual tuning | Full control | Medium |
| Cloudflare Stream | Upload video | Fully automatic | No control (H.264 only) | None |
| Mux | Upload video | Fully automatic | No control | None |
| Vidaio | Select preset (basic/medium/hyper) | Automatic | Choose AV1 or H.265 | Low |

### What "best compression for given quality" requires

For each provider, the practical steps needed to achieve the best possible file size at a target quality (e.g., VMAF 93):

| Provider | Process | Iteration Required? |
|----------|---------|-------------------|
| **Vidaio** | {{EASE_VIDAIO}} | {{EASE_VIDAIO_ITER}} |
| **Bitmovin** | {{EASE_BITMOVIN}} | {{EASE_BITMOVIN_ITER}} |
| **AWS MediaConvert** | {{EASE_MC}} | {{EASE_MC_ITER}} |
| **Brightcove Zencoder** | {{EASE_ZC}} | {{EASE_ZC_ITER}} |
| **Mux** | {{EASE_MUX}} | {{EASE_MUX_ITER}} |
| **Cloudflare Stream** | {{EASE_CF}} | {{EASE_CF_ITER}} |

### API integration effort

| Provider | SDK | Auth Setup | Job Submission | Result Retrieval | Documentation Quality |
|----------|-----|-----------|---------------|-----------------|----------------------|
| AWS MediaConvert | boto3 | IAM role + endpoint discovery | Moderate (job JSON with nested settings) | Poll + S3 download | Extensive |
| Bitmovin | bitmovin-api-sdk (Python) | API key | Complex (input → encoding → stream → codec config → muxing → start) | Poll + S3 download | Extensive |
| Brightcove Zencoder | zencoder (Python) | API key | Simple (POST with input + outputs) | Poll + download URL | Adequate |
| Cloudflare Stream | cloudflare (Python) | API token | Simple (POST with URL) | Webhook or poll | Good |
| Mux | mux-python | Token ID + secret | Simple (POST asset with URL) | Webhook or poll | Good |
| Vidaio | {{API_VIDAIO_SDK}} | {{API_VIDAIO_AUTH}} | {{API_VIDAIO_SUBMIT}} | {{API_VIDAIO_RETRIEVE}} | {{API_VIDAIO_DOCS}} |

> **Figure 8.1 — Ease of Use vs. Compression Efficiency**
> {{FIGURE_8_1_EASE_VS_EFFICIENCY}}
> *Scatter plot. X-axis: compression efficiency (BD-Rate or file size at VMAF 93). Y-axis: ease-of-use score (qualitative, based on configuration complexity). Providers in the top-left quadrant offer both simplicity and efficiency.*

---

## 9. Pricing Analysis

Encoding cost is only part of the picture. The total cost of ownership includes encoding fees, storage, and delivery. This section compares the economics using public list pricing.

### Encoding cost per minute

| Provider | Pricing Model | Cost per Minute (1080p) | Cost per Minute (4K) | Notes |
|----------|--------------|------------------------|---------------------|-------|
| AWS MediaConvert | Per-minute, tier-dependent (Basic vs. Professional) | {{PRICE_MC_1080}} | {{PRICE_MC_4K}} | AV1 requires Professional tier |
| Bitmovin | Per-minute, codec-dependent | {{PRICE_BITMOVIN_1080}} | {{PRICE_BITMOVIN_4K}} | {{PRICE_BITMOVIN_NOTES}} |
| Brightcove Zencoder | Per-minute, output-based | {{PRICE_ZC_1080}} | {{PRICE_ZC_4K}} | {{PRICE_ZC_NOTES}} |
| Cloudflare Stream | $5/1K min stored, $1/1K min delivered | {{PRICE_CF_1080}} | {{PRICE_CF_4K}} | No separate encoding fee |
| Mux | Per-minute ingested + stored + delivered | {{PRICE_MUX_1080}} | {{PRICE_MUX_4K}} | Encoding bundled with storage |
| Vidaio | {{PRICE_VIDAIO_MODEL}} | {{PRICE_VIDAIO_1080}} | {{PRICE_VIDAIO_4K}} | {{PRICE_VIDAIO_NOTES}} |

### Total cost of ownership: encoding + storage

The real question: when you factor in the smaller file sizes from better compression, does the encoding cost pay for itself in storage savings?

| Scenario: {{TCO_SCENARIO_DESCRIPTION}} | | | | |
|---|---|---|---|---|
| Provider | Encoding Cost | Annual Storage Cost | **Total Annual Cost** | **Savings vs. Most Expensive** |
| AWS MediaConvert | {{TCO_MC_ENC}} | {{TCO_MC_STOR}} | **{{TCO_MC_TOTAL}}** | {{TCO_MC_SAVINGS}} |
| Bitmovin | {{TCO_BITMOVIN_ENC}} | {{TCO_BITMOVIN_STOR}} | **{{TCO_BITMOVIN_TOTAL}}** | {{TCO_BITMOVIN_SAVINGS}} |
| Brightcove Zencoder | {{TCO_ZC_ENC}} | {{TCO_ZC_STOR}} | **{{TCO_ZC_TOTAL}}** | {{TCO_ZC_SAVINGS}} |
| Cloudflare Stream | {{TCO_CF_ENC}} | {{TCO_CF_STOR}} | **{{TCO_CF_TOTAL}}** | {{TCO_CF_SAVINGS}} |
| Mux | {{TCO_MUX_ENC}} | {{TCO_MUX_STOR}} | **{{TCO_MUX_TOTAL}}** | {{TCO_MUX_SAVINGS}} |
| Vidaio | {{TCO_VIDAIO_ENC}} | {{TCO_VIDAIO_STOR}} | **{{TCO_VIDAIO_TOTAL}}** | {{TCO_VIDAIO_SAVINGS}} |

> **Figure 9.1 — Total Cost of Ownership Breakdown**
> {{FIGURE_9_1_TCO_STACKED_BAR}}
> *Stacked bar chart: encoding cost (bottom) + annual storage cost (top) per provider. Shows where better compression offsets higher encoding fees.*

> **Figure 9.2 — Break-Even Analysis: Compression Savings vs. Encoding Cost**
> {{FIGURE_9_2_BREAKEVEN}}
> *For each provider pair: how many months of storage does it take for the compression-efficient provider's savings to offset any encoding cost premium?*

### Cost per quality point

| Provider | Cost per VMAF Point (at VMAF 93) | Cost per GB Saved (vs. baseline) |
|----------|----------------------------------|----------------------------------|
| AWS MediaConvert | {{CPQ_MC}} | {{CPGB_MC}} |
| Bitmovin | {{CPQ_BITMOVIN}} | {{CPGB_BITMOVIN}} |
| Brightcove Zencoder | {{CPQ_ZC}} | {{CPGB_ZC}} |
| Cloudflare Stream | {{CPQ_CF}} | {{CPGB_CF}} |
| Mux | {{CPQ_MUX}} | {{CPGB_MUX}} |
| Vidaio | {{CPQ_VIDAIO}} | {{CPGB_VIDAIO}} |

**Pricing caveat:** All costs use public list pricing as of {{PRICE_DATE}}. Enterprise/volume pricing varies significantly. This analysis is directional, not a substitute for provider quotes at your specific volume.

---

## 10. Encoding Speed

Encoding time is a secondary metric for archival workloads (typically batch-processed), but important for operational planning.

> **Figure 10.1 — Encoding Speed Comparison**
> {{FIGURE_10_1_ENCODING_SPEED}}
> *Average encoding time as a multiple of real-time. Values < 1x indicate faster-than-realtime encoding.*

| Provider | Avg Encode Time (s) | Avg Speed (× real-time) | Min | Max |
|----------|--------------------|-----------------------|-----|-----|
| AWS MediaConvert | {{SPEED_MC_AVG}} | {{SPEED_MC_RT}} | {{SPEED_MC_MIN}} | {{SPEED_MC_MAX}} |
| Bitmovin | {{SPEED_BITMOVIN_AVG}} | {{SPEED_BITMOVIN_RT}} | {{SPEED_BITMOVIN_MIN}} | {{SPEED_BITMOVIN_MAX}} |
| Brightcove Zencoder | {{SPEED_ZC_AVG}} | {{SPEED_ZC_RT}} | {{SPEED_ZC_MIN}} | {{SPEED_ZC_MAX}} |
| Cloudflare Stream | {{SPEED_CF_AVG}} | {{SPEED_CF_RT}} | {{SPEED_CF_MIN}} | {{SPEED_CF_MAX}} |
| Mux | {{SPEED_MUX_AVG}} | {{SPEED_MUX_RT}} | {{SPEED_MUX_MIN}} | {{SPEED_MUX_MAX}} |
| Vidaio | {{SPEED_VIDAIO_AVG}} | {{SPEED_VIDAIO_RT}} | {{SPEED_VIDAIO_MIN}} | {{SPEED_VIDAIO_MAX}} |

**Caveat:** Encoding time varies with server load, region, and pricing tier. These measurements are indicative, not guaranteed.

---

## 11. Recommendations by Use Case

### 11.1 E-Commerce Platforms

**What they need:** The smallest possible product video at VMAF 93+ quality. Fine detail (fabric texture, product labels, text overlays) must remain sharp. Storage cost scales with millions of SKUs.

**Recommendation:** {{ECOM_RECOMMENDATION}}

**Projected savings:** {{ECOM_PROJECTED_SAVINGS}}

### 11.2 UGC Platforms

**What they need:** Handle diverse, often noisy input quality. Minimize storage at acceptable quality. Pipeline simplicity matters — millions of uploads per day with minimal manual intervention.

**Recommendation:** {{UGC_RECOMMENDATION}}

**Note on black-box providers:** {{UGC_BLACKBOX_NOTE}}

### 11.3 Video Archives & Media Libraries

**What they need:** Guaranteed quality floor at minimum file size. Long-term storage where every byte saved compounds over years and petabytes. Format longevity matters.

**Recommendation:** {{ARCHIVE_RECOMMENDATION}}

**Quality floor analysis:** {{ARCHIVE_QUALITY_FLOOR}}

### 11.4 Online Education

**What they need:** Sharp text, code, and diagrams. Consistent quality across mixed content (slides + camera). Cost-effective hosting at millions of hours of content.

**Recommendation:** {{EDUCATION_RECOMMENDATION}}

### Use case recommendation matrix

| Use Case | Best for Quality | Best for Simplicity | Best for Cost |
|----------|-----------------|-------------------|--------------|
| E-commerce | {{ECOM_BEST_QUALITY}} | {{ECOM_BEST_SIMPLE}} | {{ECOM_BEST_COST}} |
| UGC | {{UGC_BEST_QUALITY}} | {{UGC_BEST_SIMPLE}} | {{UGC_BEST_COST}} |
| Archives | {{ARCHIVE_BEST_QUALITY}} | {{ARCHIVE_BEST_SIMPLE}} | {{ARCHIVE_BEST_COST}} |
| Education | {{EDU_BEST_QUALITY}} | {{EDU_BEST_SIMPLE}} | {{EDU_BEST_COST}} |

---

## 12. Limitations and Future Work

### Limitations

1. **Sample size.** {{N_CLIPS}} clips is representative but not exhaustive. Results may vary on content types not tested (e.g., sports, gaming, medical imaging).
2. **Provider evolution.** Cloud encoders are updated frequently. These results reflect provider capabilities as of {{TEST_DATE}}.
3. **Pricing not fully compared.** Encoding, storage, and delivery costs vary by volume, contract, and region. Storage projections use public list prices and do not account for negotiated enterprise rates.
4. **VMAF limitations on UGC.** Research (BVI-UGC 2024) shows VMAF correlates less well with subjective quality on noisy, low-quality UGC content (SROCC < 0.6). Results on UGC clips should be interpreted with this caveat.
5. **Black-box provider snapshots.** Mux and Cloudflare may change their encoding pipelines at any time. The single data points in this report are snapshots, not permanent characterizations.
6. **No subjective evaluation.** This benchmark uses objective metrics only. A subjective study (MOS scores) would provide additional validation.
7. **Encoding time variability.** Cloud encoding speed depends on server load and is not deterministic.

### Future work

- Expand to 4K test content
- Add subjective quality evaluation (MOS study)
- Test VP9 and H.264 as additional codec baselines
- Re-run annually as providers update their encoders
- Include cost-per-quality-point analysis with actual invoiced costs
- Compute convex hull baseline via brute-force ffmpeg encoding

---

## 13. Conclusions

{{CONCLUSION_HEADLINE}}

{{CONCLUSION_EXPLANATION}}

{{CONCLUSION_IMPLICATION}}

---

## Appendices

### Appendix A: Per-Clip Rate-Distortion Curves

One RD chart per test clip, showing all providers. This is the full evidence base — every aggregate claim can be verified by examining individual clips.

{{APPENDIX_A_PER_CLIP_RD_CURVES}}

### Appendix B: Per-Clip Data Tables

Complete data for every clip × provider × rendition combination.

| Clip | Provider | Codec | Preset/CRF | Bitrate (kbps) | File Size (bytes) | VMAF Mean | VMAF Min | VMAF P1 | VMAF P5 | Compression Ratio | Encoding Time (s) |
|------|----------|-------|-----------|---------------|-------------------|-----------|----------|---------|---------|-------------------|--------------------|
| {{APPENDIX_B_DATA_ROWS}} |

### Appendix C: Exact Encoding Configuration

Exact API calls and SDK invocations used for each provider.

#### Bitmovin
```
{{APPENDIX_C_BITMOVIN_CONFIG}}
```

#### AWS MediaConvert
```
{{APPENDIX_C_MEDIACONVERT_CONFIG}}
```

#### Brightcove Zencoder
```
{{APPENDIX_C_ZENCODER_CONFIG}}
```

#### Mux
```
{{APPENDIX_C_MUX_CONFIG}}
```

#### Cloudflare Stream
```
{{APPENDIX_C_CLOUDFLARE_CONFIG}}
```

#### Vidaio
```
{{APPENDIX_C_VIDAIO_CONFIG}}
```

### Appendix D: BD-Rate Computation Methodology

**Definition:** Bjontegaard Delta Rate (BD-Rate) measures the average percentage difference in bitrate between two rate-distortion curves at equivalent quality levels (Bjontegaard, 2001).

**Curve fitting:** Piecewise cubic Hermite interpolation (PCHIP) over the overlapping bitrate range of both curves.

**Integration range:** Limited to the bitrate range where both providers have data points, to avoid extrapolation artifacts.

**Edge cases:** Black-box providers with a single data point are excluded from BD-Rate computation.

{{APPENDIX_D_BDRATE_DETAILS}}

### Appendix E: Test Content Source Details

| Clip | SHA-256 | Source URL | License | Resolution | Frame Count | Pixel Format |
|------|---------|-----------|---------|------------|-------------|--------------|
| {{APPENDIX_E_CONTENT_ROWS}} |

### Appendix F: Glossary

| Term | Definition |
|------|-----------|
| **VMAF** | Video Multimethod Assessment Fusion. A perceptual video quality metric developed by Netflix. Scale 0-100, where higher is better. |
| **BD-Rate** | Bjontegaard Delta Rate. Measures the average bitrate difference between two RD curves at equivalent quality. Negative values indicate bitrate savings. |
| **CRF** | Constant Rate Factor. A quality-target rate control mode where the encoder adjusts bitrate to maintain a target quality. Lower CRF = higher quality. |
| **QVBR** | Quality-Defined Variable Bitrate. AWS MediaConvert's quality-target mode. Scale 1-10. |
| **GOP** | Group of Pictures. The sequence of frames between I-frames. Longer GOPs are more efficient but less suitable for seeking/segmenting. |
| **I-frame** | Intra-coded frame. A complete image that does not reference other frames. Expensive in bits but required for random access. |
| **P-frame** | Predicted frame. References previous frames to achieve higher compression. |
| **B-frame** | Bidirectionally predicted frame. References both previous and future frames for maximum compression. |
| **RD curve** | Rate-Distortion curve. Plots quality (VMAF) against bitrate. A curve closer to the top-left is more efficient. |
| **Per-Title** | Content-adaptive encoding that analyzes source complexity to optimize the bitrate ladder per video. |
| **SI** | Spatial Information. Measures the spatial complexity (detail) of a video frame. Higher SI = more detail. |
| **TI** | Temporal Information. Measures the temporal complexity (motion) between frames. Higher TI = more motion. |
