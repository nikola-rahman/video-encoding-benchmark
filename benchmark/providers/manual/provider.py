"""Manual file placement provider (replaces add_output.py)."""

import os
from pathlib import Path

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.ffmpeg import get_video_info
from benchmark.util.log import setup_logging

log = setup_logging("manual")

KNOWN_CODECS = ["av1", "hevc", "h265", "h264", "vp9"]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class ManualProvider(Provider):
    capabilities = {"scan"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        data_dir = Path(config["data_dir"])
        self.inputs_dir = Path(config["inputs"]["dir"])
        self.outputs_dir = data_dir / "outputs"

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        """Scan the provider's output directory for encoded files matching the input."""
        provider_name = kwargs.get("provider_name", self.name)
        provider_dir = self.outputs_dir / provider_name

        if not provider_dir.exists():
            log.warning(f"Provider directory not found: {provider_dir}")
            return []

        results = []
        for subdir in sorted(provider_dir.iterdir()):
            if not subdir.is_dir():
                continue

            dir_name = subdir.name

            # Check if this directory matches the input file
            if not dir_name.startswith(input_file.stem):
                continue

            # Extract codec from directory name
            detected_codec = self._extract_codec(dir_name, input_file.stem)
            if detected_codec and detected_codec != codec:
                continue

            video_file = self._find_video_file(subdir)
            if not video_file:
                continue

            result = self._build_result(provider_name, dir_name, detected_codec or codec, input_file, video_file)
            results.append(result)

        return results

    def scan(self, provider_name: str) -> list[EncodingResult]:
        """Scan all files under a provider's output directory."""
        provider_dir = self.outputs_dir / provider_name

        if not provider_dir.exists():
            log.error(f"Provider directory not found: {provider_dir}")
            return []

        results = []
        for subdir in sorted(provider_dir.iterdir()):
            if not subdir.is_dir():
                continue

            dir_name = subdir.name

            video_file = self._find_video_file(subdir)
            if not video_file:
                log.warning(f"  No video file found in {dir_name}/, skipping")
                continue

            input_file = self._find_input_file(dir_name)
            if not input_file:
                log.warning(f"  Could not match input for {dir_name}/, skipping")
                continue

            codec = self._extract_codec(dir_name, input_file.stem)
            if not codec:
                log.warning(f"  Could not extract codec from {dir_name}/, skipping")
                continue

            log.info(f"  Found: {dir_name}")
            log.info(f"    Input: {input_file.name}")
            log.info(f"    Codec: {codec}")
            log.info(f"    File:  {video_file.name}")

            result = self._build_result(provider_name, dir_name, codec, input_file, video_file)
            results.append(result)

        return results

    def _build_result(self, provider_name: str, encoding_name: str, codec: str,
                      input_file: Path, output_file: Path) -> EncodingResult:
        probe = get_video_info(str(output_file))
        fmt = probe.get("format", {})
        bitrate_bps = int(fmt.get("bit_rate", 0))
        file_size = os.path.getsize(output_file)

        return EncodingResult(
            provider=provider_name,
            encoding_name=encoding_name,
            codec=codec,
            input_file=input_file,
            renditions=[Rendition(
                bitrate_bps=bitrate_bps,
                local_file=output_file,
                total_size_bytes=file_size,
            )],
        )

    def _find_input_file(self, dir_name: str) -> Path | None:
        """Match a directory name to an input file."""
        inputs = sorted(self.inputs_dir.iterdir()) if self.inputs_dir.exists() else []
        for inp in sorted(inputs, key=lambda p: len(p.stem), reverse=True):
            if dir_name.startswith(inp.stem):
                return inp
        return None

    @staticmethod
    def _extract_codec(dir_name: str, input_stem: str) -> str | None:
        """Extract codec from the part of dir_name after the input stem."""
        remainder = dir_name[len(input_stem):].lstrip("_")
        parts = remainder.split("_")
        for part in parts:
            if part.lower() in KNOWN_CODECS:
                return part.lower()
        return None

    @staticmethod
    def _find_video_file(directory: Path) -> Path | None:
        """Find a single video file in a directory."""
        videos = [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
        if len(videos) == 1:
            return videos[0]
        if len(videos) > 1:
            for v in videos:
                if v.stem == "output":
                    return v
            return max(videos, key=lambda f: f.stat().st_size)
        return None
