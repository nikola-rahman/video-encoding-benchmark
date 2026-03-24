# Cloudflare Stream

Video encoding and delivery platform integrated with Cloudflare's CDN. Like Mux, Cloudflare Stream auto-encodes uploaded videos — there are no granular codec or quality knobs.

## Status

**Not yet implemented.** All methods raise `NotImplementedError`.

## Credentials

| Variable | Description |
|----------|-------------|
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | API token with Stream permissions |

## Config (benchmark.yaml)

```yaml
providers:
  cloudflare:
    enabled: true
    account_id: ${CLOUDFLARE_ACCOUNT_ID}
    api_token: ${CLOUDFLARE_API_TOKEN}
```

## SDK

```
pip install cloudflare
```

- **GitHub:** https://github.com/cloudflare/cloudflare-python
- **PyPI:** https://pypi.org/project/cloudflare/

Note: the older `python-cloudflare` package is archived. Use the official `cloudflare` package.

## Key documentation

- **Stream docs (overview):** https://developers.cloudflare.com/stream/
- **Getting started:** https://developers.cloudflare.com/stream/get-started/
- **API reference:** https://developers.cloudflare.com/api/resources/stream/
- **API reference (Python examples):** https://developers.cloudflare.com/api/python/resources/stream/
- **Pricing:** https://developers.cloudflare.com/stream/pricing/

### Upload & download

- **Upload via URL:** https://developers.cloudflare.com/stream/uploading-videos/upload-via-link/
- **Upload via URL (API endpoint):** https://developers.cloudflare.com/api/resources/stream/subresources/copy/methods/create/
- **Download videos:** https://developers.cloudflare.com/stream/viewing-videos/download-videos/
- **Downloads API:** https://developers.cloudflare.com/api/resources/stream/subresources/downloads/

### Status & webhooks

- **Webhooks:** https://developers.cloudflare.com/stream/manage-video-library/using-webhooks/

### Codec & quality

- **FAQ (codecs, input format):** https://developers.cloudflare.com/stream/faq/

## Notes

- Cloudflare Stream does **not** expose codec or quality controls. It automatically encodes to H.264 adaptive bitrate (360p-1080p). AV1 may be used for live playback but is not selectable for VOD output.
- Downloads must be explicitly enabled per video via the downloads API before the MP4 can be fetched.
- Pricing: $5 per 1,000 minutes stored, $1 per 1,000 minutes delivered.
- The API uses a REST interface. Base URL: `https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/`.
