#!/usr/bin/env python3
"""Download video samples from catalog.yaml using ffmpeg."""

import subprocess
from pathlib import Path

import yaml
from tqdm import tqdm

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"
DEFAULT_OUTPUT_DIR = Path("data/samples/raw")


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name",
         "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")

    import json
    data = json.loads(result.stdout)
    s = data.get("streams", [{}])[0]
    fmt = data.get("format", {})
    return {
        "width": s.get("width", 0),
        "height": s.get("height", 0),
        "codec": s.get("codec_name", "unknown"),
        "duration": float(fmt.get("duration", 0)),
    }


def download(url: str, output_path: Path) -> None:
    """Download a video URL to mp4 using ffmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", url, "-c", "copy", str(output_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[:500]}")


def run(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    verticals: list[str] | None = None,
    ids: list[str] | None = None,
):
    catalog = load_catalog()

    if verticals:
        catalog = [s for s in catalog if s["vertical"] in verticals]
    if ids:
        catalog = [s for s in catalog if s["id"] in ids]

    if not catalog:
        print("No sources match filters.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    succeeded = []
    failed = []

    for source in tqdm(catalog, desc="Downloading", unit="video"):
        sid = source["id"]
        url = source.get("url")
        output_file = output_dir / f"{sid}.mp4"

        if output_file.exists():
            succeeded.append(sid)
            continue

        if not url:
            failed.append((sid, "missing url"))
            continue

        try:
            download(url, output_file)
            info = probe_video(output_file)
            tqdm.write(f"  {sid}: {info['width']}x{info['height']} {info['duration']:.0f}s")
            succeeded.append(sid)
        except Exception as e:
            output_file.unlink(missing_ok=True)
            failed.append((sid, str(e)))

    print(f"\n{len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        for sid, err in failed:
            print(f"  FAILED {sid}: {err}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download video samples from catalog")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--vertical", nargs="*")
    parser.add_argument("--id", nargs="*")
    args = parser.parse_args()
    run(output_dir=args.output, verticals=args.vertical, ids=args.id)
