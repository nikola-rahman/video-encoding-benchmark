"""AWS MediaConvert provider."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.ffmpeg import get_actual_bitrate
from benchmark.util.log import setup_logging
from benchmark.util.s3 import get_s3_client, get_bucket, presign_url

log = setup_logging("mediaconvert")

# QVBR max bitrate safety caps per resolution (from AWS docs)
MAX_BITRATE_BY_HEIGHT = {
    2160: 20_000_000,
    1440: 12_000_000,
    1080: 6_000_000,
    720: 4_000_000,
    480: 1_000_000,
    360: 700_000,
}


def _max_bitrate_for_height(height: int) -> int:
    for h in sorted(MAX_BITRATE_BY_HEIGHT.keys(), reverse=True):
        if height >= h:
            return MAX_BITRATE_BY_HEIGHT[h]
    return 6_000_000


class MediaConvertProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}
    supported_codecs = {"h265", "av1"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config["providers"]["mediaconvert"]
        self.region = os.environ.get("MEDIACONVERT_REGION", self.provider_config.get("region"))
        self.role_arn = os.environ["MEDIACONVERT_ROLE_ARN"]
        self.endpoint = os.environ["MEDIACONVERT_ENDPOINT"]
        self.s3_output_bucket = os.environ["MEDIACONVERT_S3_OUTPUT_BUCKET"]
        self.s3_output_prefix = self.provider_config["s3_output_prefix"]
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "mediaconvert",
                region_name=self.region,
                endpoint_url=self.endpoint,
            )
        return self._client

    def _aws_s3(self):
        return boto3.client("s3", region_name=self.region)

    def prepare_input(self, input_file: Path, s3_key: str) -> str:
        """Presign a Hippius S3 URL for MediaConvert to read via HTTPS."""
        s3 = get_s3_client()
        bucket = get_bucket()
        return presign_url(s3, bucket, s3_key, 86400)

    def encode_to_target_vmaf(self, input_file, codec, target_vmaf, measure_vmaf, tolerance=1.0, max_steps=8, **kwargs):
        return self._search_interpolation_continuous(input_file, codec, 1.0, 10.0, target_vmaf, measure_vmaf, tolerance, max_steps, **kwargs)

    def encode_at_quality(self, input_file: Path, codec: str, quality: float, **kwargs) -> EncodingResult:
        """Submit a job, wait for completion, download the output."""
        video_url = kwargs.get("video_url")
        if not video_url:
            s3_prefix = self.config["storage"]["s3"]["prefix"]
            s3_key = f"{s3_prefix}/{input_file.name}"
            video_url = self.prepare_input(input_file, s3_key)

        # Submit
        result = self._submit_job(video_url, codec, input_file, quality)
        job_id = result.encoding_id

        # Poll until complete
        while True:
            status = self.check_status(job_id)
            state = status["status"]
            if state == "COMPLETE":
                break
            if state == "ERROR":
                raise RuntimeError(f"MediaConvert job {job_id} failed: {status.get('error', 'unknown')}")
            log.info(f"    {state}{status.get('progress', '')}")
            time.sleep(10)

        # Download
        data_dir = Path(self.config["data_dir"])
        output_dir = data_dir / "outputs" / "mediaconvert"
        return self.download(result, output_dir)

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        """Submit a MediaConvert job. Returns list with one EncodingResult."""
        video_url = kwargs.get("video_url")
        if not video_url:
            raise ValueError("MediaConvertProvider.get_results() requires video_url kwarg")

        qvbr_level = kwargs.get("qvbr_level", 7)
        result = self._submit_job(video_url, codec, input_file, qvbr_level)
        return [result]

    def check_status(self, encoding_id: str) -> dict:
        """Check job status."""
        mc = self._get_client()
        job = mc.get_job(Id=encoding_id)["Job"]
        status = job["Status"]
        progress = ""
        if status == "PROGRESSING" and job.get("JobPercentComplete"):
            progress = f" ({job['JobPercentComplete']}%)"
        return {
            "encoding_id": encoding_id,
            "name": job.get("UserMetadata", {}).get("benchmark_name", ""),
            "status": status,
            "progress": progress,
            "error": job.get("ErrorMessage", ""),
        }

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        """Download the encoded output from AWS S3."""
        mc = self._get_client()
        job = mc.get_job(Id=result.encoding_id)["Job"]

        if job["Status"] != "COMPLETE":
            log.warning(f"  Skipping {result.encoding_id} (status: {job['Status']})")
            return result

        s3 = self._aws_s3()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find output files in the job's output groups
        renditions = []
        for og in job["Settings"]["OutputGroups"]:
            dest = og["OutputGroupSettings"]["FileGroupSettings"]["Destination"]
            # dest is like s3://bucket/prefix/
            prefix = dest.replace(f"s3://{self.s3_output_bucket}/", "")

            # List objects under that prefix
            resp = s3.list_objects_v2(Bucket=self.s3_output_bucket, Prefix=prefix)
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                filename = key.rsplit("/", 1)[-1]
                if not filename.endswith(".mp4"):
                    continue

                local_file = output_dir / result.encoding_name / filename
                local_file.parent.mkdir(parents=True, exist_ok=True)

                if not local_file.exists() or local_file.stat().st_size != obj["Size"]:
                    log.info(f"  Downloading: {filename} ({obj['Size'] / (1024*1024):.1f} MB)")
                    s3.download_file(self.s3_output_bucket, key, str(local_file))

                bitrate_bps = get_actual_bitrate(str(local_file)) or 0
                renditions.append(Rendition(
                    bitrate_bps=bitrate_bps,
                    local_file=local_file,
                    total_size_bytes=obj["Size"],
                    s3_prefix=prefix,
                ))

        result.renditions = renditions
        return result

    def cleanup(self, result: EncodingResult) -> None:
        """Delete output files from AWS S3."""
        s3 = self._aws_s3()
        for rendition in result.renditions:
            if rendition.s3_prefix:
                resp = s3.list_objects_v2(Bucket=self.s3_output_bucket, Prefix=rendition.s3_prefix)
                for obj in resp.get("Contents", []):
                    s3.delete_object(Bucket=self.s3_output_bucket, Key=obj["Key"])
                    log.info(f"  Deleted s3://{self.s3_output_bucket}/{obj['Key']}")

    # ── Private helpers ──────────────────────────────────────

    def _submit_job(self, video_url: str, codec: str, input_file: Path, qvbr_level: float) -> EncodingResult:
        """Build and submit a MediaConvert job."""
        mc = self._get_client()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        encoding_name = f"benchmark_{input_file.stem}_{codec}_{timestamp}"
        output_dest = f"s3://{self.s3_output_bucket}/{self.s3_output_prefix.rstrip('/')}/{encoding_name}/"

        # Probe input for resolution to set appropriate max bitrate
        from benchmark.util.ffmpeg import get_stream_info
        stream_info = get_stream_info(str(input_file))
        height = stream_info.get("streams", [{}])[0].get("height", 1080)
        max_bitrate = _max_bitrate_for_height(height)

        codec_settings = self._build_codec_settings(codec, qvbr_level, max_bitrate)

        job = mc.create_job(
            Role=self.role_arn,
            Settings={
                "Inputs": [{
                    "FileInput": video_url,
                    "VideoSelector": {"PadVideo": "DISABLED"},
                }],
                "OutputGroups": [{
                    "Name": "File Group",
                    "OutputGroupSettings": {
                        "Type": "FILE_GROUP_SETTINGS",
                        "FileGroupSettings": {"Destination": output_dest},
                    },
                    "Outputs": [{
                        "ContainerSettings": {"Container": "MP4", "Mp4Settings": {}},
                        "VideoDescription": {"CodecSettings": codec_settings},
                    }],
                }],
            },
            UserMetadata={"benchmark_name": encoding_name},
        )

        job_id = job["Job"]["Id"]
        log.info(f"  Created job: {job_id} ({encoding_name})")

        return EncodingResult(
            provider="mediaconvert",
            encoding_name=encoding_name,
            codec=codec,
            input_file=input_file,
            encoding_id=job_id,
        )

    @staticmethod
    def _build_codec_settings(codec: str, qvbr_level: float, max_bitrate: int) -> dict:
        """Build codec settings using QVBR with fine-tune."""
        level = int(qvbr_level)
        fine_tune = qvbr_level - level

        qvbr_settings = {"QvbrQualityLevel": level}
        if fine_tune != 0:
            qvbr_settings["QvbrQualityLevelFineTune"] = fine_tune

        if codec == "h265":
            return {
                "Codec": "H_265",
                "H265Settings": {
                    "RateControlMode": "QVBR",
                    "QvbrSettings": qvbr_settings,
                    "QualityTuningLevel": "MULTI_PASS_HQ",
                    "MaxBitrate": max_bitrate,
                },
            }
        elif codec == "av1":
            return {
                "Codec": "AV1",
                "Av1Settings": {
                    "RateControlMode": "QVBR",
                    "QvbrSettings": qvbr_settings,
                    "MaxBitrate": max_bitrate,
                },
            }
        else:
            raise ValueError(f"Unsupported codec: {codec}")
