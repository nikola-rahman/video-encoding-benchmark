# Non-Streaming Video Encoding Benchmarks — Industry Research

## Summary

Almost no independent benchmarks exist for non-streaming video encoding quality. The streaming/OTT industry has extensive comparisons (Jan Ozer, MSU, vendor reports), but the much larger market of single-file video encoding is essentially unbenchmarked.

## What Exists

### MSU Cloud Video Transcoding Benchmarks (Most Relevant)

The only independent cloud encoding quality benchmarks:

**MSU 2020 Cloud Benchmark**
- Providers: Alibaba, AWS MediaConvert, Coconut, Kingsoft Cloud, Qencode, Tencent, Zencoder, FFmpeg
- Method: 15 FullHD videos, H.264/HEVC, multiple bitrates, 480p/720p/1080p
- Metrics: SSIM, PSNR, VMAF
- Key finding: 100% file size difference and 700% cost difference for same quality
- Winners: Tencent, Kingsoft Cloud, Coconut (best cost/quality)
- Source: https://www.compression.ru/video/codec_comparison/cloud_2020/

**MSU 2022 Cloud Benchmark**
- Added: Bitmovin, Azure (expanded set)
- Method: 28+ objective metrics, 10,800+ crowdsourcing participants, 529,171 pairwise assessments
- H.264 leaders: Alibaba and Tencent
- HEVC leader: Tencent
- AV1 leader: Tencent
- Source: https://www.compression.ru/video/codec_comparison/2022/cloud_report.html

**MSU 2023-2024**: FullHD + 4K 10-bit reports ongoing at https://videoprocessing.ai/benchmarks/

Note: MSU benchmarks still use streaming-style methodology (bitrate ladders, multi-resolution). Not focused on single-file quality optimization.

### Video Archives / Preservation (Well Benchmarked)

The only non-streaming domain with thorough comparison work:

**FADGI (Federal Agencies Digital Guidelines Initiative)**
- Compared: AVI, MOV, Matroska, MXF wrappers with uncompressed, lossless JPEG 2000, FFV1, MPEG-2
- 4-star rating system for digitization quality
- Outcome: MXF AS-07 adopted by Library of Congress
- Source: https://www.digitizationguidelines.gov/guidelines/video_reformatting_compare.html

**IASA TC-06** (International Association of Sound and Audiovisual Archives)
- International standard for video preservation
- Recommends FFV1 + Matroska as primary digital target format
- Alternative: MXF + lossless JPEG 2000
- Source: https://www.iasa-web.org/tc06/guidelines-preservation-video-recordings

**Library of Congress** adopted FFV1/Matroska as preferred format in December 2023
- Source: https://blogs.loc.gov/thesignal/2023/12/embracing-ffv1-matroska-container-preferred/

**Key archive findings**: FFV1 wins on speed + compression ratio for lossless. JPEG 2000/MXF has interop issues. But this is all **lossless** — lossy archival encoding (for access copies) is not benchmarked.

### Surveillance / CCTV (Vendor-Specific)

**IPVM** — dominant surveillance testing org:
- H.265 vs H.264 camera tests (Samsung, Vivotek, Hikvision)
- Found H.265 processing 50-300% greater than H.264
- Source: https://ipvm.com/reports/h265-camera-test

**Benchmark Magazine** (UK):
- Axis Zipstream vs Hanwha WiseStream dynamic encoding
- Zipstream: 25-47% bitrate reduction; WiseStream: 17-65%
- Both degrade in rain (5-15% savings only)
- Source: https://benchmarkmagazine.com/cctv-test-dynamic-video-encoding/

**ONVIF** — conformance testing for IP surveillance interoperability
- Source: https://www.onvif.org/profiles/

### Social Media / UGC (Academic Research)

**YouTube UGC Dataset** (Google, 2019)
- 1,500 clips from YouTube for compression research
- Source: https://arxiv.org/abs/1904.06457

**BVI-UGC** (University of Bristol, 2024)
- 60 reference videos, 1,080 test sequences, 3,500+ human participants
- Key finding: ALL existing quality metrics performed poorly (SROCC < 0.6) at predicting UGC perceived quality
- Source: https://arxiv.org/abs/2408.07171

**Meta Engineering disclosures:**
- Instagram: Replaced basic ABR with repackaged progressive frames, 94% compute reduction
  Source: https://engineering.fb.com/2022/11/04/video-engineering/instagram-video-processing-encoding-reduction/
- AV1 for Reels: 65% lower bitrate than AVC, 48% lower than VP9
  Source: https://engineering.fb.com/2023/02/21/video-engineering/av1-codec-facebook-instagram-reels/

### Medical / Scientific Video

DICOM standard covers medical video compression (H.264 High Profile). Academic papers prove surgery video can compress ~100:1 at "visually lossless." Clinical panels must validate every lossy use case.

## What Doesn't Exist (Gaps)

| Domain | Has Encoding Quality Benchmark? | Notes |
|--------|:-------------------------------:|-------|
| **E-commerce product video** | No | Shopify, Amazon, eBay set upload specs only. Zero quality comparisons. |
| **E-learning / screen recording** | No | Udemy, Coursera, Thinkific set minimums. No platform comparison. |
| **Enterprise video** | No | Gartner evaluates features/security/analytics, never encoding quality. |
| **Single-file quality-optimized encoding** | No | Nobody benchmarks "best quality at smallest size" across providers. |
| **Target-VMAF cloud encoding** | No | Doesn't exist as a service, so can't be benchmarked. |
| **Lossy archival (access copies)** | No | Archives benchmark lossless only. Lossy access copies = afterthought. |

## E-Commerce Platform Specs (for reference)

- **Shopify**: H.264 only, transcodes to 480p/720p/1080p. Recommends 2,500-4,000 kbps for 720p.
- **Amazon**: MP4/MOV, H.264 or H.265, min 720p, max 500MB, 6-45 seconds.
- **eBay**: MP4 H.264 only, max 150MB, output limited to 720p.
- **Cloudinary**: Most used encoding service in e-commerce. Auto quality (`q_auto`), auto format selection. No independent quality benchmark.

## E-Learning Platform Specs (for reference)

- **Udemy**: Min 720p, H.264, max playback 1080p. Free test video review service.
- **Thinkific**: 640px-3840px, uses Wistia for backend encoding. Min 1200 kbps for screencasts.
- **Teachable**: Up to 20GB uploads, broad format support.

## Enterprise Video Platforms (for reference)

- **Kaltura**: Open, customizable. 4.5/5 Gartner Peer Insights.
- **Panopto**: AI search, LMS integration, lecture capture focused. 4.8/5 Gartner.
- **Microsoft Stream**: "Not best optimized for playback, limited encoding" per competitors.
- **Wistia**: Built own encoding, marketing analytics focus. Used by Thinkific.

## Implications for Our Benchmark

1. **MSU is our closest competitor** but they use streaming methodology and don't test single-file quality
2. **Archive benchmarks** are lossless-only; lossy single-file encoding is an open field
3. **E-commerce, e-learning, enterprise** have zero encoding quality benchmarks — complete white space
4. **Meta's research** validates that progressive single-file delivery (not ABR) is the right approach for short-form content
5. **BVI-UGC finding** that VMAF performs poorly on UGC is worth noting — may need supplementary metrics
