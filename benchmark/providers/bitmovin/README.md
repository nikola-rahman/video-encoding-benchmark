# Bitmovin

Cloud encoding API with Per-Title optimization. Bitmovin analyzes content complexity and automatically selects optimal bitrate points — the primary competitor in this benchmark.

## Status

**Implemented.** Submit, poll, download, and cleanup all working.

## Credentials

| Variable | Description |
|----------|-------------|
| `BITMOVIN_API_KEY` | Bitmovin API key |
| `BITMOVIN_S3_OUTPUT_ID` | Pre-configured S3 output ID in Bitmovin dashboard |

## Config (benchmark.yaml)

```yaml
providers:
  bitmovin:
    enabled: true
    api_key: ${BITMOVIN_API_KEY}
    s3_output_id: ${BITMOVIN_S3_OUTPUT_ID}
    s3_output_base_path: encoding-benchmarks/
    per_title:
      max_bitrate: null
      min_bitrate: null
```

## SDK

```bash
uv add bitmovin-api-sdk
```

## Key documentation

- **Encoding API overview:** https://developer.bitmovin.com/encoding/docs
- **API reference:** https://developer.bitmovin.com/encoding/reference
- **Per-Title encoding:** https://developer.bitmovin.com/encoding/docs/per-title-encoding
- **Python SDK (GitHub):** https://github.com/bitmovin/bitmovin-api-sdk-python
- **Pricing:** https://bitmovin.com/pricing

### Codec support

- H.264, H.265/HEVC, AV1, VP9
- Per-Title mode available for all codecs
- Preset configurations: `VOD_STANDARD`, `VOD_HIGH_QUALITY`, etc.

## Notes

- Encoding outputs are written to S3 via a pre-configured output ID (set up in the Bitmovin dashboard).
- Per-Title mode auto-selects a bitrate ladder — each rendition lands in a `{bitrate}/` subdirectory.
- Input is provided as an HTTPS presigned URL.
