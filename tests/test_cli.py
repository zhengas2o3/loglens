import contextlib
import io
import os
import tempfile
import unittest

from loglens.cli import main

SAMPLE_LOG = """\
2026-01-01 08:00:01 INFO service started
2026-01-01 08:00:30 INFO user 42 logged in
2026-01-01 08:01:00 ERROR Connection failed after 3 retries (id=111)
2026-01-01 08:02:00 ERROR Connection failed after 9 retries (id=999)
2026-01-01 08:03:00 CRITICAL Out of memory
2026-01-01 08:04:00 DEBUG heartbeat
"""


def run_cli(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_path = os.path.join(self.tmp.name, "app.log")
        with open(self.log_path, "w", encoding="utf-8") as handle:
            handle.write(SAMPLE_LOG)


class TestSummaryCommand(CliTestCase):
    def test_summary_output(self):
        code, out, _ = run_cli(["summary", self.log_path])
        self.assertEqual(code, 0)
        self.assertIn("Total lines: 6", out)
        self.assertIn("INFO", out)
        self.assertIn("ERROR", out)
        self.assertIn("2026-01-01 08:00:01 -> 2026-01-01 08:04:00", out)
        self.assertIn("Connection failed after # retries (id=#)", out)


class TestErrorsCommand(CliTestCase):
    def test_errors_groups_similar_messages(self):
        code, out, _ = run_cli(["errors", self.log_path])
        self.assertEqual(code, 0)
        self.assertIn("2 x Connection failed after # retries (id=#)", out)

    def test_errors_top_flag(self):
        code, out, _ = run_cli(["errors", self.log_path, "--top", "1"])
        self.assertEqual(code, 0)
        self.assertNotIn("Out of memory", out)


class TestTailCommand(CliTestCase):
    def test_tail_error_and_above(self):
        code, out, _ = run_cli(["tail", self.log_path, "--level", "ERROR"])
        self.assertEqual(code, 0)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertNotIn("service started", out)

    def test_tail_accepts_lowercase_level(self):
        code, out, _ = run_cli(["tail", self.log_path, "--level", "critical"])
        self.assertEqual(code, 0)
        self.assertIn("Out of memory", out)
        self.assertNotIn("Connection failed", out)


class TestRateCommand(CliTestCase):
    def test_rate_minute(self):
        code, out, _ = run_cli(["rate", self.log_path])
        self.assertEqual(code, 0)
        self.assertIn("2026-01-01 08:00  ## 2", out)
        self.assertIn("2026-01-01 08:01  # 1", out)

    def test_rate_hour(self):
        code, out, _ = run_cli(["rate", self.log_path, "--bucket", "hour"])
        self.assertEqual(code, 0)
        self.assertIn("2026-01-01 08:00  ###### 6", out)


class TestFileErrors(CliTestCase):
    def test_missing_file(self):
        code, _, err = run_cli(["summary", os.path.join(self.tmp.name, "nope.log")])
        self.assertNotEqual(code, 0)
        self.assertIn("no such file", err)

    def test_empty_file(self):
        empty = os.path.join(self.tmp.name, "empty.log")
        with open(empty, "w", encoding="utf-8"):
            pass
        code, _, err = run_cli(["summary", empty])
        self.assertNotEqual(code, 0)
        self.assertIn("empty", err)


if __name__ == "__main__":
    unittest.main()
