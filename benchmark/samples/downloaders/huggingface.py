"""HuggingFace datasets downloader."""

import shutil
from pathlib import Path

from benchmark.samples.downloaders.base import Downloader


class HuggingFaceDownloader(Downloader):
    name = "huggingface"

    def download(self, source: dict, output_path: Path) -> Path:
        from huggingface_hub import hf_hub_download

        repo_id = source.get("repo_id")
        filename = source.get("filename")
        if not repo_id:
            raise ValueError(f"Source {source['id']} missing 'repo_id'")
        if not filename:
            raise ValueError(f"Source {source['id']} missing 'filename'")

        output_file = output_path.with_suffix(Path(filename).suffix)
        if output_file.exists():
            return output_file

        cached_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type="dataset",
        )
        shutil.copy2(cached_path, output_file)
        return output_file
