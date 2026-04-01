"""CLI entry point: python -m benchmark <command>"""

import argparse
import sys


def _load_config(args):
    from benchmark.config import load_config
    return load_config(args.config)


def cmd_preprocess(args):
    from benchmark.steps import preprocess
    preprocess.run(_load_config(args), fix=args.fix, files=args.file)


def cmd_upload(args):
    from benchmark.steps import upload
    upload.run(_load_config(args), presign_only=args.presign_only, expires=args.expires,
               update_urls=args.update_urls, files=args.file)


def cmd_encode(args):
    from benchmark.steps import encode
    encode.run(_load_config(args), provider_name=args.provider, codec=args.codec,
               video_filter=args.video)


def cmd_poll(args):
    from benchmark.steps import poll
    config = _load_config(args)
    poll.run(config, provider_name=args.provider, watch=args.watch,
             encoding_ids=args.id, status_filter=args.status,
             all_encodings=args.all, limit=args.limit)


def cmd_download(args):
    from benchmark.steps import download
    download.run(_load_config(args), provider_name=args.provider,
                 encoding_ids=args.encoding_id, list_only=args.list)


def cmd_scan(args):
    """Scan a manual provider's output directory and add to metadata."""
    from pathlib import Path
    from benchmark.providers.manual import ManualProvider
    from benchmark.metadata import load_metadata, save_metadata

    config = _load_config(args)
    data_dir = Path(config.get("data_dir", "./data"))
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


def cmd_measure(args):
    from benchmark.steps import measure
    measure.run(_load_config(args), seed=args.seed, duration=args.duration,
                threads=args.threads, model=args.model)


def cmd_report(args):
    from benchmark.steps import report
    report.run(_load_config(args))


def cmd_export(args):
    from benchmark.steps import export
    export.run(_load_config(args), output_dir=args.output)



def cmd_cleanup(args):
    from benchmark.steps import cleanup
    config = _load_config(args)
    cleanup.run(config, provider_name=args.provider,
                encoding_ids=args.id, delete=args.delete,
                keep_local=args.keep_local)


def cmd_run(args):
    """Run the full pipeline."""
    from benchmark.util.log import setup_logging
    log = setup_logging("pipeline")

    config = _load_config(args)
    skip = set(args.skip.split(",")) if args.skip else set()
    steps = ["preprocess", "upload", "encode", "poll", "download", "measure", "report"]

    for step in steps:
        if step in skip:
            log.info(f"\nSkipping: {step}")
            continue

        log.info(f"\n{'=' * 60}")
        log.info(f"STEP: {step}")
        log.info(f"{'=' * 60}")

        if step == "preprocess":
            from benchmark.steps import preprocess
            preprocess.run(config, fix=True)
        elif step == "upload":
            from benchmark.steps import upload
            upload.run(config, update_urls=True)
        elif step == "encode":
            from benchmark.steps import encode
            encode.run(config, provider_name=args.provider)
        elif step == "poll":
            log.info("  Skipping poll in automated pipeline (use 'python -m benchmark poll --watch 30')")
        elif step == "download":
            from benchmark.steps import download
            download.run(config, provider_name=args.provider)
        elif step == "measure":
            from benchmark.steps import measure
            measure.run(config)
        elif step == "report":
            from benchmark.steps import report
            report.run(config)


def main():
    parser = argparse.ArgumentParser(prog="benchmark", description="Multi-provider video encoding benchmark")
    parser.add_argument("--config", default=None, help="Path to benchmark.yaml (default: ./benchmark.yaml)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # preprocess
    p = subparsers.add_parser("preprocess", help="Validate and fix input videos")
    p.add_argument("--fix", action="store_true", help="Fix any issues found")
    p.add_argument("--file", nargs="*", help="Specific file(s) to check")

    # upload
    p = subparsers.add_parser("upload", help="Upload inputs to S3 and presign URLs")
    p.add_argument("--file", nargs="*", help="Specific file(s)")
    p.add_argument("--presign-only", action="store_true", help="Skip upload")
    p.add_argument("--expires", type=int, default=604800, help="URL expiration in seconds")
    p.add_argument("--update-urls", action="store_true", help="Write URLs to video_urls.txt")

    # encode
    p = subparsers.add_parser("encode", help="Submit encoding jobs")
    p.add_argument("--provider", help="Provider name")
    p.add_argument("--codec", help="Codec to use (av1, h265)")
    p.add_argument("--video", help="Filter to specific video")

    # poll
    p = subparsers.add_parser("poll", help="Check encoding status")
    p.add_argument("--provider", help="Provider name")
    p.add_argument("--watch", type=int, metavar="SECONDS", help="Poll interval")
    p.add_argument("--id", nargs="*", help="Specific encoding ID(s)")
    p.add_argument("--status", choices=["created", "queued", "running", "finished", "error"])
    p.add_argument("--all", action="store_true", help="Show all encodings")
    p.add_argument("--limit", type=int, default=50, help="Max encodings to fetch")

    # download
    p = subparsers.add_parser("download", help="Download encoded outputs")
    p.add_argument("--provider", help="Provider name")
    p.add_argument("--encoding-id", nargs="*", help="Specific encoding ID(s)")
    p.add_argument("--list", action="store_true", help="List only, don't download")

    # scan
    p = subparsers.add_parser("scan", help="Scan manual provider outputs and register in metadata")
    p.add_argument("provider", help="Provider name (e.g. vidaio)")

    # measure
    p = subparsers.add_parser("measure", help="Calculate VMAF scores")
    p.add_argument("--seed", type=int, help="Random seed for sampling")
    p.add_argument("--duration", type=float, help="Sample duration in seconds")
    p.add_argument("--threads", type=int, help="VMAF threads")
    p.add_argument("--model", help="VMAF model string")

    # report
    subparsers.add_parser("report", help="Generate plots and summary tables")

    # export
    p = subparsers.add_parser("export", help="Export results to CSV for report generation")
    p.add_argument("--output", default="report/data", help="Output directory (default: report/data)")

    # cleanup
    p = subparsers.add_parser("cleanup", help="Clean up remote and local resources")
    p.add_argument("--provider", help="Provider name")
    p.add_argument("--id", nargs="*", help="Specific encoding ID(s)")
    p.add_argument("--delete", action="store_true", help="Actually delete")
    p.add_argument("--keep-local", action="store_true", help="Keep local files")

    # run (full pipeline)
    p = subparsers.add_parser("run", help="Run the full pipeline")
    p.add_argument("--provider", help="Provider name")
    p.add_argument("--skip", help="Comma-separated steps to skip")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler = {
        "preprocess": cmd_preprocess,
        "upload": cmd_upload,
        "encode": cmd_encode,
        "poll": cmd_poll,
        "download": cmd_download,
        "scan": cmd_scan,
        "measure": cmd_measure,
        "report": cmd_report,
        "export": cmd_export,
        "cleanup": cmd_cleanup,
        "run": cmd_run,
    }[args.command]

    handler(args)


if __name__ == "__main__":
    main()
