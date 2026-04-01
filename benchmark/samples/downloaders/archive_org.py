"""Archive.org direct HTTP downloader."""

from pathlib import Path

import requests

from benchmark.samples.downloaders.base import Downloader


class ArchiveOrgDownloader(Downloader):
    name = "archive_org"

    def download(self, source: dict, output_path: Path) -> Path:
        url = source.get("url")
        if not url:
            raise ValueError(f"Source {source['id']} missing 'url'")

        filename = source.get("filename")
        if not filename:
            filename = url.rstrip("/").rsplit("/", 1)[-1]

        output_file = output_path.with_suffix(Path(filename).suffix)
        if output_file.exists():
            return output_file

        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        self._stream_to_file(resp, output_file)
        return output_file
