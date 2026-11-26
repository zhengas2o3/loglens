# loglens

A small, dependency-free command-line analyzer for plain-text log files.
`loglens` answers the questions you usually reach for `grep`, `awk` and
`sort | uniq -c` to solve: How many errors are in this file? Which error
keeps repeating? When did the burst happen? It understands common log
formats out of the box and groups "the same" error together even when
every occurrence carries a different id, counter or address.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

## Features

- **summary** — total lines, counts per level (`DEBUG` / `INFO` /
  `WARNING` / `ERROR` / `CRITICAL`, case-insensitive, `WARN` accepted),
  the time range covered by the file, and the top error messages.
- **errors** — the most frequent `ERROR`/`CRITICAL` messages, normalised
  before counting: digits, UUIDs, IP addresses and hex-style ids are
  masked, so `Connection failed after 3 retries (id=8812)` and the same
  line with `5 retries (id=1044)` count as one message.
- **tail** — print only the lines at or above a chosen level.
- **rate** — messages per minute or per hour, based on the timestamps
  parsed from each line.
- Timestamp formats: ISO 8601 (`2026-01-01T12:00:00.441Z`, offsets
  supported), `2026-01-01 12:00:00` (with `.` or `,` fractional seconds)
  and syslog style (`Jan  1 12:00:00`). Lines without a parseable
  timestamp still count toward the totals.
- Pure Python standard library. No dependencies, nothing to compile.
- Missing or empty files produce a clean error message on stderr and a
  non-zero exit code, so `loglens` is safe to use in scripts.

## Installation

```bash
git clone https://github.com/zhengas2o3/loglens.git
cd loglens
pip install .
```

This installs a `loglens` command. Without installing, run it from the
project root as `python3 -m loglens.cli ...`.

## Quickstart

The examples use the bundled sample log, `examples/sample.log`.

### Summary

```console
$ loglens summary examples/sample.log
File: examples/sample.log
Total lines: 28
Time range: 2026-01-01 08:00:01 -> 2026-01-01 08:45:59
Lines with timestamps: 27

Levels:
  DEBUG     3
  INFO      12
  WARNING   3
  ERROR     8
  CRITICAL  1
  UNKNOWN   1

Top error messages:
    3 x Connection to database failed after # retries (id=#)
    3 x Timeout while calling payment API (request #)
    2 x Failed to open file /var/data/report-#.csv
    1 x Out of memory: worker # killed
```

### Top errors

```console
$ loglens errors examples/sample.log --top 3
Top 3 error messages in examples/sample.log:
    3 x Connection to database failed after # retries (id=#)
    3 x Timeout while calling payment API (request #)
    2 x Failed to open file /var/data/report-#.csv
```

### Filter by level

```console
$ loglens tail examples/sample.log --level ERROR
2026-01-01 08:03:05 ERROR Connection to database failed after 3 retries (id=8812)
2026-01-01 08:03:09 ERROR Connection to database failed after 3 retries (id=9021)
2026-01-01 08:06:57 ERROR Timeout while calling payment API (request 5f3a21)
2026-01-01 08:09:52 ERROR Timeout while calling payment API (request 77bc90)
2026-01-01 08:12:40 CRITICAL Out of memory: worker 4 killed
2026-01-01 08:15:37 ERROR Connection to database failed after 5 retries (id=1044)
Jan  1 08:18:45 ERROR Failed to open file /var/data/report-2026.csv
2026-01-01 08:26:31 ERROR Failed to open file /var/data/report-2027.csv
2026-01-01 08:33:18 ERROR Timeout while calling payment API (request 91de02)
```

### Rate per time bucket

```console
$ loglens rate examples/sample.log
2026-01-01 08:00  ### 3
2026-01-01 08:01  # 1
2026-01-01 08:02  # 1
2026-01-01 08:03  ### 3
...

$ loglens rate examples/sample.log --bucket hour
2026-01-01 08:00  ########################### 27
```

## Project structure

```
loglens/
├── loglens/
│   ├── __init__.py      # package metadata
│   ├── core.py          # line/timestamp parsing, grouping, bucketing
│   └── cli.py           # argparse CLI: summary / errors / tail / rate
├── examples/
│   └── sample.log       # mixed-format sample log used in the Quickstart
├── tests/
│   ├── test_core.py     # parsing, normalisation, bucketing, filtering
│   └── test_cli.py      # end-to-end CLI behaviour and file errors
├── pyproject.toml
├── LICENSE
└── README.md
```

## Roadmap

- `--since` / `--until` time-window filters for every subcommand.
- JSON output (`--format json`) for piping into other tools.
- Compressed input (`.gz`) and reading from stdin.
- Custom level sets and per-file format hints for non-standard logs.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Ruizhao Zheng.
