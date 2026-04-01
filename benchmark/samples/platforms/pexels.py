"""Pexels API downloader."""

import os
import re
from pathlib import Path

import requests

from benchmark.samples.platforms.base import Downloader
from benchmark.util.log import setup_logging

log = setup_logging("pexels")

API_BASE = "https://api.pexels.com/videos/videos"


class PexelsDownloader(Downloader):
    name = "pexels"

    def __init__(self):
        self.api_key = os.environ.get("PEXELS_API_KEY", "")

    def validate_config(self, source: dict) -> None:
        if not self.api_key:
            raise ValueError(
                "PEXELS_API_KEY environment variable is required. "
                "Get a free key at https://www.pexels.com/api/"
            )

    def download(self, source: dict, output_path: Path) -> Path:
        self.validate_config(source)

        url = source.get("url", "")
        video_id = source.get("pexels_id") or self._extract_id(url)
        if not video_id:
            raise ValueError(f"Source {source.get('id')} missing 'pexels_id' and could not extract from URL")

        output_file = output_path.with_suffix(".mp4")
        if output_file.exists():
            log.info(f"  Already downloaded: {output_file.name}")
            return output_file

        log.info(f"  Fetching Pexels video metadata: {video_id}")
        resp = requests.get(
            f"{API_BASE}/{video_id}",
            headers={"Authorization": self.api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        target_quality = source.get("quality", "hd")
        download_url = self._pick_file(data, target_quality)

        log.info(f"  Downloading from Pexels: {data.get('url', video_id)}")
        resp = requests.get(download_url, stream=True, timeout=30)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(output_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    log.info(f"    {downloaded / (1024*1024):.0f} / {total / (1024*1024):.0f} MB ({pct:.0f}%)")

        log.info(f"  Saved: {output_file} ({output_file.stat().st_size / (1024*1024):.1f} MB)")
        return output_file

    @staticmethod
    def _extract_id(url: str) -> str | None:
        match = re.search(r"-(\d+)/?$", url)
        return match.group(1) if match else None

    @staticmethod
    def _pick_file(data: dict, target_quality: str) -> str:
        files = data.get("video_files", [])
        if not files:
            raise RuntimeError(f"No video files found for Pexels video {data.get('id')}")

        # Prefer HD (1080p), fall back to highest available
        quality_priority = {"hd": 1080, "sd": 720, "uhd": 2160}
        target_height = quality_priority.get(target_quality, 1080)

        # Sort by closeness to target height
        best = min(files, key=lambda f: abs((f.get("height") or 0) - target_height))
        url = best.get("link")
        if not url:
            raise RuntimeError(f"No download link for Pexels video {data.get('id')}")

        log.info(f"    Selected: {best.get('width')}x{best.get('height')}, {best.get('quality')}")
        return url
