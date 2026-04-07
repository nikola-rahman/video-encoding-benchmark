"""Provider ABC, shared dataclasses, and quality search."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from benchmark.util.log import setup_logging

log = setup_logging("provider")


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

    def quality_range(self, codec: str) -> tuple[float, float]:
        """Return (min, max) of the provider's quality setting.

        Higher values must mean higher quality (larger files).
        If the native scale is inverted (e.g. CRF where lower = better),
        the provider must flip it internally.
        """
        raise NotImplementedError(f"{self.name} does not define a quality range")

    def encode_at_quality(self, input_file: Path, codec: str, quality: float, **kwargs) -> EncodingResult:
        """Encode a single file at a specific quality level.

        The quality value is on the scale returned by quality_range().
        Returns an EncodingResult with renditions populated (file downloaded and ready for VMAF).
        """
        raise NotImplementedError(f"{self.name} does not support encode_at_quality")


def search_quality(
    provider: "Provider",
    input_file: Path,
    codec: str,
    target_vmaf: float,
    measure_vmaf: callable,
    tolerance: float = 0.5,
    max_steps: int = 10,
    **kwargs,
) -> tuple[EncodingResult, float, list[dict]]:
    """Binary search over a provider's quality range to find the setting that produces target VMAF.

    Args:
        provider: Provider instance with quality_range() and encode_at_quality().
        input_file: Source video file.
        codec: Codec to encode with.
        target_vmaf: Desired VMAF score.
        measure_vmaf: Callable(reference: Path, distorted: Path) -> float.
            Measures VMAF between two files.
        tolerance: Stop when VMAF is within this many points of target.
        max_steps: Maximum number of encode iterations.
        **kwargs: Passed through to encode_at_quality().

    Returns:
        (best_result, best_vmaf, history) where history is a list of
        {quality, vmaf, encoding_name} dicts for every encode attempted.
    """
    lo, hi = provider.quality_range(codec)
    history = []
    best_result = None
    best_vmaf = 0
    best_distance = float("inf")

    for step in range(max_steps):
        quality = (lo + hi) / 2
        log.info(f"  Step {step + 1}/{max_steps}: quality={quality:.2f} (range {lo:.2f}-{hi:.2f})")

        result = provider.encode_at_quality(input_file, codec, quality, **kwargs)

        # Measure VMAF on the first rendition
        if not result.renditions:
            raise RuntimeError(f"encode_at_quality returned no renditions at quality={quality}")

        distorted = result.renditions[0].local_file
        vmaf = measure_vmaf(input_file, distorted)
        log.info(f"    VMAF: {vmaf:.2f} (target: {target_vmaf})")

        history.append({
            "quality": quality,
            "vmaf": vmaf,
            "encoding_name": result.encoding_name,
        })

        distance = abs(vmaf - target_vmaf)
        if distance < best_distance:
            best_distance = distance
            best_result = result
            best_vmaf = vmaf

        if distance <= tolerance:
            log.info(f"  Converged: VMAF {vmaf:.2f} within tolerance {tolerance}")
            break

        if vmaf < target_vmaf:
            lo = quality
        else:
            hi = quality

    log.info(f"  Best: quality={history[-1]['quality']:.2f}, VMAF={best_vmaf:.2f} ({len(history)} encodes)")
    return best_result, best_vmaf, history
