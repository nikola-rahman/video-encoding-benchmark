from benchmark.samples.platforms.archive_org import ArchiveOrgDownloader
from benchmark.samples.platforms.huggingface import HuggingFaceDownloader
from benchmark.samples.platforms.kitware import KitwareDownloader
from benchmark.samples.platforms.pexels import PexelsDownloader

PLATFORMS = {
    "archive_org": ArchiveOrgDownloader,
    "pexels": PexelsDownloader,
    "kitware": KitwareDownloader,
    "huggingface": HuggingFaceDownloader,
}


def get_downloader(platform: str):
    cls = PLATFORMS.get(platform)
    if cls is None:
        raise ValueError(f"Unknown platform: {platform!r}. Available: {list(PLATFORMS.keys())}")
    return cls()
