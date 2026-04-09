"""Bitmovin cloud API provider."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bitmovin_api_sdk import BitmovinApi, BitmovinApiLogger
from bitmovin_api_sdk.models import (
    HttpsInput,
    H265VideoConfiguration,
    Av1VideoConfiguration,
    Av1PresetConfiguration,
    Encoding,
    Stream,
    StreamInput,
    StreamMode,
    StreamSelectionMode,
    EncodingOutput,
    Mp4Muxing,
    MuxingStream,
    CloudRegion,
    AclEntry,
    AclPermission,
    StartEncodingRequest,
    Status,
    ProfileH265,
    EncodingMode,
)

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.ffmpeg import get_actual_bitrate
from benchmark.util.log import setup_logging
from benchmark.util.s3 import get_s3_client, get_bucket, presign_url, download_prefix, delete_prefix

log = setup_logging("bitmovin")


class BitmovinProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}
    supported_codecs = {"h265", "av1"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config["providers"]["bitmovin"]
        self.api_key = os.environ["BITMOVIN_API_KEY"]
        self.s3_output_id = os.environ["BITMOVIN_S3_OUTPUT_ID"]
        self.s3_output_base_path = self.provider_config["s3_output_base_path"]
        self._api = None

    def _get_api(self):
        if self._api is None:
            self._api = BitmovinApi(api_key=self.api_key, logger=BitmovinApiLogger())
        return self._api

    def prepare_input(self, input_file: Path, s3_key: str) -> str:
        """Presign a Hippius S3 URL for Bitmovin to read via HTTPS."""
        s3 = get_s3_client()
        bucket = get_bucket()
        return presign_url(s3, bucket, s3_key, 86400)

    def encode_to_target_vmaf(self, input_file, codec, target_vmaf, measure_vmaf, tolerance=1.0, max_steps=8, **kwargs):
        if codec == "av1":
            input_bitrate = get_actual_bitrate(str(input_file))
            return self._search_continuous(input_file, codec, 10_000, input_bitrate, target_vmaf, measure_vmaf, tolerance, max_steps, **kwargs)
        return self._search_continuous(input_file, codec, 0.0, 51.0, target_vmaf, measure_vmaf, tolerance, max_steps, **kwargs)

    def encode_at_quality(self, input_file: Path, codec: str, quality: float, **kwargs) -> EncodingResult:
        """Encode at a quality level.

        For H.265: quality is on our inverted CRF scale (higher = better).
        For AV1: quality is target bitrate in bps (higher = better quality).
        """
        video_url = kwargs.get("video_url")
        if not video_url:
            s3_prefix = self.config["storage"]["s3"]["prefix"]
            s3_key = f"{s3_prefix}/{input_file.name}"
            video_url = self.prepare_input(input_file, s3_key)

        result = self._submit_job(video_url, codec, input_file, quality)
        job_id = result.encoding_id

        # Poll until complete
        while True:
            status = self.check_status(job_id)
            state = status["status"]
            if state == "FINISHED":
                break
            if state == "ERROR":
                raise RuntimeError(f"Bitmovin job {job_id} failed")
            log.info(f"    {state}{status.get('progress', '')}")
            time.sleep(10)

        # Download
        data_dir = Path(self.config["data_dir"])
        output_dir = data_dir / "outputs" / "bitmovin"
        return self.download(result, output_dir)

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        """Submit a Bitmovin encoding job."""
        video_url = kwargs.get("video_url")
        if not video_url:
            raise ValueError("BitmovinProvider.get_results() requires video_url kwarg")

        crf = kwargs.get("crf", 23)
        result = self._submit_job(video_url, codec, input_file, crf)
        return [result]

    def check_status(self, encoding_id: str) -> dict:
        """Check encoding status."""
        api = self._get_api()
        enc = api.encoding.encodings.get(encoding_id=encoding_id)
        resp = api.encoding.encodings.status(encoding_id=encoding_id)
        progress = ""
        if resp.status == Status.RUNNING and resp.progress is not None:
            progress = f" ({resp.progress}%)"
        return {
            "encoding_id": encoding_id,
            "name": enc.name or "",
            "status": str(resp.status).replace("Status.", ""),
            "progress": progress,
        }

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        """Download encoding outputs from Hippius S3."""
        api = self._get_api()
        encoding_id = result.encoding_id

        encoding = api.encoding.encodings.get(encoding_id=encoding_id)
        status_resp = api.encoding.encodings.status(encoding_id=encoding_id)

        if status_resp.status != Status.FINISHED:
            log.warning(f"  Skipping {encoding_id} (not finished)")
            return result

        s3_client = get_s3_client()
        bucket = get_bucket()

        mp4_muxings = api.encoding.encodings.muxings.mp4.list(encoding_id=encoding_id).items
        renditions = []

        for muxing in mp4_muxings:
            if not muxing.outputs:
                continue

            for output in muxing.outputs:
                output_path = output.output_path
                if "{bitrate}" in output_path or "{uuid}" in output_path:
                    continue

                parts = output_path.rstrip("/").split("/")
                bitrate_dir = parts[-1] if parts else "unknown"

                rendition_dir = output_dir / encoding.name / bitrate_dir
                rendition_dir.mkdir(parents=True, exist_ok=True)

                log.info(f"  Downloading rendition: {bitrate_dir}")
                files = download_prefix(s3_client, bucket, output_path, rendition_dir)

                mp4_files = [f for f in files if f["local_path"].endswith(".mp4")]
                if mp4_files:
                    local_file = Path(mp4_files[0]["local_path"])
                    bitrate_bps = get_actual_bitrate(str(local_file)) or 0
                    total_size = local_file.stat().st_size

                    renditions.append(Rendition(
                        bitrate_bps=bitrate_bps,
                        local_file=local_file,
                        total_size_bytes=total_size,
                        s3_prefix=output_path,
                    ))

        result.renditions = renditions
        return result

    def cleanup(self, result: EncodingResult) -> None:
        """Delete Bitmovin encoding and S3 outputs."""
        api = self._get_api()
        s3_client = get_s3_client()
        bucket = get_bucket()

        s3_prefix = f"{self.s3_output_base_path.rstrip('/')}/{result.encoding_name}/"
        log.info(f"  Deleting S3 prefix: {s3_prefix}")
        count = delete_prefix(s3_client, bucket, s3_prefix)
        log.info(f"  Deleted {count} S3 object(s)")

        if result.encoding_id:
            log.info(f"  Deleting Bitmovin encoding...")
            api.encoding.encodings.delete(encoding_id=result.encoding_id)
            log.info(f"  Deleted encoding {result.encoding_id}")

    # ── Private helpers ──────────────────────────────────────

    def _submit_job(self, video_url: str, codec: str, input_file: Path, quality: float) -> EncodingResult:
        """Submit an encoding job. quality semantics depend on codec."""
        api = self._get_api()

        parsed = urlparse(video_url)
        host = parsed.hostname
        input_path = parsed.path
        if parsed.query:
            input_path = f"{parsed.path}?{parsed.query}"

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        encoding_name = f"benchmark_{input_file.stem}_{codec}_{timestamp}"
        output_path = f"{self.s3_output_base_path.rstrip('/')}/{encoding_name}"

        # Create HTTPS input
        https_input = api.encoding.inputs.https.create(
            https_input=HttpsInput(name=f"Input: {host}", host=host)
        )

        # Create encoding
        encoding = api.encoding.encodings.create(
            encoding=Encoding(name=encoding_name, cloud_region=CloudRegion.AUTO)
        )

        codec_config = self._create_codec_config(api, codec, quality)

        # Create video stream
        stream = api.encoding.encodings.streams.create(
            encoding_id=encoding.id,
            stream=Stream(
                name=f"{codec.upper()} video",
                input_streams=[StreamInput(
                    input_id=https_input.id,
                    input_path=input_path,
                    selection_mode=StreamSelectionMode.AUTO,
                )],
                codec_config_id=codec_config.id,
                mode=StreamMode.STANDARD,
            ),
        )

        # Create MP4 muxing
        def build_output(path):
            return EncodingOutput(
                output_id=self.s3_output_id,
                output_path=path,
                acl=[AclEntry(permission=AclPermission.PRIVATE)],
            )

        api.encoding.encodings.muxings.mp4.create(
            encoding_id=encoding.id,
            mp4_muxing=Mp4Muxing(
                name="MP4 muxing",
                filename="output.mp4",
                streams=[MuxingStream(stream_id=stream.id)],
                outputs=[build_output(f"{output_path}/")],
            ),
        )

        # Start encoding
        api.encoding.encodings.start(
            encoding_id=encoding.id,
            start_encoding_request=StartEncodingRequest(),
        )
        log.info(f"  Created job: {encoding.id} ({encoding_name})")

        return EncodingResult(
            provider="bitmovin",
            encoding_name=encoding_name,
            codec=codec,
            input_file=input_file,
            encoding_id=encoding.id,
        )

    def _create_codec_config(self, api, codec: str, quality: float):
        if codec == "h265":
            return self._create_h265_config(api, quality)
        elif codec == "av1":
            return self._create_av1_config(api, quality)
        raise ValueError(f"Unsupported codec: {codec}")

    def _create_h265_config(self, api, quality: float):
        """H.265: CRF single-pass. quality is on inverted scale (higher = better)."""
        crf = 51.0 - quality
        config = H265VideoConfiguration(
            name=f"H.265 CRF {crf:.0f}",
            crf=crf,
            profile=ProfileH265.MAIN,
            encoding_mode=EncodingMode.SINGLE_PASS,
        )
        return api.encoding.configurations.video.h265.create(
            h265_video_configuration=config
        )

    def _create_av1_config(self, api, quality: float):
        """AV1: bitrate-targeted 3-pass. quality is target bitrate in bps."""
        bitrate = int(quality)
        config = Av1VideoConfiguration(
            name=f"AV1 {bitrate / 1000:.0f}kbps",
            bitrate=bitrate,
            preset_configuration=Av1PresetConfiguration.VOD_QUALITY,
            encoding_mode=EncodingMode.THREE_PASS,
        )
        return api.encoding.configurations.video.av1.create(
            av1_video_configuration=config
        )
