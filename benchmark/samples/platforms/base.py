"""Base class for platform downloaders."""

from abc import ABC, abstractmethod
from pathlib import Path


class Downloader(ABC):
    """Base class for all platform downloaders."""

    name: str

    @abstractmethod
    def download(self, source: dict, output_path: Path) -> Path:
        """Download a video from this platform.

        Args:
            source: Source definition from catalog.yaml
            output_path: Where to save the file (without extension — downloader adds it)

        Returns:
            Path to the downloaded file.

        Raises:
            ValueError: If required config is missing (e.g., API key)
            RuntimeError: If download fails
        """
        ...

    def validate_config(self, source: dict) -> None:
        """Validate that all required config is present. Raises ValueError if not."""
        pass
