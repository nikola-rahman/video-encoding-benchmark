"""Download samples that have automated downloaders."""

from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from benchmark.samples.catalog import load_catalog, filter_catalog, find_raw_file
from benchmark.samples.downloaders import get_downloader, is_downloadable

load_dotenv()


def run(raw_dir: Path, verticals: list[str] | None = None, ids: list[str] | None = None):
    catalog = filter_catalog(load_catalog(), verticals, ids)
    downloadable = [s for s in catalog if is_downloadable(s["platform"])]
    manual = [s for s in catalog if not is_downloadable(s["platform"])]

    if not downloadable and not manual:
        print("No sources match the given filters.")
        return

    if manual:
        print(f"\nManual download required ({len(manual)}):")
        for source in manual:
            url = source.get("url", "see dataset documentation")
            notes = source.get("notes", "")
            print(f"  [{source['id']}] {source['name']}")
            print(f"    URL: {url}")
            if notes:
                print(f"    Notes: {notes}")
            print(f"    Save as: {raw_dir}/{source['id']}.mp4")
        print()

    if not downloadable:
        return

    raw_dir.mkdir(parents=True, exist_ok=True)

    succeeded = []
    failed = []

    for source in tqdm(downloadable, desc="Downloading", unit="video"):
        sid = source["id"]

        if find_raw_file(source, raw_dir):
            succeeded.append(sid)
            continue

        try:
            downloader = get_downloader(source["platform"])
            downloader.download(source, raw_dir / sid)
            succeeded.append(sid)
        except Exception as e:
            failed.append((sid, str(e)))

    print(f"\n{len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        for sid, err in failed:
            print(f"  FAILED: {sid}: {err}")
        raise RuntimeError(f"{len(failed)} download(s) failed.")
