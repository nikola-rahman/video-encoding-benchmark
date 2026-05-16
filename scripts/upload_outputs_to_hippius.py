#!/usr/bin/env python3
"""Upload encoded outputs to Hippius S3.

Mirrors `data/outputs/<provider>/...` on the local/server filesystem to
`snapshots/<today>/data/outputs/<provider>/...` in the bucket configured
via env vars (see benchmark/util/s3.py). The snapshot date is in the
prefix so re-running on another day produces a separate snapshot.

You specify which providers to upload via --provider. There is no
default; nothing is uploaded unless asked.

To restore later:
    aws s3 sync s3://<bucket>/snapshots/<date>/data/outputs/ ./data/outputs/

Reliability features:
  - Resumes safely: per-file head_object check skips already-uploaded
    files (configurable via --no-skip-existing).
  - Per-file retry with exponential backoff on S3 errors.
  - tqdm progress bar with rate / ETA.
  - All work is per-file; killing the script mid-run is safe.
  - --dry-run prints what would be uploaded without doing it.

Usage:
    .venv/bin/python scripts/upload_outputs_to_hippius.py --provider ffmpeg mediaconvert zencoder
    .venv/bin/python scripts/upload_outputs_to_hippius.py --provider ffmpeg --dry-run
    .venv/bin/python scripts/upload_outputs_to_hippius.py --provider ffmpeg --root /path/to/data/outputs

Env vars required (.env or shell):
    HIPPIUS_S3_ENDPOINT
    HIPPIUS_S3_ACCESS_KEY
    HIPPIUS_S3_SECRET_KEY
    HIPPIUS_S3_BUCKET
    HIPPIUS_S3_REGION  (optional)
"""

import argparse
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from botocore.exceptions import (  # noqa: E402
    BotoCoreError,
    ClientError,
    ConnectionError as BotoConnectionError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from tqdm import tqdm

from benchmark.util.s3 import get_s3_client, get_bucket, object_exists  # noqa: E402


def default_prefix() -> str:
    return f"snapshots/{date.today().isoformat()}/data/outputs"

# Errors worth retrying. Anything else (e.g. 403 NoSuchBucket) we let bubble up.
RETRYABLE_ERROR_CODES = {
    "InternalError", "ServiceUnavailable", "SlowDown",
    "RequestTimeout", "RequestTimeoutException",
    "BadDigest", "OperationAborted",
}
RETRYABLE_EXCEPTIONS = (
    BotoConnectionError,
    EndpointConnectionError,
    ReadTimeoutError,
    BotoCoreError,
    OSError,  # broken pipe, etc.
)


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def human_time(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{s / 60:.1f}m"
    return f"{s / 3600:.1f}h"


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in RETRYABLE_ERROR_CODES
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def upload_with_retry(s3_client, local_path: Path, bucket: str, key: str,
                      max_attempts: int = 6, base_backoff: float = 2.0,
                      log=None) -> None:
    """Upload one file with exponential-backoff retry on transient errors."""
    for attempt in range(1, max_attempts + 1):
        try:
            s3_client.upload_file(str(local_path), bucket, key)
            return
        except Exception as exc:
            if not is_retryable(exc) or attempt == max_attempts:
                raise
            sleep_for = base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 1)
            if log is not None:
                log(f"retry {attempt}/{max_attempts} for {key} ({type(exc).__name__}); sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)


def collect_files(root: Path, providers: set[str]) -> list[tuple[Path, str]]:
    """Walk data/outputs/<provider>/... and return (local_path, provider) pairs
    for each provider in the given set."""
    out = []
    for provider_dir in sorted(root.iterdir()):
        if not provider_dir.is_dir() or provider_dir.name not in providers:
            continue
        for fpath in provider_dir.rglob("*"):
            if fpath.is_file():
                out.append((fpath, provider_dir.name))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", nargs="+", required=True,
                        help="Providers to upload (subdirectories of --root). "
                             "Example: --provider ffmpeg mediaconvert zencoder")
    parser.add_argument("--root", default="data/outputs",
                        help="Local outputs directory (default: data/outputs)")
    parser.add_argument("--prefix", default=None,
                        help="S3 prefix (default: snapshots/<today>/data/outputs)")
    parser.add_argument("--no-skip-existing", action="store_true",
                        help="Re-upload files even if they already exist in S3.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be uploaded; do not upload.")
    parser.add_argument("--max-attempts", type=int, default=6,
                        help="Per-file max retry attempts (default: 6).")
    args = parser.parse_args()

    if args.prefix is None:
        args.prefix = default_prefix()

    load_dotenv()

    root = Path(args.root).resolve()
    if not root.exists():
        sys.exit(f"Root directory not found: {root}")

    providers = set(args.provider)
    files_with_provider = collect_files(root, providers)

    if not files_with_provider:
        print(f"No files to upload under {root} for providers: {sorted(providers)}")
        return

    total_bytes = sum(p.stat().st_size for p, _ in files_with_provider)
    by_provider = {}
    for _, prov in files_with_provider:
        by_provider[prov] = by_provider.get(prov, 0) + 1
    print(f"Bucket:         {get_bucket() if not args.dry_run else '(dry-run, not connecting)'}")
    print(f"Local root:     {root}")
    print(f"S3 prefix:      {args.prefix}/<provider>/...")
    print(f"Files to scan:  {len(files_with_provider)}  ({human_bytes(total_bytes)})")
    for prov, n in sorted(by_provider.items()):
        print(f"  {prov:<14} {n}")
    print()

    if args.dry_run:
        for p, prov in files_with_provider[:25]:
            rel = p.relative_to(root)
            print(f"  WOULD UPLOAD  {p}  ->  s3://.../{args.prefix}/{rel.as_posix()}  ({human_bytes(p.stat().st_size)})")
        if len(files_with_provider) > 25:
            print(f"  ... and {len(files_with_provider) - 25} more files")
        print()
        print("Dry run only. Nothing uploaded.")
        return

    s3_client = get_s3_client()
    bucket = get_bucket()

    uploaded_n = skipped_n = failed_n = 0
    failures = []
    start = time.time()

    bar = tqdm(
        total=total_bytes,
        unit="B", unit_scale=True, unit_divisor=1024,
        smoothing=0.05, dynamic_ncols=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]{postfix}",
    )

    def log_warn(msg: str) -> None:
        bar.write(msg)

    for local_path, _ in files_with_provider:
        rel = local_path.relative_to(root)
        key = f"{args.prefix.rstrip('/')}/{rel.as_posix()}"
        size = local_path.stat().st_size

        try:
            if not args.no_skip_existing and object_exists(s3_client, bucket, key):
                skipped_n += 1
            else:
                upload_with_retry(s3_client, local_path, bucket, key,
                                  max_attempts=args.max_attempts, log=log_warn)
                uploaded_n += 1
        except Exception as exc:
            failed_n += 1
            failures.append((str(local_path), repr(exc)))
            bar.write(f"FAILED {key}: {type(exc).__name__}: {exc}")

        bar.update(size)
        bar.set_postfix_str(f"up={uploaded_n} skip={skipped_n} fail={failed_n}", refresh=False)

    bar.close()

    elapsed = time.time() - start
    print()
    print(f"Done in {human_time(elapsed)}.")
    print(f"  Uploaded:  {uploaded_n} files")
    print(f"  Skipped:   {skipped_n} files (already in S3)")
    print(f"  Failed:    {failed_n} files")
    if failures:
        print("\nFailures:")
        for path, err in failures:
            print(f"  {path}\n    {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
