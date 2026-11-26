import unittest
from datetime import datetime

from loglens.core import (
    canonical_level,
    filter_entries,
    level_counts,
    normalize_message,
    parse_line,
    parse_lines,
    parse_timestamp,
    rate_buckets,
    summarize,
    top_errors,
)

SAMPLE_LINES = [
    "2026-01-01 08:00:01 INFO service started",
    "2026-01-01 08:00:02 DEBUG cache warmup",
    "2026-01-01 08:01:00 WARN disk almost full",
    "2026-01-01 08:02:00 WARNING disk almost full",
    "2026-01-01 08:03:00 ERROR Connection failed after 3 retries (id=111)",
    "2026-01-01 08:04:00 ERROR Connection failed after 5 retries (id=222)",
    "2026-01-01 08:05:00 CRITICAL Out of memory",
    "a plain line with nothing to parse",
]


class TestLevelParsing(unittest.TestCase):
    def test_canonical_levels(self):
        self.assertEqual(parse_line("2026-01-01 08:00:01 INFO ok").level, "INFO")
        self.assertEqual(parse_line("2026-01-01 08:00:01 ERROR bad").level, "ERROR")
        self.assertEqual(
            parse_line("2026-01-01 08:00:01 CRITICAL boom").level, "CRITICAL"
        )

    def test_level_is_case_insensitive(self):
        self.assertEqual(parse_line("2026-01-01 08:00:01 error bad").level, "ERROR")
        self.assertEqual(parse_line("2026-01-01 08:00:01 Info ok").level, "INFO")

    def test_warn_alias_maps_to_warning(self):
        self.assertEqual(parse_line("2026-01-01 08:00:01 WARN slow").level, "WARNING")
        self.assertEqual(canonical_level("warn"), "WARNING")
        self.assertIsNone(canonical_level("NOPE"))

    def test_line_without_level(self):
        entry = parse_line("just some text")
        self.assertIsNone(entry.level)
        self.assertEqual(entry.message, "just some text")

    def test_message_extraction(self):
        entry = parse_line("2026-01-01 08:00:01 ERROR - something broke")
        self.assertEqual(entry.message, "something broke")

    def test_level_counts(self):
        counts = level_counts(parse_lines(SAMPLE_LINES))
        self.assertEqual(counts["INFO"], 1)
        self.assertEqual(counts["DEBUG"], 1)
        self.assertEqual(counts["WARNING"], 2)  # WARN + WARNING
        self.assertEqual(counts["ERROR"], 2)
        self.assertEqual(counts["CRITICAL"], 1)
        self.assertEqual(counts["UNKNOWN"], 1)


class TestTimestampParsing(unittest.TestCase):
    def test_space_separated(self):
        self.assertEqual(
            parse_timestamp("2026-01-01 12:00:00 INFO x"),
            datetime(2026, 1, 1, 12, 0, 0),
        )

    def test_iso8601_with_fraction_and_zulu(self):
        self.assertEqual(
            parse_timestamp("2026-01-01T12:00:00.500Z INFO x"),
            datetime(2026, 1, 1, 12, 0, 0, 500000),
        )

    def test_iso8601_with_offset_is_converted_to_utc(self):
        self.assertEqual(
            parse_timestamp("2026-01-01T14:30:00+02:30 INFO x"),
            datetime(2026, 1, 1, 12, 0, 0),
        )

    def test_comma_fraction(self):
        self.assertEqual(
            parse_timestamp("2026-01-01 12:00:00,250 INFO x"),
            datetime(2026, 1, 1, 12, 0, 0, 250000),
        )

    def test_syslog_style(self):
        parsed = parse_timestamp("Jan  1 12:00:00 myhost app: started")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.month, parsed.day, parsed.hour), (1, 1, 12))

    def test_no_timestamp(self):
        self.assertIsNone(parse_timestamp("INFO no time here"))
        self.assertIsNone(parse_timestamp(""))


class TestNormalizeAndErrors(unittest.TestCase):
    def test_digits_are_masked(self):
        self.assertEqual(
            normalize_message("Connection failed after 3 retries (id=8812)"),
            "Connection failed after # retries (id=#)",
        )

    def test_uuid_and_ip_are_masked(self):
        self.assertEqual(
            normalize_message("request 550e8400-e29b-41d4-a716-446655440000 from 10.0.0.7"),
            "request # from #",
        )

    def test_similar_errors_group_together(self):
        entries = parse_lines(SAMPLE_LINES)
        ranked = top_errors(entries)
        self.assertEqual(ranked[0], ("Connection failed after # retries (id=#)", 2))
        self.assertIn(("Out of memory", 1), ranked)

    def test_hex_like_ids_group_together(self):
        entries = parse_lines(
            [
                "2026-01-01 08:00:00 ERROR Timeout calling API (request 5f3a21)",
                "2026-01-01 08:01:00 ERROR Timeout calling API (request 77bc90)",
                "2026-01-01 08:02:00 ERROR Timeout calling API (request 91de02)",
            ]
        )
        self.assertEqual(
            top_errors(entries), [("Timeout calling API (request #)", 3)]
        )

    def test_top_limit(self):
        entries = parse_lines(SAMPLE_LINES)
        self.assertEqual(len(top_errors(entries, top=1)), 1)


class TestRateBuckets(unittest.TestCase):
    def test_minute_buckets(self):
        entries = parse_lines(
            [
                "2026-01-01 08:00:01 INFO a",
                "2026-01-01 08:00:45 INFO b",
                "2026-01-01 08:01:10 INFO c",
                "no timestamp INFO d",
            ]
        )
        self.assertEqual(
            rate_buckets(entries, "minute"),
            [("2026-01-01 08:00", 2), ("2026-01-01 08:01", 1)],
        )

    def test_hour_buckets(self):
        entries = parse_lines(
            [
                "2026-01-01 08:15:00 INFO a",
                "2026-01-01 08:45:00 INFO b",
                "2026-01-01 09:05:00 INFO c",
            ]
        )
        self.assertEqual(
            rate_buckets(entries, "hour"),
            [("2026-01-01 08:00", 2), ("2026-01-01 09:00", 1)],
        )

    def test_invalid_bucket(self):
        with self.assertRaises(ValueError):
            rate_buckets([], "day")


class TestFilterAndSummary(unittest.TestCase):
    def test_filter_at_or_above_error(self):
        entries = parse_lines(SAMPLE_LINES)
        kept = filter_entries(entries, "ERROR")
        self.assertEqual([e.level for e in kept], ["ERROR", "ERROR", "CRITICAL"])

    def test_filter_at_or_above_warning_includes_warn_alias(self):
        entries = parse_lines(SAMPLE_LINES)
        kept = filter_entries(entries, "WARNING")
        self.assertEqual(len(kept), 5)  # 2 WARNING + 2 ERROR + 1 CRITICAL

    def test_summarize(self):
        stats = summarize(parse_lines(SAMPLE_LINES))
        self.assertEqual(stats["total"], 8)
        self.assertEqual(stats["with_timestamps"], 7)
        self.assertEqual(stats["first_timestamp"], datetime(2026, 1, 1, 8, 0, 1))
        self.assertEqual(stats["last_timestamp"], datetime(2026, 1, 1, 8, 5, 0))


if __name__ == "__main__":
    unittest.main()
