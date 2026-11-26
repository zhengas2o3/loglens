"""Core parsing and analysis routines for loglens."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LEVEL_ORDER = {name: index for index, name in enumerate(LEVELS)}
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL", "ERR": "ERROR"}

_LEVEL_RE = re.compile(
    r"\b(DEBUG|INFO|WARNING|WARN|ERROR|ERR|CRITICAL|FATAL)\b", re.IGNORECASE
)

# 2026-01-01T12:00:00 / 2026-01-01 12:00:00,123 / ...+02:00 / ...Z
_ISO_TS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})"
    r"(?:[.,](\d+))?"
    r"(Z|[+-]\d{2}:?\d{2})?"
)
# Jan  1 12:00:00 (syslog)
_SYSLOG_TS_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+"
    r"(\d{2}):(\d{2}):(\d{2})\b"
)
_MONTHS = {
    name: index + 1
    for index, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
# Hex-like identifiers such as 5f3a21 or 77bc90: 4+ hex chars with a digit.
_HEX_TOKEN_RE = re.compile(r"\b(?=[0-9a-fA-F]{4,}\b)(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{4,}\b")
_DIGITS_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")


def canonical_level(name: str) -> Optional[str]:
    """Return the canonical level name for *name*, or None if unknown."""
    upper = name.upper()
    if upper in LEVEL_ORDER:
        return upper
    return _LEVEL_ALIASES.get(upper)


@dataclass
class LogEntry:
    """One parsed log line."""

    raw: str
    timestamp: Optional[datetime]
    level: Optional[str]  # canonical level name, or None when not found
    message: str


def parse_timestamp(text: str) -> Optional[datetime]:
    """Find and parse the first timestamp in *text*.

    Supports ISO 8601 (``2026-01-01T12:00:00``, optional fractional seconds
    and timezone), ``2026-01-01 12:00:00`` and syslog style
    (``Jan  1 12:00:00``, current year assumed).  Timezone-aware results are
    converted to naive UTC so values are always comparable.  Returns None
    when no timestamp can be parsed.
    """
    match = _ISO_TS_RE.search(text)
    if match:
        date_part, time_part, frac, tz = match.groups()
        candidate = f"{date_part}T{time_part}"
        if frac:
            candidate += "." + frac
        if tz:
            if tz == "Z":
                candidate += "+00:00"
            elif len(tz) == 5:  # +0000 -> +00:00
                candidate += tz[:3] + ":" + tz[3:]
            else:
                candidate += tz
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
    match = _SYSLOG_TS_RE.search(text)
    if match:
        month_name, day, hour, minute, second = match.groups()
        try:
            return datetime(
                datetime.now().year,
                _MONTHS[month_name],
                int(day),
                int(hour),
                int(minute),
                int(second),
            )
        except ValueError:
            return None
    return None


def parse_line(line: str) -> LogEntry:
    """Parse a single raw log line into a :class:`LogEntry`."""
    timestamp = parse_timestamp(line)
    level = None
    message = line.strip()
    match = _LEVEL_RE.search(line)
    if match:
        level = canonical_level(match.group(1))
        rest = line[match.end():].strip(" \t:|-]")
        if rest:
            message = rest
    return LogEntry(raw=line, timestamp=timestamp, level=level, message=message)


def parse_lines(lines: Iterable[str]) -> List[LogEntry]:
    """Parse an iterable of raw lines, skipping blank lines."""
    return [parse_line(line) for line in lines if line.strip()]


def normalize_message(message: str) -> str:
    """Normalise a message so similar messages group together.

    UUIDs, IP addresses, hex literals and every run of digits are replaced
    by ``#`` and whitespace is collapsed.
    """
    text = _UUID_RE.sub("#", message)
    text = _IP_RE.sub("#", text)
    text = _HEX_RE.sub("#", text)
    text = _HEX_TOKEN_RE.sub("#", text)
    text = _DIGITS_RE.sub("#", text)
    return _WS_RE.sub(" ", text).strip()


def level_counts(entries: Iterable[LogEntry]) -> Counter:
    """Count entries per canonical level (``UNKNOWN`` when no level found)."""
    return Counter(entry.level or "UNKNOWN" for entry in entries)


def top_errors(entries: Iterable[LogEntry], top: int = 10) -> List[Tuple[str, int]]:
    """Most frequent normalised ERROR/CRITICAL messages, with counts."""
    counter = Counter(
        normalize_message(entry.message)
        for entry in entries
        if entry.level in ("ERROR", "CRITICAL")
    )
    return counter.most_common(top)


def filter_entries(entries: Iterable[LogEntry], min_level: str) -> List[LogEntry]:
    """Entries whose level is at or above *min_level* (canonical name)."""
    threshold = LEVEL_ORDER[min_level]
    return [
        entry
        for entry in entries
        if entry.level is not None and LEVEL_ORDER[entry.level] >= threshold
    ]


def rate_buckets(
    entries: Iterable[LogEntry], bucket: str = "minute"
) -> List[Tuple[str, int]]:
    """Count timestamped entries per minute or hour bucket, sorted by time."""
    if bucket not in ("minute", "hour"):
        raise ValueError(f"unknown bucket: {bucket!r} (expected 'minute' or 'hour')")
    counter: Counter = Counter()
    for entry in entries:
        if entry.timestamp is None:
            continue
        if bucket == "minute":
            key = entry.timestamp.strftime("%Y-%m-%d %H:%M")
        else:
            key = entry.timestamp.strftime("%Y-%m-%d %H:00")
        counter[key] += 1
    return sorted(counter.items())


def summarize(entries: List[LogEntry]) -> dict:
    """Summary statistics for a list of entries."""
    timestamps = [e.timestamp for e in entries if e.timestamp is not None]
    return {
        "total": len(entries),
        "level_counts": level_counts(entries),
        "with_timestamps": len(timestamps),
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "top_errors": top_errors(entries, top=5),
    }
