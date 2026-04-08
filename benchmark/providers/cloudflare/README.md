# Cloudflare Stream

## Status

**Not included in the benchmark.** See below for why.

## Why Cloudflare Stream is not compatible with this benchmark

This benchmark compares single-file compression efficiency: smallest file at a given quality (VMAF). Cloudflare Stream's architecture makes this comparison impossible for the following reasons.

### Downloads are H.264 only

Cloudflare Stream's downloadable MP4 output is always H.264. There is no option to download H.265 or AV1 encoded files.

- **Download docs**: https://developers.cloudflare.com/stream/viewing-videos/download-videos/ — no codec parameter
- **FAQ**: https://developers.cloudflare.com/stream/faq/ — recommends "MP4 containers, AAC audio codec, H264 video codec" as input format; output codec is not configurable

### AV1 is live-only beta

Cloudflare announced AV1 support for live streaming in open beta, but this applies only to live stream playback — not to VOD uploads or downloadable files.

- **AV1 blog post**: https://blog.cloudflare.com/av1-cloudflare-stream-beta/ — "Play live streams and recordings using the AV1 codec" — live only, not general VOD
- **Community confirmation**: https://community.cloudflare.com/t/stream-h-265-support-not-working/790135 — H.265 not supported

### No quality control

Cloudflare Stream provides no quality, bitrate, CRF, or codec parameters. You upload a video and get whatever encoding Cloudflare decides. There is no way to target a specific VMAF or control the quality-vs-size tradeoff.

- **LLM docs**: https://developers.cloudflare.com/stream/llms-full.txt — confirms automatic encoding with "H.264 codec with adaptive bitrate streaming, supporting resolutions from 360p to 1080p"

### Verified by test

We uploaded `ecom_watch.mp4` (1920x1080, 10s, H.264 CRF 18) to Cloudflare Stream and downloaded the result:

```
Input:  1920x1080, 10.2s, H.264, 9.1 MB
Output: 1920x1080, 10.2s, H.264, 5.5 MB
VMAF:   96.68 (vmaf_v0.6.1neg)
```

For comparison:
- MediaConvert achieved VMAF 93.29 at 1.6 MB (H.265) — 3.4x smaller
- Zencoder achieved VMAF 93.72 at 1.8 MB (H.265) — 3.1x smaller

The difference is primarily codec generation (H.264 vs H.265), not encoding efficiency. This makes the comparison unfair — Cloudflare is handicapped by its codec, not its encoder.

### Benchmark report implications

Cloudflare Stream is a relevant finding for the report:

- Like Mux, Cloudflare represents the "fully managed, zero-configuration" approach
- Their encoding may use modern codecs internally for HLS delivery, but downloadable files are H.264 only
- For single-file delivery (e-commerce, archives, UGC storage), customers get a codec generation behind the competition
- No quality control means no way to optimize for storage efficiency

## Credentials (for reference)

| Variable | Description |
|----------|-------------|
| `CLOUDFLARE_ACCOUNT_ID` | Account ID from dashboard |
| `CLOUDFLARE_API_TOKEN` | API token with Stream:Edit permission |

## API workflow tested

```python
# Upload via URL
POST /accounts/{id}/stream/copy
{"url": "https://...", "meta": {"name": "test"}}

# Check status
GET /accounts/{id}/stream/{uid}

# Enable downloads
POST /accounts/{id}/stream/{uid}/downloads

# Download MP4 (follows 302 redirect)
GET https://customer-xxx.cloudflarestream.com/{uid}/downloads/default.mp4
```

## Key documentation

- **Stream docs**: https://developers.cloudflare.com/stream/
- **Download videos**: https://developers.cloudflare.com/stream/viewing-videos/download-videos/
- **FAQ**: https://developers.cloudflare.com/stream/faq/
- **Pricing**: https://developers.cloudflare.com/stream/pricing/ ($5/1K min stored, $1/1K min delivered)
