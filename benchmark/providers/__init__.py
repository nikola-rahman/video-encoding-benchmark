from benchmark.providers.bitmovin import BitmovinProvider
from benchmark.providers.cloudflare import CloudflareProvider
from benchmark.providers.ffmpeg import FFmpegProvider
from benchmark.providers.manual import ManualProvider
from benchmark.providers.mediaconvert import MediaConvertProvider
from benchmark.providers.mux import MuxProvider
from benchmark.providers.zencoder import ZencoderProvider

PROVIDERS = {
    "bitmovin": BitmovinProvider,
    "cloudflare": CloudflareProvider,
    "ffmpeg": FFmpegProvider,
    "manual": ManualProvider,
    "mediaconvert": MediaConvertProvider,
    "mux": MuxProvider,
    "zencoder": ZencoderProvider,
}


def get_provider(name: str, config: dict):
    """Instantiate a provider by name with the given config."""
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(PROVIDERS.keys())}")
    return cls(name, config)
