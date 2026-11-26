"""Command-line interface for loglens."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Tuple

from .core import (
    LEVELS,
    LogEntry,
    canonical_level,
    filter_entries,
    parse_lines,
    rate_buckets,
    summarize,
    top_errors,
)


def _load(path: str) -> Tuple[Optional[List[LogEntry]], Optional[str]]:
    """Read and parse *path*; return (entries, error_message)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return None, f"loglens: error: no such file: {path}"
    except IsADirectoryError:
        return None, f"loglens: error: is a directory: {path}"
    except OSError as exc:
        return None, f"loglens: error: cannot read {path}: {exc.strerror or exc}"
    if not any(line.strip() for line in lines):
        return None, f"loglens: error: file is empty: {path}"
    return parse_lines(lines), None


def _format_ts(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else "n/a"


def cmd_summary(args: argparse.Namespace) -> int:
    entries, error = _load(args.file)
    if error:
        print(error, file=sys.stderr)
        return 2
    stats = summarize(entries)
    print(f"File: {args.file}")
    print(f"Total lines: {stats['total']}")
    if stats["first_timestamp"] is not None:
        print(
            "Time range: "
            f"{_format_ts(stats['first_timestamp'])} -> "
            f"{_format_ts(stats['last_timestamp'])}"
        )
    else:
        print("Time range: n/a (no parseable timestamps)")
    print(f"Lines with timestamps: {stats['with_timestamps']}")
    print()
    print("Levels:")
    counts = stats["level_counts"]
    for level in LEVELS:
        if counts.get(level):
            print(f"  {level:<9} {counts[level]}")
    if counts.get("UNKNOWN"):
        print(f"  {'UNKNOWN':<9} {counts['UNKNOWN']}")
    print()
    print("Top error messages:")
    if stats["top_errors"]:
        for message, count in stats["top_errors"]:
            print(f"  {count:>3} x {message}")
    else:
        print("  (none)")
    return 0


def cmd_errors(args: argparse.Namespace) -> int:
    entries, error = _load(args.file)
    if error:
        print(error, file=sys.stderr)
        return 2
    ranked = top_errors(entries, top=args.top)
    print(f"Top {args.top} error messages in {args.file}:")
    if ranked:
        for message, count in ranked:
            print(f"  {count:>3} x {message}")
    else:
        print("  (no ERROR or CRITICAL lines found)")
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    entries, error = _load(args.file)
    if error:
        print(error, file=sys.stderr)
        return 2
    level = canonical_level(args.level)
    for entry in filter_entries(entries, level):
        print(entry.raw)
    return 0


def cmd_rate(args: argparse.Namespace) -> int:
    entries, error = _load(args.file)
    if error:
        print(error, file=sys.stderr)
        return 2
    buckets = rate_buckets(entries, bucket=args.bucket)
    if not buckets:
        print("No lines with parseable timestamps.")
        return 0
    for key, count in buckets:
        bar = "#" * min(count, 50)
        print(f"{key}  {bar} {count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loglens",
        description="Analyze plain-text log files from the command line.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary = subparsers.add_parser(
        "summary", help="totals, level counts, time range, top errors"
    )
    summary.add_argument("file", help="path to the log file")
    summary.set_defaults(func=cmd_summary)

    errors = subparsers.add_parser(
        "errors", help="most frequent ERROR/CRITICAL messages, grouped"
    )
    errors.add_argument("file", help="path to the log file")
    errors.add_argument(
        "--top", type=int, default=10, help="how many messages to show (default 10)"
    )
    errors.set_defaults(func=cmd_errors)

    tail = subparsers.add_parser(
        "tail", help="print only lines at or above a given level"
    )
    tail.add_argument("file", help="path to the log file")
    tail.add_argument(
        "--level",
        default="ERROR",
        help="minimum level: DEBUG, INFO, WARNING, ERROR or CRITICAL "
        "(default ERROR; WARN is accepted for WARNING)",
    )
    tail.set_defaults(func=cmd_tail)

    rate = subparsers.add_parser(
        "rate", help="messages per time bucket based on parsed timestamps"
    )
    rate.add_argument("file", help="path to the log file")
    rate.add_argument(
        "--bucket",
        choices=["minute", "hour"],
        default="minute",
        help="bucket size (default minute)",
    )
    rate.set_defaults(func=cmd_rate)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "level", None) is not None and canonical_level(args.level) is None:
        parser.error(
            f"invalid level: {args.level!r} "
            "(choose from DEBUG, INFO, WARNING, ERROR, CRITICAL)"
        )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
