"""CLI entry point for hallubib."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__, cache
from .config import configure
from .csl import to_csl
from .output import format_markdown, format_stdout, write_html_and_open
from .parser import parse_file
from .serialize import results_to_dict
from .verify import check_references


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hallubib",
        description="Check bibliography references against online sources.",
    )
    parser.add_argument("file", nargs="?", type=Path, help=".bib or .tex file to check")
    parser.add_argument(
        "--output",
        choices=["stdout", "md", "html", "json", "csl"],
        default="stdout",
        help="output format (default: stdout); csl converts without checking",
    )
    parser.add_argument(
        "--mailto",
        help="contact email sent to polite API pools (or set HALLUBIB_MAILTO)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="clear the cache and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"hallubib {__version__}",
    )
    args = parser.parse_args(argv)

    if args.clear_cache:
        cache.clear()
        print("Cache cleared.")
        return 0

    if args.file is None:
        parser.error("a .bib or .tex file is required (unless --clear-cache)")

    if args.mailto:
        configure(mailto=args.mailto)

    path: Path = args.file
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        return 1
    if path.suffix not in (".bib", ".tex"):
        print(
            f"Error: unsupported file type {path.suffix}, expected .bib or .tex",
            file=sys.stderr,
        )
        return 1

    refs = parse_file(path)
    if not refs:
        print(f"No references found in {path}")
        return 0

    if args.output == "csl":
        print(json.dumps([to_csl(r) for r in refs], ensure_ascii=False, indent=2))
        return 0

    print(f"Checking {len(refs)} references...", file=sys.stderr)
    results = check_references(refs)

    if args.output == "stdout":
        print(format_stdout(results, path.name))
    elif args.output == "md":
        print(format_markdown(results, path.name))
    elif args.output == "json":
        print(json.dumps(results_to_dict(results), ensure_ascii=False, indent=2))
    elif args.output == "html":
        out = write_html_and_open(results, path.name)
        print(f"Report written to {out}", file=sys.stderr)

    return 0
