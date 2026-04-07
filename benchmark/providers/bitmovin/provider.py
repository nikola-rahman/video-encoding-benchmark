"""Bitmovin cloud API provider."""

import os
import re
import shutil
import sys
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
    PresetConfiguration,
    AclEntry,
    AclPermission,
    StartEncodingRequest,
    PerTitle,
    H265PerTitleConfiguration,
    Av1PerTitleConfiguration,
    Status,
)

import requests

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.ffmpeg import get_actual_bitrate
from benchmark.util.log import setup_logging
from benchmark.util.s3 import get_s3_client, get_bucket, download_prefix, delete_prefix

log = setup_logging("bitmovin")


class BitmovinProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config.get("providers", {}).get("bitmovin", {})
        self.api_key = os.environ.get("BITMOVIN_API_KEY", "")
        self.s3_output_id = os.environ.get("BITMOVIN_S3_OUTPUT_ID", "")
        self.s3_output_base_path = self.provider_config.get("s3_output_base_path", "encoding-benchmarks/")
        self.per_title = self.provider_config.get("per_title", {})
        self._api = None

    def _get_api(self):
        if self._api is None:
            if not self.api_key:
                log.error("Bitmovin API key not configured")
                sys.exit(1)
            self._api = BitmovinApi(api_key=self.api_key, logger=BitmovinApiLogger())
        return self._api

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        """Submit a Bitmovin encoding job. Returns list with one EncodingResult containing the encoding ID."""
        video_url = kwargs.get("video_url")
        if not video_url:
            raise ValueError("BitmovinProvider.get_results() requires video_url kwarg")

        api = self._get_api()
        info = self._submit_encoding(api, video_url, codec)
        return [EncodingResult(
            provider="bitmovin",
            encoding_name=info["name"],
            codec=codec,
            input_file=input_file,
            encoding_id=info["encoding_id"],
        )]

    def check_status(self, encoding_id: str) -> dict:
        """Check encoding status via Bitmovin API."""
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

    def list_encodings(self, status_filter: str | None = None, limit: int = 50, all_encodings: bool = False) -> list[dict]:
        """List Bitmovin encodings."""
        api = self._get_api()


        status_map = {
            "created": Status.CREATED,
            "queued": Status.QUEUED,
            "running": Status.RUNNING,
            "finished": Status.FINISHED,
            "error": Status.ERROR,
        }

        encodings = api.encoding.encodings.list(sort="createdAt:DESC", limit=limit).items
        if not all_encodings:
            encodings = [e for e in encodings if e.name and e.name.startswith("benchmark_")]

        filter_status = status_map.get(status_filter.lower()) if status_filter else None

        rows = []
        for enc in encodings:
            try:
                resp = api.encoding.encodings.status(encoding_id=enc.id)
            except Exception:
                continue
            if filter_status and resp.status != filter_status:
                continue

            progress = ""
            if resp.status == Status.RUNNING and resp.progress is not None:
                progress = f" ({resp.progress}%)"

            rows.append({
                "encoding_id": enc.id,
                "name": enc.name or "",
                "status": str(resp.status).replace("Status.", ""),
                "progress": progress,
            })

        return rows

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        """Download encoding outputs from S3."""
        api = self._get_api()


        encoding_id = result.encoding_id
        encoding, status_resp, streams, fmp4_muxings, mp4_muxings = self._get_encoding_details(api, encoding_id)

        if status_resp.status != Status.FINISHED:
            log.warning(f"  Skipping {encoding_id} (not finished)")
            return result

        s3_client = get_s3_client()
        bucket = get_bucket()

        renditions = self._download_encoding_outputs(
            s3_client, encoding, fmp4_muxings, mp4_muxings, output_dir, bucket
        )

        result.renditions = renditions
        return result

    def download_all_finished(self, output_dir: Path, encoding_ids: list[str] | None = None) -> list[EncodingResult]:
        """Download all finished encodings. Returns list of EncodingResults with populated renditions."""
        api = self._get_api()


        if encoding_ids:
            ids_to_process = encoding_ids
        else:
            encodings = api.encoding.encodings.list(sort="createdAt:DESC").items
            completed = []
            for enc in encodings:
                if enc.name and enc.name.startswith("benchmark_"):
                    try:
                        status_resp = api.encoding.encodings.status(encoding_id=enc.id)
                        if status_resp.status == Status.FINISHED:
                            completed.append(enc)
                    except Exception:
                        pass
            ids_to_process = [e.id for e in completed]

        if not ids_to_process:
            log.info("No completed benchmark encodings found.")
            return []

        log.info(f"Found {len(ids_to_process)} encoding(s) to download")

        s3_client = get_s3_client()
        bucket = get_bucket()

        # Load video URLs for input matching
        video_urls = self._load_video_urls()

        results = []
        for eid in ids_to_process:
            log.info(f"\nProcessing encoding: {eid}")
            encoding, status_resp, streams, fmp4_muxings, mp4_muxings = self._get_encoding_details(api, eid)

            if status_resp.status != Status.FINISHED:
                log.warning(f"  Skipping (not finished)")
                continue

            # Match input URL and download input
            input_url = self._match_input_url(encoding.name, video_urls)
            input_local_path = None
            if input_url:
                input_local_path = self._download_input_video(input_url, output_dir.parent / "inputs")

            # Download outputs
            renditions = self._download_encoding_outputs(
                s3_client, encoding, fmp4_muxings, mp4_muxings, output_dir, bucket
            )

            codec = self._extract_codec_from_name(encoding.name)
            er = EncodingResult(
                provider="bitmovin",
                encoding_name=encoding.name,
                codec=codec,
                input_file=Path(input_local_path) if input_local_path else Path("unknown"),
                renditions=renditions,
                encoding_id=eid,
            )
            results.append(er)

        return results

    def cleanup(self, result: EncodingResult) -> None:
        """Delete Bitmovin encoding job and S3 output files."""
        api = self._get_api()
        s3_client = get_s3_client()
        bucket = get_bucket()

        s3_prefix = f"{self.s3_output_base_path.rstrip('/')}/{result.encoding_name}/"
        log.info(f"  Deleting S3 prefix: {s3_prefix}")
        try:
            count = delete_prefix(s3_client, bucket, s3_prefix)
            log.info(f"  Deleted {count} S3 object(s)")
        except Exception as e:
            log.error(f"  S3 delete failed: {e}")

        if result.encoding_id:
            log.info(f"  Deleting Bitmovin encoding...")
            try:
                api.encoding.encodings.delete(encoding_id=result.encoding_id)
                log.info(f"  Deleted encoding {result.encoding_id}")
            except Exception as e:
                log.error(f"  Bitmovin delete failed: {e}")

    def cleanup_all(self, encoding_ids: list[str] | None = None, keep_local: bool = False,
                    local_output_dir: Path | None = None) -> int:
        """Clean up multiple encodings. Returns count of deleted encodings."""
        api = self._get_api()
        s3_client = get_s3_client()
        bucket = get_bucket()

        if encoding_ids:
            encodings = []
            for eid in encoding_ids:
                try:
                    enc = api.encoding.encodings.get(encoding_id=eid)
                    encodings.append(enc)
                except Exception as e:
                    log.error(f"Could not find encoding {eid}: {e}")
        else:
            encodings_list = api.encoding.encodings.list(sort="createdAt:DESC").items
            encodings = [e for e in encodings_list if e.name and e.name.startswith("benchmark_")]

        if not encodings:
            log.info("No benchmark encodings found.")
            return 0

        for enc in encodings:
            log.info(f"\nDeleting: {enc.name} ({enc.id})")

            s3_prefix = f"{self.s3_output_base_path.rstrip('/')}/{enc.name}/"
            log.info(f"  Deleting S3 prefix: {s3_prefix}")
            try:
                count = delete_prefix(s3_client, bucket, s3_prefix)
                log.info(f"  Deleted {count} S3 object(s)")
            except Exception as e:
                log.error(f"  S3 delete failed: {e}")

            if not keep_local and local_output_dir:
                local_dir = local_output_dir / "bitmovin" / enc.name
                if local_dir.exists():
                    log.info(f"  Deleting local: {local_dir}")
                    shutil.rmtree(local_dir)

            log.info(f"  Deleting Bitmovin encoding...")
            try:
                api.encoding.encodings.delete(encoding_id=enc.id)
                log.info(f"  Deleted encoding {enc.id}")
            except Exception as e:
                log.error(f"  Bitmovin delete failed: {e}")

        return len(encodings)

    # ── Private helpers ──────────────────────────────────────

    def _submit_encoding(self, api, video_url: str, codec_key: str) -> dict:
        parsed = urlparse(video_url)
        host = parsed.hostname
        input_path = parsed.path
        if parsed.query:
            input_path = f"{parsed.path}?{parsed.query}"

        video_name = os.path.basename(parsed.path).rsplit(".", 1)[0]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        encoding_name = f"benchmark_{video_name}_{codec_key}_{timestamp}"
        output_path = f"{self.s3_output_base_path.rstrip('/')}/{encoding_name}"

        # Create HTTPS input
        https_input = api.encoding.inputs.https.create(
            https_input=HttpsInput(name=f"Input: {host}", host=host)
        )
        log.info(f"  Created HTTPS input: {https_input.id}")

        # Create encoding
        encoding = api.encoding.encodings.create(
            encoding=Encoding(name=encoding_name, cloud_region=CloudRegion.AUTO)
        )
        log.info(f"  Created encoding: {encoding.id}")

        # Create codec config
        if codec_key == "h265":
            config = H265VideoConfiguration(
                name="H.265 Per-Title",
                preset_configuration=PresetConfiguration.VOD_STANDARD,
            )
            codec_config = api.encoding.configurations.video.h265.create(h265_video_configuration=config)
            label = "H.265 (HEVC)"
        elif codec_key == "av1":
            config = Av1VideoConfiguration(
                name="AV1 Per-Title",
                preset_configuration=Av1PresetConfiguration.VOD_STANDARD,
            )
            codec_config = api.encoding.configurations.video.av1.create(av1_video_configuration=config)
            label = "AV1"
        else:
            raise ValueError(f"Unsupported codec: {codec_key}")

        # Create video stream
        stream = api.encoding.encodings.streams.create(
            encoding_id=encoding.id,
            stream=Stream(
                name=f"{label} video",
                input_streams=[StreamInput(
                    input_id=https_input.id,
                    input_path=input_path,
                    selection_mode=StreamSelectionMode.AUTO,
                )],
                codec_config_id=codec_config.id,
                mode=StreamMode.PER_TITLE_TEMPLATE_FIXED_RESOLUTION,
            ),
        )
        log.info(f"  Created video stream: {stream.id}")

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
                name="Progressive MP4 muxing",
                filename="output.mp4",
                streams=[MuxingStream(stream_id=stream.id)],
                outputs=[build_output(f"{output_path}/video/{{bitrate}}/")],
            ),
        )
        log.info(f"  Created MP4 muxing")

        # Start encoding with Per-Title
        per_title = PerTitle()
        max_bitrate = self.per_title.get("max_bitrate")
        min_bitrate = self.per_title.get("min_bitrate")

        if codec_key == "h265":
            pt_config = H265PerTitleConfiguration()
            if max_bitrate is not None:
                pt_config.max_bitrate = max_bitrate
            if min_bitrate is not None:
                pt_config.min_bitrate = min_bitrate
            per_title.h265_configuration = pt_config
        elif codec_key == "av1":
            pt_config = Av1PerTitleConfiguration()
            if max_bitrate is not None:
                pt_config.max_bitrate = max_bitrate
            if min_bitrate is not None:
                pt_config.min_bitrate = min_bitrate
            per_title.av1_configuration = pt_config

        api.encoding.encodings.start(
            encoding_id=encoding.id,
            start_encoding_request=StartEncodingRequest(per_title=per_title),
        )
        log.info(f"  Encoding started!")

        return {"encoding_id": encoding.id, "name": encoding_name, "codec": codec_key}

    def _get_encoding_details(self, api, encoding_id):
        encoding = api.encoding.encodings.get(encoding_id=encoding_id)
        status_resp = api.encoding.encodings.status(encoding_id=encoding_id)
        streams = api.encoding.encodings.streams.list(encoding_id=encoding_id).items
        fmp4_muxings = api.encoding.encodings.muxings.fmp4.list(encoding_id=encoding_id).items
        mp4_muxings = api.encoding.encodings.muxings.mp4.list(encoding_id=encoding_id).items
        return encoding, status_resp, streams, fmp4_muxings, mp4_muxings

    def _download_encoding_outputs(self, s3_client, encoding, fmp4_muxings, mp4_muxings, outputs_dir, bucket):
        muxings_to_use = mp4_muxings if mp4_muxings else fmp4_muxings
        muxing_type = "mp4" if mp4_muxings else "fmp4"
        renditions = []

        for muxing in muxings_to_use:
            if not muxing.outputs:
                continue

            for output in muxing.outputs:
                output_path = output.output_path
                if "{bitrate}" in output_path or "{uuid}" in output_path:
                    continue

                parts = output_path.rstrip("/").split("/")
                bitrate_dir = parts[-1] if parts else "unknown"

                rendition_dir = outputs_dir / "bitmovin" / encoding.name / bitrate_dir
                rendition_dir.mkdir(parents=True, exist_ok=True)

                log.info(f"  Downloading rendition: {bitrate_dir} bps ({muxing_type})")
                files = download_prefix(s3_client, bucket, output_path, rendition_dir)

                bitrate_bps = int(bitrate_dir) if bitrate_dir.isdigit() else 0
                total_size = sum(f["size_bytes"] for f in files)
                local_file = None

                if muxing_type == "mp4":
                    mp4_files = [f for f in files if f["local_path"].endswith(".mp4")]
                    if mp4_files:
                        local_file = Path(mp4_files[0]["local_path"])
                        actual = get_actual_bitrate(str(local_file))
                        if actual:
                            bitrate_bps = actual

                if local_file is None:
                    local_file = rendition_dir

                renditions.append(Rendition(
                    bitrate_bps=bitrate_bps,
                    local_file=local_file,
                    total_size_bytes=total_size,
                    s3_prefix=output_path,
                ))

        return renditions

    def _load_video_urls(self) -> list[str]:
        video_urls_file = Path("video_urls.txt")
        urls = []
        if video_urls_file.exists():
            with open(video_urls_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        return urls

    def _match_input_url(self, encoding_name: str, video_urls: list[str]) -> str | None:
        for url in video_urls:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            video_id = filename.rsplit(".", 1)[0]
            if video_id in encoding_name:
                return url
        return None

    def _download_input_video(self, url: str, inputs_dir: Path) -> Path:

        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename:
            filename = "input_video.mp4"

        inputs_dir.mkdir(parents=True, exist_ok=True)
        local_path = inputs_dir / filename
        if local_path.exists():
            log.info(f"  Input already downloaded: {local_path}")
            return local_path

        log.info(f"  Downloading input: {filename}")
        resp = requests.get(url, stream=True)
        resp.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = local_path.stat().st_size / (1024 * 1024)
        log.info(f"  Downloaded input: {filename} ({size_mb:.1f} MB)")
        return local_path

    @staticmethod
    def _extract_codec_from_name(encoding_name: str) -> str:
        match = re.search(r"_(h265|av1|h264|vp9)_\d{8}_", encoding_name)
        if match:
            return match.group(1)
        return "unknown"
