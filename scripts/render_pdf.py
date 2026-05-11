#!/usr/bin/env python3
"""Render a markdown report to PDF via md2pdf (weasyprint).

Usage:
    .venv/bin/python scripts/render_pdf.py [input.md] [output.pdf]

Defaults: report/output/latest/report.md -> report/output/latest/report.pdf
"""

import sys
from pathlib import Path

from md2pdf.core import md2pdf

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "report" / "output" / "latest" / "report.md"


def main():
    md_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    pdf_path = Path(sys.argv[2]) if len(sys.argv) > 2 else md_path.with_suffix(".pdf")

    if not md_path.exists():
        sys.exit(f"Not found: {md_path}")

    md2pdf(pdf_path, md=md_path, base_url=md_path.parent)
    size = pdf_path.stat().st_size
    print(f"Wrote {pdf_path} ({size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
