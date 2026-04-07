"""AWS MediaConvert provider."""

import os
from pathlib import Path

import boto3

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.log import setup_logging
from benchmark.util.s3 import get_s3_client, get_bucket, presign_url

log = setup_logging("mediaconvert")


class MediaConvertProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config.get("providers", {}).get("mediaconvert", {})
        self.region = os.environ.get("MEDIACONVERT_REGION", self.provider_config.get("region", "us-east-1"))
        self.role_arn = os.environ.get("MEDIACONVERT_ROLE_ARN", "")
        self.endpoint = os.environ.get("MEDIACONVERT_ENDPOINT", "")
        self.s3_output_bucket = os.environ.get("MEDIACONVERT_S3_OUTPUT_BUCKET", "")
        self.s3_output_prefix = self.provider_config["s3_output_prefix"]
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.role_arn:
                raise ValueError("MEDIACONVERT_ROLE_ARN env var not set")
            if not self.endpoint:
                raise ValueError("MEDIACONVERT_ENDPOINT env var not set")
            self._client = boto3.client(
                "mediaconvert",
                region_name=self.region,
                endpoint_url=self.endpoint,
            )
        return self._client

    def prepare_input(self, input_file: Path, s3_key: str) -> str:
        """Presign a Hippius S3 URL for MediaConvert to read via HTTPS."""
        s3 = get_s3_client()
        bucket = get_bucket()
        return presign_url(s3, bucket, s3_key, 86400)

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        raise NotImplementedError("MediaConvertProvider.get_results() not yet implemented")

    def check_status(self, encoding_id: str) -> dict:
        raise NotImplementedError("MediaConvertProvider.check_status() not yet implemented")

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        raise NotImplementedError("MediaConvertProvider.download() not yet implemented")

    def cleanup(self, result: EncodingResult) -> None:
        raise NotImplementedError("MediaConvertProvider.cleanup() not yet implemented")
