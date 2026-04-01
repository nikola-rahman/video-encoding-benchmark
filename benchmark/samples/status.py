"""Show sample collection status."""

from pathlib import Path

from benchmark.samples.catalog import load_catalog, filter_catalog, find_raw_file
from benchmark.samples.downloaders import is_downloadable


def run(raw_dir: Path, verticals: list[str] | None = None, ids: list[str] | None = None):
    catalog = filter_catalog(load_catalog(), verticals, ids)
    if not catalog:
        print("No sources match the given filters.")
        return

    ready = []
    missing_auto = []
    missing_manual = []

    for source in catalog:
        raw_file = find_raw_file(source, raw_dir)
        if raw_file:
            ready.append((source, raw_file))
        elif is_downloadable(source["platform"]):
            missing_auto.append(source)
        else:
            missing_manual.append(source)

    print(f"Samples: {len(ready)} ready, {len(missing_auto)} downloadable, {len(missing_manual)} manual\n")

    if ready:
        print(f"Ready ({len(ready)}):")
        for source, path in ready:
            print(f"  [{source['id']}] {path.name}")

    if missing_auto:
        print(f"\nMissing — auto-downloadable ({len(missing_auto)}):")
        for source in missing_auto:
            print(f"  [{source['id']}] {source['name']} ({source['platform']})")
        print(f"\nRun: python -m benchmark samples download")

    if missing_manual:
        print(f"\nMissing — manual download ({len(missing_manual)}):")
        for source in missing_manual:
            url = source.get("url", "see dataset documentation")
            notes = source.get("notes", "")
            print(f"  [{source['id']}] {source['name']}")
            print(f"    URL: {url}")
            if notes:
                print(f"    Notes: {notes}")
            print(f"    Save as: {raw_dir}/{source['id']}.mp4")
