"""Pexels API downloader."""

import os
import re
from pathlib import Path

import requests

from benchmark.samples.downloaders.base import Downloader

API_BASE = "https://api.pexels.com/videos/videos"


class PexelsDownloader(Downloader):
    name = "pexels"

    def __init__(self):
        self.api_key = os.environ.get("PEXELS_API_KEY", "")

    def download(self, source: dict, output_path: Path) -> Path:
        if not self.api_key:
            raise ValueError(
                "PEXELS_API_KEY environment variable is required. "
                "Get a free key at https://www.pexels.com/api/"
            )

        video_id = source.get("pexels_id") or self._extract_id(source.get("url", ""))
        if not video_id:
            raise ValueError(f"Source {source['id']} missing 'pexels_id'")

        output_file = output_path.with_suffix(".mp4")
        if output_file.exists():
            return output_file

        resp = requests.get(
            f"{API_BASE}/{video_id}",
            headers={"Authorization": self.api_key},
            timeout=15,
        )
        resp.raise_for_status()

        download_url = self._pick_file(resp.json())

        resp = requests.get(download_url, stream=True, timeout=30)
        resp.raise_for_status()
        self._stream_to_file(resp, output_file)
        return output_file

    @staticmethod
    def _extract_id(url: str) -> str | None:
        match = re.search(r"-(\d+)/?$", url)
        return match.group(1) if match else None

    @staticmethod
    def _pick_file(data: dict) -> str:
        files = data.get("video_files", [])
        if not files:
            raise RuntimeError(f"No video files for Pexels video {data.get('id')}")

        best = max(files, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
        url = best.get("link")
        if not url:
            raise RuntimeError(f"No download link for Pexels video {data.get('id')}")
        return url
