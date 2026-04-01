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


def download_ffmpeg(url: str, output_path: Path) -> None:
    """Download using ffmpeg — for m3u8 and other streaming URLs."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", url, "-c", "copy", str(output_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")


def download_http(url: str, output_path: Path) -> None:
    """Direct HTTP download — preserves original file format."""
    import requests
    from tqdm import tqdm as tqdm_bar

    # Use original file extension from URL
    ext = Path(url.split("?")[0].split("/")[-1]).suffix or ".mp4"
    output_path = output_path.with_suffix(ext)

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(output_path, "wb") as f, tqdm_bar(
        total=total, unit="B", unit_scale=True, desc=output_path.name, leave=False,
    ) as bar:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            bar.update(len(chunk))


def download_ytdlp(url: str, output_path: Path) -> None:
    result = subprocess.run(
        ["yt-dlp", "--merge-output-format", "mp4", "-o", str(output_path), url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()[:500]}")


METHODS = {
    "ffmpeg": download_ffmpeg,
    "http": download_http,
    "yt-dlp": download_ytdlp,
}


def run(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    verticals: list[str] | None = None,
    ids: list[str] | None = None,
    force: bool = False,
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

        if not force and list(output_dir.glob(f"{sid}.*")):
            succeeded.append(sid)
            continue

        if not url:
            failed.append((sid, "missing url"))
            continue

        method = source.get("method", "ffmpeg")
        dl_fn = METHODS.get(method)
        if not dl_fn:
            failed.append((sid, f"unknown method: {method}"))
            continue

        try:
            dl_fn(url, output_file)
            # Find the actual file (extension may differ from .mp4)
            downloaded = list(output_dir.glob(f"{sid}.*"))
            if not downloaded:
                raise RuntimeError(f"Download produced no file for {sid}")
            info = probe_video(downloaded[0])
            tqdm.write(f"  {sid}: {info['width']}x{info['height']} {info['duration']:.0f}s")
            succeeded.append(sid)
        except Exception as e:
            for f in output_dir.glob(f"{sid}.*"):
                f.unlink()
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
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()
    run(output_dir=args.output, verticals=args.vertical, ids=args.id, force=args.force)
