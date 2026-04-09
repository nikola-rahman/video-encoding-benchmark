"""Brightcove Zencoder provider."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import requests

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.ffmpeg import get_actual_bitrate, get_stream_info
from benchmark.util.log import setup_logging
from benchmark.util.s3 import get_s3_client, get_bucket, presign_url

log = setup_logging("zencoder")

API_BASE = "https://app.zencoder.com/api/v2"


class ZencoderProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}
    supported_codecs = {"h265"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config["providers"]["zencoder"]
        self.api_key = os.environ["ZENCODER_API_KEY"]
        self.s3_output_bucket = os.environ["ZENCODER_S3_OUTPUT_BUCKET"]
        self.s3_output_prefix = self.provider_config.get("s3_output_prefix", "zencoder-outputs")
        self.s3_region = os.environ.get("AWS_REGION", "us-east-1")

    def _headers(self) -> dict:
        return {
            "Zencoder-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _aws_s3(self):
        return boto3.client("s3", region_name=self.s3_region)

    def prepare_input(self, input_file: Path, s3_key: str) -> str:
        """Presign a Hippius S3 URL for Zencoder to read via HTTPS."""
        s3 = get_s3_client()
        bucket = get_bucket()
        return presign_url(s3, bucket, s3_key, 86400)

    def encode_to_target_vmaf(self, input_file, codec, target_vmaf, measure_vmaf, tolerance=1.0, max_steps=8, **kwargs):
        return self._search_discrete(input_file, codec, [1, 2, 3, 4, 5], target_vmaf, measure_vmaf, tolerance, **kwargs)

    def encode_at_quality(self, input_file: Path, codec: str, quality, **kwargs) -> EncodingResult:
        """Submit a job, wait for completion, download the output."""
        video_url = kwargs.get("video_url")
        if not video_url:
            s3_prefix = self.config["storage"]["s3"]["prefix"]
            s3_key = f"{s3_prefix}/{input_file.name}"
            video_url = self.prepare_input(input_file, s3_key)

        result = self._submit_job(video_url, codec, input_file, quality)
        job_id = result.encoding_id

        while True:
            status = self.check_status(job_id)
            state = status["status"]
            if state == "FINISHED":
                break
            if state in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Zencoder job {job_id} failed: {status.get('error', state)}")
            log.info(f"    {state}{status.get('progress', '')}")
            time.sleep(5)

        data_dir = Path(self.config["data_dir"])
        output_dir = data_dir / "outputs" / "zencoder"
        return self.download(result, output_dir)

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        """Submit a Zencoder job. Returns list with one EncodingResult."""
        video_url = kwargs.get("video_url")
        if not video_url:
            raise ValueError("ZencoderProvider.get_results() requires video_url kwarg")

        quality = kwargs.get("quality", 3)
        result = self._submit_job(video_url, codec, input_file, quality)
        return [result]

    def check_status(self, encoding_id: str) -> dict:
        """Check job status."""
        resp = requests.get(
            f"{API_BASE}/jobs/{encoding_id}/progress.json",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", "unknown").upper()
        progress = ""
        if state == "PROCESSING" and data.get("progress"):
            progress = f" ({data['progress']}%)"
        return {
            "encoding_id": encoding_id,
            "name": "",
            "status": state,
            "progress": progress,
        }

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        """Download the encoded output from AWS S3."""
        s3 = self._aws_s3()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get job details to find output URL
        resp = requests.get(
            f"{API_BASE}/jobs/{result.encoding_id}.json",
            headers=self._headers(),
        )
        resp.raise_for_status()
        job = resp.json()["job"]

        renditions = []
        for output in job.get("output_media_files", []):
            if output.get("state") != "finished":
                continue

            # Parse S3 key from output URL
            url = output.get("url", "")
            s3_key = url.split(f"{self.s3_output_bucket}/", 1)[-1] if self.s3_output_bucket in url else ""
            if not s3_key:
                continue

            filename = s3_key.rsplit("/", 1)[-1]
            local_file = output_dir / result.encoding_name / filename
            local_file.parent.mkdir(parents=True, exist_ok=True)

            if not local_file.exists():
                log.info(f"  Downloading: {filename}")
                s3.download_file(self.s3_output_bucket, s3_key, str(local_file))

            file_size = local_file.stat().st_size
            bitrate_bps = get_actual_bitrate(str(local_file)) or 0
            renditions.append(Rendition(
                bitrate_bps=bitrate_bps,
                local_file=local_file,
                total_size_bytes=file_size,
                s3_prefix=s3_key,
            ))

        result.renditions = renditions
        return result

    def cleanup(self, result: EncodingResult) -> None:
        """Delete output files from AWS S3."""
        s3 = self._aws_s3()
        for rendition in result.renditions:
            if rendition.s3_prefix:
                s3.delete_object(Bucket=self.s3_output_bucket, Key=rendition.s3_prefix)
                log.info(f"  Deleted s3://{self.s3_output_bucket}/{rendition.s3_prefix}")

    # ── Private helpers ──────────────────────────────────────

    def _submit_job(self, video_url: str, codec: str, input_file: Path, quality: float) -> EncodingResult:
        """Build and submit a Zencoder job."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        encoding_name = f"benchmark_{input_file.stem}_{codec}_{timestamp}"
        output_base = f"s3+{self.s3_region}://{self.s3_output_bucket}/{self.s3_output_prefix}/{encoding_name}/"

        video_codec = self._codec_name(codec)

        payload = {
            "input": video_url,
            "outputs": [{
                "base_url": output_base,
                "filename": f"{input_file.stem}.mp4",
                "format": "mp4",
                "video_codec": video_codec,
                "quality": quality,
                "speed": 1,
            }],
        }

        resp = requests.post(
            f"{API_BASE}/jobs",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        job_id = str(data["id"])
        log.info(f"  Created job: {job_id} ({encoding_name})")

        return EncodingResult(
            provider="zencoder",
            encoding_name=encoding_name,
            codec=codec,
            input_file=input_file,
            encoding_id=job_id,
        )

    @staticmethod
    def _codec_name(codec: str) -> str:
        if codec == "h265":
            return "hevc"
        elif codec == "av1":
            return "av1"
        else:
            raise ValueError(f"Unsupported codec: {codec}")
