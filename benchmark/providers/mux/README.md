# Mux

Developer-focused video platform. Mux ingests a source URL and automatically encodes it — there is no manual bitrate ladder or codec selection. The benchmark will use Mux's static MP4 renditions to download and measure the encoded outputs.

## Status

**Not yet implemented.** All methods raise `NotImplementedError`.

## Credentials

| Variable | Description |
|----------|-------------|
| `MUX_TOKEN_ID` | API access token ID |
| `MUX_TOKEN_SECRET` | API access token secret |

Generate credentials at https://dashboard.mux.com/settings/access-tokens.

## Config (benchmark.yaml)

```yaml
providers:
  mux:
    enabled: true
    token_id: ${MUX_TOKEN_ID}
    token_secret: ${MUX_TOKEN_SECRET}
```

## SDK

```
pip install mux-python
```

- **GitHub:** https://github.com/muxinc/mux-python
- **PyPI:** https://pypi.org/project/mux-python/

## Key documentation

- **API Reference:** https://docs.mux.com/api-reference
- **Video API Reference:** https://docs.mux.com/api-reference/video
- **Python SDK guide:** https://www.mux.com/docs/integrations/mux-python-sdk
- **Pricing:** https://www.mux.com/pricing

### Asset workflow

- **Create Asset:** https://www.mux.com/docs/api-reference/video/assets/create-asset
- **Quick-start (stream video files):** https://docs.mux.com/core/stream-video-files
- **Static MP4 renditions:** https://docs.mux.com/guides/enable-static-mp4-renditions

### Status & webhooks

- **Webhook reference:** https://docs.mux.com/webhook-reference
- **Listen for webhooks:** https://docs.mux.com/core/listen-for-webhooks

### Input requirements

- **Preparing assets:** https://docs.mux.com/docs/preparing-assets-for-mux-video

## Notes

- Mux does not expose codec selection (no AV1/HEVC output control). It auto-selects encoding settings. This is a key limitation for the benchmark — we measure whatever Mux produces.
- Use `mp4_support="standard"` (or the newer `static_renditions` API) when creating assets to get downloadable MP4 files.
- Mux pricing is based on input minutes stored + delivery minutes. See https://www.mux.com/docs/pricing/estimating-video-costs.
