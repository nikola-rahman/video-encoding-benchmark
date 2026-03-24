"""Mux video encoding provider."""

from pathlib import Path

from benchmark.providers.base import Provider, EncodingResult, Rendition
from benchmark.util.log import setup_logging

log = setup_logging("mux")


class MuxProvider(Provider):
    capabilities = {"submit", "poll", "download", "cleanup"}

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.provider_config = config.get("providers", {}).get("mux", {})
        self.token_id = self.provider_config.get("token_id", "")
        self.token_secret = self.provider_config.get("token_secret", "")

    def get_results(self, input_file: Path, codec: str, **kwargs) -> list[EncodingResult]:
        raise NotImplementedError("MuxProvider.get_results() not yet implemented")

    def check_status(self, encoding_id: str) -> dict:
        raise NotImplementedError("MuxProvider.check_status() not yet implemented")

    def download(self, result: EncodingResult, output_dir: Path) -> EncodingResult:
        raise NotImplementedError("MuxProvider.download() not yet implemented")

    def cleanup(self, result: EncodingResult) -> None:
        raise NotImplementedError("MuxProvider.cleanup() not yet implemented")
