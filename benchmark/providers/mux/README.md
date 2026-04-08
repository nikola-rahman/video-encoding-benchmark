# Mux

## Status

**Not included in the benchmark.** See below for why.

## Why Mux is not compatible with this benchmark

This benchmark compares single-file compression efficiency: smallest file at a given quality (VMAF). Mux's architecture makes this comparison impossible for the following reasons.

### No codec control

Mux offers three quality tiers (basic, plus, premium) but no codec selection. The `video_quality` parameter controls encoding effort, not the codec. There is no `video_codec` parameter in the API.

- **API reference** confirms no codec parameter: https://www.mux.com/docs/api-reference/video.txt
- **Quality levels docs**: https://www.mux.com/docs/guides/use-video-quality-levels

### Static MP4 downloads are H.264 only

Mux delivers H.265 and AV1 via HLS streaming to supported browsers, but the only downloadable format is static MP4 renditions — which are always H.264.

- **Static renditions docs**: https://www.mux.com/docs/guides/enable-static-mp4-renditions — resolution is configurable (270p-2160p), but codec is not.
- **HEVC is input-only**: https://www.mux.com/blog/faster-processing-for-modern-video-hevc-is-now-a-standard-input-on-mux-video — "HEVC is on our list of standard input codecs" — explicitly about accepting HEVC uploads, not outputting HEVC.

### No quality target

Mux does not accept a target VMAF, CRF, QVBR level, or any quality parameter beyond the three tiers. There is no way to control the quality-vs-size tradeoff. You get whatever Mux decides.

### Streaming-optimized encoding

Mux's H.265/AV1 encodings are locked behind HLS streaming delivery (short GOPs, segmented, ABR ladder). Downloading HLS segments and reassembling them would give us streaming-optimized encoding — exactly the overhead this benchmark measures against. That would not represent single-file compression efficiency.

### Test results

We tested Mux Premium with `ecom_watch.mp4` (1920x1080, 10s):

| Rendition | Resolution | Codec | Bitrate | Size | VMAF |
|-----------|-----------|-------|---------|------|------|
| high | 1920x1080 | H.264 | 7461 kbps | 9.5 MB | 97.73 |
| medium | 960x540 | H.264 | 1739 kbps | 2.2 MB | — |
| low | 640x360 | H.264 | 907 kbps | 1.1 MB | — |

For comparison, MediaConvert achieved VMAF 93.29 at 1318 kbps (H.265) — 5.6x lower bitrate than Mux's H.264 output at similar quality. This is an unfair codec-generation comparison (H.264 vs H.265), which is exactly why Mux cannot be included in the benchmark.

### Benchmark report implications

Mux is a relevant finding for the report's narrative:

- Mux represents the "fully managed, zero-configuration" approach to video encoding
- Their best compression technology (H.265/AV1) is only available via streaming delivery, not as downloadable files
- For customers who need single-file delivery (e-commerce, archives, UGC storage), Mux forces H.264 — a codec generation behind the competition
- This supports the benchmark's thesis: streaming-optimized platforms are not optimized for storage-first use cases

## Credentials (for reference)

| Variable | Description |
|----------|-------------|
| `MUX_TOKEN_ID` | API access token ID |
| `MUX_TOKEN_SECRET` | API access token secret |

Generate at https://dashboard.mux.com/settings/access-tokens.

## Key documentation

- **API Reference:** https://docs.mux.com/api-reference/video
- **Static MP4 renditions:** https://docs.mux.com/guides/enable-static-mp4-renditions
- **Quality levels:** https://www.mux.com/docs/guides/use-video-quality-levels
- **Pricing:** https://www.mux.com/pricing
