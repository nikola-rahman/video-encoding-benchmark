"""Metadata and VMAF results read/write."""

import json
from pathlib import Path


def load_metadata(path: Path) -> list[dict]:
    """Load metadata.json, returning empty list if file doesn't exist."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_metadata(path: Path, entries: list[dict]) -> None:
    """Write metadata entries to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2, default=str)


def merge_metadata(existing: list[dict], new: list[dict], provider: str) -> list[dict]:
    """Merge new entries into existing metadata, replacing entries from the same provider."""
    other_providers = [e for e in existing if e.get("provider") != provider]
    return new + other_providers


def load_vmaf_results(path: Path) -> list[dict]:
    """Load vmaf_results.json, returning empty list if file doesn't exist."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_vmaf_results(path: Path, results: list[dict]) -> None:
    """Write VMAF results to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
