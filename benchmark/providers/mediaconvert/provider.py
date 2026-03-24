"""AWS MediaConvert provider."""

from pathlib import Path

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.log import setup_logging

log = setup_logging("mediaconvert")


class MediaConvertProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config.get("providers", {}).get("mediaconvert", {})
        self.region = self.provider_config.get("region", "us-east-1")
        self.role_arn = self.provider_config.get("role_arn", "")
        self.queue_arn = self.provider_config.get("queue_arn", "")
        self.s3_output_bucket = self.provider_config.get("s3_output_bucket", "")
        self.s3_output_prefix = self.provider_config.get("s3_output_prefix", "benchmark-outputs/")

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        raise NotImplementedError("MediaConvertProvider.get_results() not yet implemented")

    def check_status(self, encoding_id: str) -> dict:
        raise NotImplementedError("MediaConvertProvider.check_status() not yet implemented")

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        raise NotImplementedError("MediaConvertProvider.download() not yet implemented")

    def cleanup(self, result: EncodingResult) -> None:
        raise NotImplementedError("MediaConvertProvider.cleanup() not yet implemented")
