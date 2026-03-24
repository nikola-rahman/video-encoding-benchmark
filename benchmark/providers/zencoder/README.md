# Brightcove Zencoder

Enterprise cloud transcoding API from Brightcove. Zencoder provides granular control over codec, quality, speed, and output settings — making it one of the more configurable providers in the benchmark.

## Status

**Not yet implemented.** All methods raise `NotImplementedError`.

## Credentials

| Variable | Description |
|----------|-------------|
| `ZENCODER_API_KEY` | Zencoder API key |
| `ZENCODER_S3_OUTPUT_BUCKET` | S3 bucket for encoded outputs |

Sign up at https://app.zencoder.com/signup (includes free integration/test mode).

## Config (benchmark.yaml)

```yaml
providers:
  zencoder:
    enabled: true
    api_key: ${ZENCODER_API_KEY}
    s3_output_bucket: ${ZENCODER_S3_OUTPUT_BUCKET}
    s3_output_prefix: benchmark-outputs/
```

## SDK

```bash
uv add zencoder
```

- **GitHub:** https://github.com/zencoder/zencoder-py
- **Python docs:** https://zencoder.readthedocs.io/en/stable/usage.html
- **API module reference:** https://zencoder.readthedocs.io/en/latest/zencoder.html

## Key documentation

- **API Reference:** https://zencoder.support.brightcove.com/references/reference.html
- **Legacy API docs:** https://app.zencoder.com/docs/api
- **Pricing:** https://zencoder.com/en/file-transcoding/pricing
- **Supported formats & codecs:** https://zencoder.com/en/formats

### Job workflow

- **Create job:** `POST https://app.zencoder.com/api/v2/jobs` with `input` URL and `outputs` array
- **Job progress:** `GET https://app.zencoder.com/api/v2/jobs/{id}/progress.json`
- **Notifications/webhooks:** https://app.zencoder.com/docs/api/encoding/notifications/notifications

### Quality & encoding settings

- **Quality / rate control:** https://app.zencoder.com/docs/api/encoding/rate-control/quality
- Set `"video_codec": "hevc"` for H.265, `"video_codec": "av1"` for AV1
- `quality` parameter: 1 (lowest) to 5 (highest)
- `speed` parameter: 1 (slowest/best quality) to 5 (fastest)

## Notes

- Both H.265/HEVC and AV1 are supported as output codecs.
- The REST API base URL is `https://app.zencoder.com/api/v2/`.
- Outputs can be written to S3, GCS, FTP, or HTTP destinations.
- The Python SDK wraps the REST API: `Zencoder().job.create(input_url, outputs=[...])`.
