#!/usr/bin/env python3
"""Stream tar of data/outputs/<provider>/ straight to Hippius S3.

Avoids per-file overhead by piping a single tar stream through boto3's
multipart upload. Much faster than per-file PUTs when most files are small.

Usage:
    .venv/bin/python scripts/upload_outputs_tar.py --provider ffmpeg mediaconvert zencoder bitmovin vidaio

Output keys:
    snapshots/<today>/data/outputs/<provider>.tar

Restore:
    aws s3 cp s3://<bucket>/snapshots/<date>/data/outputs/<provider>.tar - | tar -xf - -C data/outputs/
"""

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from boto3.s3.transfer import TransferConfig  # noqa: E402

from benchmark.util.s3 import get_s3_client, get_bucket  # noqa: E402

load_dotenv()


def default_prefix() -> str:
    return f"snapshots/{date.today().isoformat()}/data/outputs"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", nargs="+", required=True)
    ap.add_argument("--root", default="data/outputs")
    ap.add_argument("--prefix", default=None)
    args = ap.parse_args()

    if args.prefix is None:
        args.prefix = default_prefix()

    root = Path(args.root).resolve()
    if not root.exists():
        sys.exit(f"Root not found: {root}")

    s3 = get_s3_client()
    bucket = get_bucket()
    cfg = TransferConfig(multipart_chunksize=64 * 1024 * 1024, max_concurrency=10)

    for prov in args.provider:
        prov_dir = root / prov
        if not prov_dir.is_dir():
            print(f"  skip {prov}: not a directory")
            continue
        key = f"{args.prefix.rstrip('/')}/{prov}.tar"
        print(f"streaming tar -> s3://{bucket}/{key}")
        proc = subprocess.Popen(
            ["tar", "-cf", "-", "-C", str(root), prov],
            stdout=subprocess.PIPE,
            bufsize=64 * 1024 * 1024,
        )
        try:
            s3.upload_fileobj(proc.stdout, bucket, key, Config=cfg)
        finally:
            proc.stdout.close()
            proc.wait()
        if proc.returncode != 0:
            sys.exit(f"tar failed for {prov} (exit {proc.returncode})")
        print(f"  done {prov}")


if __name__ == "__main__":
    main()
