"""Provider ABC and shared dataclasses."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Rendition:
    bitrate_bps: int
    local_file: Path
    total_size_bytes: int
    s3_prefix: str | None = None


@dataclass
class EncodingResult:
    provider: str
    encoding_name: str
    codec: str
    input_file: Path
    renditions: list[Rendition] = field(default_factory=list)
    encoding_id: str | None = None

    def to_metadata_dict(self) -> dict:
        """Convert to the metadata.json format used by existing scripts."""
        rendition_dicts = []
        for r in self.renditions:
            rendition_dicts.append({
                "bitrate_bps": r.bitrate_bps,
                "bitrate_kbps": round(r.bitrate_bps / 1000, 2) if r.bitrate_bps else None,
                "local_file": str(r.local_file),
                "file_count": 1,
                "total_size_bytes": r.total_size_bytes,
                "s3_prefix": r.s3_prefix,
            })
        return {
            "provider": self.provider,
            "encoding_id": self.encoding_id,
            "encoding_name": self.encoding_name,
            "codec": self.codec,
            "input": {
                "local_path": str(self.input_file),
                "filename": self.input_file.name,
            },
            "renditions": rendition_dicts,
        }


class Provider(ABC):
    """Base class for all encoding providers."""

    name: str
    capabilities: set[str]  # {"submit", "poll", "download", "local", "scan", "cleanup"}

    def __init__(self, provider_name: str, config: dict):
        self.name = provider_name
        self.config = config

    @abstractmethod
    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        """Main entry point. Cloud providers submit + return encoding IDs.
        Local providers encode synchronously. Manual providers scan the filesystem."""
        ...

    def check_status(self, encoding_id: str) -> dict:
        """Check encoding status. Only applicable if 'poll' in capabilities."""
        raise NotImplementedError(f"{self.name} does not support status polling")

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        """Download encoded outputs. Only applicable if 'download' in capabilities."""
        raise NotImplementedError(f"{self.name} does not support downloading")

    def cleanup(self, result: EncodingResult) -> None:
        """Clean up remote resources. Only applicable if 'cleanup' in capabilities."""
        raise NotImplementedError(f"{self.name} does not support cleanup")
