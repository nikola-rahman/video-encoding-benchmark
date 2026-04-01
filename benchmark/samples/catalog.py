"""Load and query the sample catalog."""

from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg"}


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def filter_catalog(
    catalog: list[dict],
    verticals: list[str] | None = None,
    ids: list[str] | None = None,
) -> list[dict]:
    if verticals:
        catalog = [s for s in catalog if s["vertical"] in verticals]
    if ids:
        catalog = [s for s in catalog if s["id"] in ids]
    return catalog


def find_raw_file(source: dict, raw_dir: Path) -> Path | None:
    """Find a raw file matching a catalog source, regardless of how it got there."""
    sid = source["id"]
    for ext in VIDEO_EXTENSIONS:
        candidate = raw_dir / f"{sid}{ext}"
        if candidate.exists():
            return candidate

    filename = source.get("filename")
    if filename:
        candidate = raw_dir / filename
        if candidate.exists():
            return candidate

    return None
