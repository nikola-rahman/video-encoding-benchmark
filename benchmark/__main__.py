"""CLI entry point: python -m benchmark <command>"""

import argparse
import sys


def _load_config(args):
    from benchmark.config import load_config
    return load_config(args.config)


def cmd_preprocess(args):
    from benchmark.steps import preprocess
    preprocess.run(_load_config(args), fix=args.fix, files=args.file)


def cmd_scan(args):
    from pathlib import Path
    from benchmark.providers.manual import ManualProvider
    from benchmark.metadata import load_metadata, save_metadata

    config = _load_config(args)
    data_dir = Path(config["data_dir"])
    metadata_path = data_dir / "metadata.json"

    provider = ManualProvider(args.provider, config)
    results = provider.scan(args.provider)

    if not results:
        print("No new outputs found.")
        return

    existing = load_metadata(metadata_path)
    registered = {(e["provider"], e["encoding_name"]) for e in existing}

    added = 0
    for r in results:
        if (r.provider, r.encoding_name) in registered:
            print(f"  Already registered: {r.encoding_name}")
            continue
        existing.append(r.to_metadata_dict())
        added += 1

    save_metadata(metadata_path, existing)
    print(f"\nDone: {added} added, {len(results) - added} already registered")


def cmd_cleanup(args):
    from benchmark.steps import cleanup
    config = _load_config(args)
    cleanup.run(config, provider_name=args.provider,
                encoding_ids=args.id, delete=args.delete,
                keep_local=args.keep_local)


def main():
    parser = argparse.ArgumentParser(prog="benchmark", description="Multi-provider video encoding benchmark")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p = subparsers.add_parser("preprocess", help="Validate and fix input videos")
    p.add_argument("--fix", action="store_true", help="Fix any issues found")
    p.add_argument("--file", nargs="*", help="Specific file(s) to check")

    p = subparsers.add_parser("scan", help="Scan manual provider outputs")
    p.add_argument("provider", help="Provider name (e.g. vidaio)")

    p = subparsers.add_parser("cleanup", help="Clean up remote and local resources")
    p.add_argument("--provider", required=True, help="Provider name")
    p.add_argument("--id", nargs="*", help="Specific encoding ID(s)")
    p.add_argument("--delete", action="store_true", help="Actually delete")
    p.add_argument("--keep-local", action="store_true", help="Keep local files")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler = {
        "preprocess": cmd_preprocess,
        "scan": cmd_scan,
        "cleanup": cmd_cleanup,
    }[args.command]

    handler(args)


if __name__ == "__main__":
    main()
