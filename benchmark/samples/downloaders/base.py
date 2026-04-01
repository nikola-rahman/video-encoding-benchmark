"""Base class for sample downloaders."""

from abc import ABC, abstractmethod
from pathlib import Path

from tqdm import tqdm


class Downloader(ABC):
    name: str

    @abstractmethod
    def download(self, source: dict, output_path: Path) -> Path:
        """Download a video and return the path to the saved file.

        Args:
            source: Entry from catalog.yaml.
            output_path: Target path without extension (downloader adds it).

        Returns:
            Path to downloaded file.

        Raises:
            ValueError: Missing required config (e.g., API key).
            RuntimeError: Download failed.
        """
        ...

    def _stream_to_file(self, resp, output_file: Path) -> None:
        """Write a streaming HTTP response to a file with tqdm progress bar."""
        total = int(resp.headers.get("content-length", 0))
        with open(output_file, "wb") as f, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            desc=output_file.name,
            leave=False,
        ) as bar:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                bar.update(len(chunk))
