"""FFmpeg software-encoder provider.

Uses libx265 (H.265) and libsvtav1 (AV1) with scene-parallel encoding:
each source is split at its existing keyframes into independent
segments, encoded in parallel, then concatenated losslessly. CRF is the
quality parameter; the benchmark's interpolation search finds the CRF
that hits each target VMAF.

This is the "what if I just ran FFmpeg myself" baseline. Runs entirely
locally (subprocess to ffmpeg in PATH), no API calls.
"""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmark.providers.base import EncodingResult, Provider, Rendition
from benchmark.util.ffmpeg import get_actual_bitrate
from benchmark.util.log import setup_logging

log = setup_logging("provider.ffmpeg")


class FFmpegProvider(Provider):
    name = "ffmpeg"
    supported_codecs = {"h265", "av1"}
    capabilities = {"local"}

    # CRF ranges used by the interpolation search. Lower CRF = higher quality.
    # Full encoder ranges; interpolation converges in 4-6 steps regardless.
    H265_CRF_LO, H265_CRF_HI = 0.0, 51.0
    AV1_CRF_LO, AV1_CRF_HI = 0.0, 63.0

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        pcfg = config.get("providers", {}).get("ffmpeg", {})
        self.preset_h265 = pcfg.get("preset_h265", "slow")
        self.preset_av1 = pcfg.get("preset_av1", 4)  # SVT-AV1 preset: 0=slowest, 13=fastest
        self.parallelism = pcfg.get("parallelism", 24)

    # -- Provider interface ------------------------------------------------

    def get_results(self, input_file: Path, codec: str, **kwargs):
        raise NotImplementedError(
            "FFmpegProvider doesn't use get_results; benchmark calls "
            "encode_to_target_vmaf directly."
        )

    def encode_to_target_vmaf(
        self,
        input_file: Path,
        codec: str,
        target_vmaf: float,
        measure_vmaf,
        tolerance: float = 1.0,
        max_steps: int = 8,
        **kwargs,
    ):
        if codec == "h265":
            lo, hi = self.H265_CRF_LO, self.H265_CRF_HI
        elif codec == "av1":
            lo, hi = self.AV1_CRF_LO, self.AV1_CRF_HI
        else:
            raise ValueError(f"Unsupported codec: {codec}")
        return self._search_interpolation_continuous(
            input_file, codec, lo, hi, target_vmaf, measure_vmaf, tolerance, max_steps, **kwargs,
        )

    def encode_at_quality(self, input_file: Path, codec: str, quality: float, **kwargs) -> EncodingResult:
        crf = float(quality)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        encoding_name = f"ffmpeg_{input_file.stem}_{codec}_crf{crf:.2f}_{timestamp}"

        data_dir = Path(self.config["data_dir"])
        work_dir = data_dir / "outputs" / "ffmpeg" / encoding_name
        seg_dir = work_dir / "segments"
        enc_dir = work_dir / "encoded"
        seg_dir.mkdir(parents=True, exist_ok=True)
        enc_dir.mkdir(parents=True, exist_ok=True)

        log.info(f"  CRF {crf:.2f} ({codec}, preset={self._preset_for(codec)})")

        segments = self._split_at_keyframes(input_file, seg_dir)
        log.info(f"  Split into {len(segments)} segments")

        self._encode_segments_parallel(segments, enc_dir, codec, crf)

        out_file = work_dir / f"{input_file.stem}.mp4"
        encoded = sorted(enc_dir.glob("enc_*.mp4"))
        self._concat(encoded, out_file)

        file_size = out_file.stat().st_size
        bitrate = get_actual_bitrate(str(out_file)) or 0
        rendition = Rendition(bitrate_bps=bitrate, local_file=out_file, total_size_bytes=file_size)
        return EncodingResult(
            provider=self.name,
            encoding_name=encoding_name,
            codec=codec,
            input_file=input_file,
            renditions=[rendition],
        )

    # -- Internals ---------------------------------------------------------

    def _preset_for(self, codec: str):
        return self.preset_h265 if codec == "h265" else self.preset_av1

    def _split_at_keyframes(self, input_file: Path, seg_dir: Path) -> list[Path]:
        """Split at the source file's existing keyframes losslessly."""
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_file),
            "-c", "copy", "-map", "0:v",
            "-f", "segment", "-reset_timestamps", "1",
            str(seg_dir / "seg_%04d.mp4"),
        ]
        subprocess.run(cmd, check=True)
        return sorted(seg_dir.glob("seg_*.mp4"))

    def _encode_segments_parallel(self, segments: list[Path], enc_dir: Path, codec: str, crf: float):
        codec_args = self._codec_args(codec, crf)

        def encode_one(seg: Path):
            out = enc_dir / f"enc_{seg.name}"
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(seg)] + codec_args + ["-an", str(out)]
            subprocess.run(cmd, check=True)

        with ThreadPoolExecutor(max_workers=self.parallelism) as ex:
            list(ex.map(encode_one, segments))  # raises if any fails

    def _codec_args(self, codec: str, crf: float) -> list[str]:
        if codec == "h265":
            return ["-c:v", "libx265", "-preset", self.preset_h265, "-crf", f"{crf:.2f}"]
        if codec == "av1":
            return ["-c:v", "libsvtav1", "-preset", str(self.preset_av1), "-crf", f"{crf:.2f}"]
        raise ValueError(f"Unsupported codec: {codec}")

    def _concat(self, encoded_segments: list[Path], out_file: Path):
        concat_list = out_file.parent / "concat.txt"
        with open(concat_list, "w") as fh:
            for seg in encoded_segments:
                fh.write(f"file '{seg.resolve()}'\n")
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(out_file),
        ]
        subprocess.run(cmd, check=True)
