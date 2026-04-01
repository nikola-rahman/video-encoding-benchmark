"""Validate and trim raw samples into benchmark-ready inputs."""

import json
import shutil
import subprocess
from pathlib import Path

from tqdm import tqdm

from benchmark.samples.catalog import load_catalog, filter_catalog, find_raw_file


def probe_video(path: Path) -> dict:
    """Probe a video file with ffprobe. Raises on failure."""
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

    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    fmt = data.get("format", {})

    width = stream.get("width", 0)
    height = stream.get("height", 0)
    duration = float(fmt.get("duration", 0) or stream.get("duration", 0))

    if width == 0 or height == 0:
        raise RuntimeError(f"Invalid video dimensions ({width}x{height}) for {path}")
    if duration <= 0:
        raise RuntimeError(f"Invalid duration ({duration}s) for {path}")

    return {
        "width": width,
        "height": height,
        "codec": stream.get("codec_name", "unknown"),
        "duration": duration,
    }


def trim_video(input_path: Path, output_path: Path, start: float, duration: float) -> None:
    """Trim a video segment with ffmpeg. Raises on failure."""
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


def run(
    raw_dir: Path,
    output_dir: Path,
    verticals: list[str] | None = None,
    ids: list[str] | None = None,
):
    """Validate raw samples and prepare trimmed versions for the benchmark."""
    catalog = filter_catalog(load_catalog(), verticals, ids)
    if not catalog:
        print("No sources match the given filters.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    ready = []
    missing = []
    failed = []

    for source in tqdm(catalog, desc="Preparing", unit="video"):
        sid = source["id"]
        raw_file = find_raw_file(source, raw_dir)

        if not raw_file:
            missing.append(sid)
            continue

        try:
            probe_video(raw_file)

            trim = source.get("trim")
            out_file = output_dir / f"{sid}{raw_file.suffix}"

            if out_file.exists():
                ready.append(sid)
                continue

            if trim:
                trim_video(raw_file, out_file, trim.get("start", 0), trim.get("duration", 60))
            else:
                shutil.copy2(raw_file, out_file)

            ready.append(sid)

        except Exception as e:
            failed.append((sid, str(e)))

    print(f"\n{len(ready)} prepared, {len(missing)} missing, {len(failed)} failed")

    if missing:
        print(f"\nMissing raw files (run 'samples download' or place manually):")
        for sid in missing:
            print(f"  {sid}")

    if failed:
        for sid, err in failed:
            print(f"  FAILED: {sid}: {err}")
        raise RuntimeError(f"{len(failed)} preparation(s) failed.")
