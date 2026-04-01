"""Download and prepare video samples from the catalog."""

import subprocess
from pathlib import Path

import yaml

from benchmark.samples.platforms import get_downloader
from benchmark.util.log import setup_logging

log = setup_logging("acquire")

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def validate_video(path: Path) -> dict:
    """Validate a downloaded video with ffprobe. Returns stream info or raises."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,duration,r_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr.strip()}")

    import json
    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    fmt = data.get("format", {})

    width = stream.get("width", 0)
    height = stream.get("height", 0)
    codec = stream.get("codec_name", "unknown")
    duration = float(fmt.get("duration", 0) or stream.get("duration", 0))

    if width == 0 or height == 0:
        raise RuntimeError(f"Invalid video dimensions ({width}x{height}) for {path}")
    if duration <= 0:
        raise RuntimeError(f"Invalid duration ({duration}s) for {path}")

    return {
        "width": width,
        "height": height,
        "codec": codec,
        "duration": duration,
    }


def trim_video(input_path: Path, output_path: Path, start: float, duration: float) -> Path:
    """Trim a video to a specific segment using ffmpeg."""
    if output_path.exists():
        log.info(f"  Already trimmed: {output_path.name}")
        return output_path

    log.info(f"  Trimming: {start}s + {duration}s → {output_path.name}")
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(duration),
            "-c", "copy",
            "-an",
            str(output_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed: {result.stderr.strip()}")

    return output_path


def acquire(
    output_dir: Path,
    verticals: list[str] | None = None,
    ids: list[str] | None = None,
    skip_trim: bool = False,
):
    """Download and prepare samples from the catalog.

    Args:
        output_dir: Where to save downloaded and trimmed videos.
        verticals: Filter to specific verticals (e.g., ["ecommerce", "ugc"]).
        ids: Filter to specific source IDs.
        skip_trim: If True, download only (no trimming).
    """
    catalog = load_catalog()

    # Filter
    if verticals:
        catalog = [s for s in catalog if s["vertical"] in verticals]
    if ids:
        catalog = [s for s in catalog if s["id"] in ids]

    if not catalog:
        raise ValueError("No sources match the given filters")

    log.info(f"Acquiring {len(catalog)} videos...")

    raw_dir = output_dir / "raw"
    trimmed_dir = output_dir / "trimmed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    trimmed_dir.mkdir(parents=True, exist_ok=True)

    succeeded = []
    failed = []

    for source in catalog:
        sid = source["id"]
        platform = source["platform"]
        log.info(f"\n[{sid}] {source['name']} ({platform})")

        try:
            # Download
            downloader = get_downloader(platform)
            downloader.validate_config(source)
            raw_path = downloader.download(source, raw_dir / sid)

            # Validate
            info = validate_video(raw_path)
            log.info(f"  Validated: {info['width']}x{info['height']}, {info['codec']}, {info['duration']:.1f}s")

            # Trim
            trim = source.get("trim")
            if trim and not skip_trim:
                start = trim.get("start", 0)
                duration = trim.get("duration", 60)
                trimmed_path = trim_video(
                    raw_path,
                    trimmed_dir / f"{sid}{raw_path.suffix}",
                    start,
                    duration,
                )
                trim_info = validate_video(trimmed_path)
                log.info(f"  Trimmed: {trim_info['duration']:.1f}s")

            succeeded.append(sid)

        except Exception as e:
            log.error(f"  FAILED: {e}")
            failed.append((sid, str(e)))

    # Summary
    log.info(f"\n{'=' * 60}")
    log.info(f"ACQUISITION SUMMARY")
    log.info(f"{'=' * 60}")
    log.info(f"  Succeeded: {len(succeeded)}")
    log.info(f"  Failed:    {len(failed)}")

    if failed:
        log.error(f"\nFailed downloads:")
        for sid, err in failed:
            log.error(f"  {sid}: {err}")
        raise RuntimeError(f"{len(failed)} download(s) failed. See errors above.")

    log.info(f"\nAll {len(succeeded)} videos acquired successfully.")
    log.info(f"  Raw:     {raw_dir}/")
    log.info(f"  Trimmed: {trimmed_dir}/")
