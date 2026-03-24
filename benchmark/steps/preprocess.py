"""Validate and fix input videos before benchmarking."""

import sys
from pathlib import Path

from benchmark.util.ffmpeg import check_video, fix_video
from benchmark.util.log import setup_logging

log = setup_logging("preprocess")


def run(config: dict, fix: bool = False, files: list[str] | None = None):
    """Run the preprocess step."""
    inputs_dir = Path(config.get("inputs", {}).get("dir", "./data/inputs"))

    if files:
        video_files = [Path(f) for f in files]
    else:
        if not inputs_dir.exists():
            log.error(f"Inputs directory not found: {inputs_dir}")
            sys.exit(1)
        video_files = sorted(inputs_dir.glob("*.mp4"))

    if not video_files:
        log.info("No video files found.")
        return

    all_ok = True
    for f in video_files:
        log.info(f"\nChecking: {f.name}")
        try:
            issues, info = check_video(f)
        except Exception as e:
            log.error(f"  Error: {e}")
            all_ok = False
            continue

        if not issues:
            log.info(f"  OK")
            continue

        all_ok = False
        for issue in issues:
            log.warning(f"  ISSUE [{issue['type']}]: {issue['message']}")

        if fix:
            log.info(f"  Fixing...")
            try:
                fix_video(f, issues)
                issues_after, _ = check_video(f)
                if issues_after:
                    for issue in issues_after:
                        log.error(f"  Still broken [{issue['type']}]: {issue['message']}")
                else:
                    log.info(f"  Verified: all issues fixed")
            except Exception as e:
                log.error(f"  Fix failed: {e}")

    if all_ok:
        log.info("\nAll inputs OK.")
    elif not fix:
        log.info("\nIssues found. Run with --fix to resolve them.")
