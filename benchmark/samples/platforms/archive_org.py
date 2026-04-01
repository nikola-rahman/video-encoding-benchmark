"""Archive.org direct HTTP downloader."""

from pathlib import Path

import requests

from benchmark.samples.platforms.base import Downloader
from benchmark.util.log import setup_logging

log = setup_logging("archive_org")


class ArchiveOrgDownloader(Downloader):
    name = "archive_org"

    def download(self, source: dict, output_path: Path) -> Path:
        url = source.get("url")
        if not url:
            raise ValueError(f"Source {source.get('id')} missing 'url'")

        filename = source.get("filename")
        if not filename:
            filename = url.rstrip("/").rsplit("/", 1)[-1]

        output_file = output_path.with_suffix(Path(filename).suffix)
        if output_file.exists():
            log.info(f"  Already downloaded: {output_file.name}")
            return output_file

        log.info(f"  Downloading from archive.org: {filename}")
        resp = requests.get(url, stream=True, timeout=30)
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
