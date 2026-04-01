from benchmark.samples.downloaders.archive_org import ArchiveOrgDownloader
from benchmark.samples.downloaders.huggingface import HuggingFaceDownloader
from benchmark.samples.downloaders.pexels import PexelsDownloader

DOWNLOADERS = {
    "archive_org": ArchiveOrgDownloader,
    "pexels": PexelsDownloader,
    "huggingface": HuggingFaceDownloader,
}

# Platforms that require manual download — no downloader exists
MANUAL_PLATFORMS = {"manual", "kitware"}


def get_downloader(platform: str):
    cls = DOWNLOADERS.get(platform)
    if cls is None:
        raise ValueError(f"No downloader for platform: {platform!r}")
    return cls()


def is_downloadable(platform: str) -> bool:
    return platform in DOWNLOADERS
