"""Cloudflare Stream provider."""

from pathlib import Path

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.log import setup_logging

log = setup_logging("cloudflare")


class CloudflareProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config.get("providers", {}).get("cloudflare", {})
        self.account_id = self.provider_config.get("account_id", "")
        self.api_token = self.provider_config.get("api_token", "")

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        raise NotImplementedError("CloudflareProvider.get_results() not yet implemented")

    def check_status(self, encoding_id: str) -> dict:
        raise NotImplementedError("CloudflareProvider.check_status() not yet implemented")

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        raise NotImplementedError("CloudflareProvider.download() not yet implemented")

    def cleanup(self, result: EncodingResult) -> None:
        raise NotImplementedError("CloudflareProvider.cleanup() not yet implemented")
