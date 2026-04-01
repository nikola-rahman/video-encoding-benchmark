"""HuggingFace datasets downloader."""

from pathlib import Path

from benchmark.samples.platforms.base import Downloader
from benchmark.util.log import setup_logging

log = setup_logging("huggingface")


class HuggingFaceDownloader(Downloader):
    name = "huggingface"

    def download(self, source: dict, output_path: Path) -> Path:
        from huggingface_hub import hf_hub_download

        repo_id = source.get("repo_id")
        filename = source.get("filename")
        if not repo_id:
            raise ValueError(f"Source {source.get('id')} missing 'repo_id'")
        if not filename:
            raise ValueError(f"Source {source.get('id')} missing 'filename'")

        output_file = output_path.with_suffix(Path(filename).suffix)
        if output_file.exists():
            log.info(f"  Already downloaded: {output_file.name}")
            return output_file

        log.info(f"  Downloading from HuggingFace: {repo_id}/{filename}")
        downloaded_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type="dataset",
        )

        # Copy from HF cache to our output path
        import shutil
        shutil.copy2(downloaded_path, output_file)

        log.info(f"  Saved: {output_file} ({output_file.stat().st_size / (1024*1024):.1f} MB)")
        return output_file
