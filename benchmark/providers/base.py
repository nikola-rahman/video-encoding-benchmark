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
    supported_codecs: set[str]  # {"h265", "av1"}

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

    def prepare_input(self, input_file: Path, s3_key: str) -> str:
        """Return a URL or path the provider can use to access this input.

        Each provider implements this based on how it accepts inputs:
        - Bitmovin: returns Hippius S3 path directly
        - MediaConvert: presigns a Hippius HTTPS URL
        - Mux/Cloudflare: presigns a Hippius HTTPS URL
        - Manual: returns the local file path
        """
        raise NotImplementedError(f"{self.name} does not implement prepare_input")

    def encode_at_quality(self, input_file: Path, codec: str, quality, **kwargs) -> EncodingResult:
        """Encode a single file at a specific quality level.

        quality type depends on the search strategy:
            - float for continuous search
            - the exact value from the discrete list for discrete search

        Returns an EncodingResult with renditions populated (file downloaded and ready for VMAF).
        """
        raise NotImplementedError(f"{self.name} does not support encode_at_quality")

    def encode_to_target_vmaf(
        self,
        input_file: Path,
        codec: str,
        target_vmaf: float,
        measure_vmaf: callable,
        tolerance: float = 1.0,
        max_steps: int = 8,
        **kwargs,
    ) -> tuple["EncodingResult", float, list[dict]]:
        """Encode a file to hit a target VMAF score.

        Providers with native VMAF targeting (e.g. Vidaio) should override this.
        Other providers should call one of:
            _search_binary_continuous()         — binary search over float range
            _search_binary_discrete()           — binary search over finite value set
            _search_interpolation_continuous()  — 2 binary steps then interpolation (float)
            _search_interpolation_discrete()    — 2 binary steps then interpolation (finite set)
        """
        raise NotImplementedError(
            f"{self.name} must implement encode_to_target_vmaf "
            f"using one of the _search_* methods"
        )

    def _search_binary_continuous(
        self,
        input_file: Path,
        codec: str,
        lo: float,
        hi: float,
        target_vmaf: float,
        measure_vmaf: callable,
        tolerance: float = 1.0,
        max_steps: int = 8,
        **kwargs,
    ) -> tuple["EncodingResult", float, list[dict]]:
        """Binary search over a continuous float range."""
        history = []
        best_result = None
        best_vmaf = 0

        for step in range(max_steps):
            quality = (lo + hi) / 2
            log.info(f"  Step {step + 1}/{max_steps}: quality={quality:.2f} (range {lo:.2f}-{hi:.2f})")

            result = self.encode_at_quality(input_file, codec, quality, **kwargs)
            if not result.renditions:
                raise RuntimeError(f"encode_at_quality returned no renditions at quality={quality}")

            distorted = result.renditions[0].local_file
            vmaf = measure_vmaf(input_file, distorted)
            log.info(f"    VMAF: {vmaf:.2f} (target: {target_vmaf})")

            history.append({"quality": quality, "vmaf": vmaf, "encoding_name": result.encoding_name})

            if vmaf >= target_vmaf:
                if best_result is None or (vmaf - target_vmaf) < (best_vmaf - target_vmaf):
                    best_result = result
                    best_vmaf = vmaf

            if target_vmaf <= vmaf <= target_vmaf + tolerance:
                log.info(f"  Converged: VMAF {vmaf:.2f}")
                break

            if vmaf < target_vmaf:
                lo = quality
            else:
                hi = quality

        if best_result is None:
            best_entry = max(history, key=lambda h: h["vmaf"])
            best_vmaf = best_entry["vmaf"]
            log.warning(f"  Did not reach target VMAF {target_vmaf}. Best: {best_vmaf:.2f}")
            best_result = self.encode_at_quality(input_file, codec, best_entry["quality"], **kwargs)

        log.info(f"  Best: VMAF={best_vmaf:.2f} ({len(history)} encodes)")
        return best_result, best_vmaf, history

    def _encode_and_measure(self, input_file, codec, quality, target_vmaf, measure_vmaf, **kwargs):
        """Encode at a quality level, measure VMAF, return (result, vmaf)."""
        result = self.encode_at_quality(input_file, codec, quality, **kwargs)
        if not result.renditions:
            raise RuntimeError(f"encode_at_quality returned no renditions at quality={quality}")
        vmaf = measure_vmaf(input_file, result.renditions[0].local_file)
        return result, vmaf

    def _interpolate_quality(self, history, target_vmaf, lo, hi):
        """Linear interpolation between the two points that bracket the target VMAF."""
        below = [h for h in history if h["vmaf"] < target_vmaf]
        above = [h for h in history if h["vmaf"] >= target_vmaf]

        if not below or not above:
            return (lo + hi) / 2

        p_lo = max(below, key=lambda h: h["vmaf"])
        p_hi = min(above, key=lambda h: h["vmaf"])

        q1, v1 = p_lo["quality"], p_lo["vmaf"]
        q2, v2 = p_hi["quality"], p_hi["vmaf"]

        if abs(v2 - v1) < 0.01:
            return (q1 + q2) / 2

        quality = q1 + (target_vmaf - v1) * (q2 - q1) / (v2 - v1)
        return max(lo, min(hi, quality))

    def _update_best(self, result, vmaf, target_vmaf, best_result, best_vmaf):
        """Update best result if this one is closer to target (and above it)."""
        if vmaf >= target_vmaf:
            if best_result is None or (vmaf - target_vmaf) < (best_vmaf - target_vmaf):
                return result, vmaf
        return best_result, best_vmaf

    def _search_interpolation_continuous(
        self,
        input_file: Path,
        codec: str,
        lo: float,
        hi: float,
        target_vmaf: float,
        measure_vmaf: callable,
        tolerance: float = 1.0,
        max_steps: int = 8,
        **kwargs,
    ) -> tuple["EncodingResult", float, list[dict]]:
        """2 binary search steps to seed, then linear interpolation."""
        history = []
        best_result = None
        best_vmaf = 0
        prev_vmaf = None

        for step in range(max_steps):
            if len(history) < 2:
                quality = (lo + hi) / 2
            else:
                quality = self._interpolate_quality(history, target_vmaf, lo, hi)

            log.info(f"  Step {step + 1}/{max_steps}: quality={quality:.2f} (range {lo:.2f}-{hi:.2f})")

            result, vmaf = self._encode_and_measure(input_file, codec, quality, target_vmaf, measure_vmaf, **kwargs)
            log.info(f"    VMAF: {vmaf:.2f} (target: {target_vmaf})")
            history.append({"quality": quality, "vmaf": vmaf, "encoding_name": result.encoding_name})
            best_result, best_vmaf = self._update_best(result, vmaf, target_vmaf, best_result, best_vmaf)

            if target_vmaf <= vmaf <= target_vmaf + tolerance:
                log.info(f"  Converged: VMAF {vmaf:.2f}")
                break

            if prev_vmaf is not None and abs(vmaf - prev_vmaf) < 0.01:
                log.info(f"  Stalled: same VMAF {vmaf:.2f}, stopping")
                break
            prev_vmaf = vmaf

            if vmaf < target_vmaf:
                lo = quality
            else:
                hi = quality

        if best_result is None:
            best_entry = max(history, key=lambda h: h["vmaf"])
            best_vmaf = best_entry["vmaf"]
            log.warning(f"  Did not reach target VMAF {target_vmaf}. Best: {best_vmaf:.2f}")
            best_result = self.encode_at_quality(input_file, codec, best_entry["quality"], **kwargs)

        log.info(f"  Best: VMAF={best_vmaf:.2f} ({len(history)} encodes)")
        return best_result, best_vmaf, history

    def _search_interpolation_discrete(
        self,
        input_file: Path,
        codec: str,
        values: list,
        target_vmaf: float,
        measure_vmaf: callable,
        tolerance: float = 1.0,
        **kwargs,
    ) -> tuple["EncodingResult", float, list[dict]]:
        """2 binary search steps to seed, then interpolation snapped to nearest discrete value."""
        history = []
        best_result = None
        best_vmaf = 0
        lo_idx = 0
        hi_idx = len(values) - 1
        tested = set()

        max_steps = len(values)  # can't exceed the number of discrete values

        for step in range(max_steps):
            if len(history) < 2:
                mid_idx = (lo_idx + hi_idx) // 2
            else:
                interpolated = self._interpolate_quality(history, target_vmaf, values[lo_idx], values[hi_idx])
                mid_idx = min(range(lo_idx, hi_idx + 1), key=lambda i: abs(values[i] - interpolated))

            quality = values[mid_idx]
            if quality in tested:
                break
            tested.add(quality)

            log.info(f"  Step {step + 1}: quality={quality} (index {lo_idx}-{hi_idx})")

            result, vmaf = self._encode_and_measure(input_file, codec, quality, target_vmaf, measure_vmaf, **kwargs)
            log.info(f"    VMAF: {vmaf:.2f} (target: {target_vmaf})")
            history.append({"quality": quality, "vmaf": vmaf, "encoding_name": result.encoding_name})
            best_result, best_vmaf = self._update_best(result, vmaf, target_vmaf, best_result, best_vmaf)

            if target_vmaf <= vmaf <= target_vmaf + tolerance:
                log.info(f"  Converged: VMAF {vmaf:.2f}")
                break

            if vmaf < target_vmaf:
                lo_idx = mid_idx + 1
            else:
                hi_idx = mid_idx - 1

            if lo_idx > hi_idx:
                break

        if best_result is None:
            best_entry = max(history, key=lambda h: h["vmaf"])
            best_vmaf = best_entry["vmaf"]
            log.warning(f"  Did not reach target VMAF {target_vmaf}. Best: {best_vmaf:.2f}")
            best_result = self.encode_at_quality(input_file, codec, best_entry["quality"], **kwargs)

        log.info(f"  Best: VMAF={best_vmaf:.2f} ({len(history)} encodes)")
        return best_result, best_vmaf, history

    def _search_binary_discrete(
        self,
        input_file: Path,
        codec: str,
        values: list,
        target_vmaf: float,
        measure_vmaf: callable,
        tolerance: float = 1.0,
        **kwargs,
    ) -> tuple["EncodingResult", float, list[dict]]:
        """Binary search over a sorted list of discrete values."""
        history = []
        best_result = None
        best_vmaf = 0
        lo_idx = 0
        hi_idx = len(values) - 1

        while lo_idx <= hi_idx:
            mid_idx = (lo_idx + hi_idx) // 2
            quality = values[mid_idx]
            log.info(f"  Step {len(history) + 1}: quality={quality} (index {lo_idx}-{hi_idx})")

            result = self.encode_at_quality(input_file, codec, quality, **kwargs)
            if not result.renditions:
                raise RuntimeError(f"encode_at_quality returned no renditions at quality={quality}")

            distorted = result.renditions[0].local_file
            vmaf = measure_vmaf(input_file, distorted)
            log.info(f"    VMAF: {vmaf:.2f} (target: {target_vmaf})")

            history.append({"quality": quality, "vmaf": vmaf, "encoding_name": result.encoding_name})

            if vmaf >= target_vmaf:
                if best_result is None or (vmaf - target_vmaf) < (best_vmaf - target_vmaf):
                    best_result = result
                    best_vmaf = vmaf

            if target_vmaf <= vmaf <= target_vmaf + tolerance:
                log.info(f"  Converged: VMAF {vmaf:.2f}")
                break

            if vmaf < target_vmaf:
                lo_idx = mid_idx + 1
            else:
                hi_idx = mid_idx - 1

        if best_result is None:
            best_entry = max(history, key=lambda h: h["vmaf"])
            best_vmaf = best_entry["vmaf"]
            log.warning(f"  Did not reach target VMAF {target_vmaf}. Best: {best_vmaf:.2f}")
            best_result = self.encode_at_quality(input_file, codec, best_entry["quality"], **kwargs)

        log.info(f"  Best: VMAF={best_vmaf:.2f} ({len(history)} encodes)")
        return best_result, best_vmaf, history
