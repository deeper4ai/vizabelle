from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable, Iterator, TextIO

from .clause import annotate_clauses


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HELPER = REPO_ROOT / "build" / "vizabelle-jjparser-json"
INSTANCE_RE = re.compile(
    r"^%%%\s+INSTANCE\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def extract_tstp_text(path: Path) -> str:
    """Return the SZS proof block when present, otherwise the whole file."""
    with open_text(path) as stream:
        lines = stream.readlines()

    start = None
    end = None
    for index, line in enumerate(lines):
        if line.startswith("% SZS output start"):
            start = index
        elif start is not None and line.startswith("% SZS output end"):
            end = index + 1
            break

    if start is not None:
        return "".join(lines[start:end])
    return "".join(lines)


def read_instance(path: Path) -> tuple[str, str] | None:
    """Read the benchmark and problem path from the proof's INSTANCE header."""
    with open_text(path) as stream:
        first_line = stream.readline()
    match = INSTANCE_RE.match(first_line)
    return (match.group(1), match.group(2)) if match else None


def run_jjparser_json(text: str, helper: Path = DEFAULT_HELPER) -> str:
    proc = subprocess.run(
        [str(helper)],
        input=text,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def parse_jsonl(lines: Iterable[str]) -> Iterator[dict]:
    for line in lines:
        line = line.strip()
        if line:
            yield json.loads(line)


def parse_file(path: Path, helper: Path = DEFAULT_HELPER) -> list[dict]:
    text = extract_tstp_text(path)
    output = run_jjparser_json(text, helper)
    records = list(parse_jsonl(output.splitlines()))
    annotate_clauses(records)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse TPTP/TSTP/THF formulas with JJParser.")
    parser.add_argument("input", type=Path, help="TPTP problem/proof file, optionally gzip-compressed")
    parser.add_argument(
        "--helper",
        type=Path,
        default=DEFAULT_HELPER,
        help="Path to the vizabelle-jjparser-json helper",
    )
    parser.add_argument("--pretty", action="store_true", help="Emit a pretty JSON array instead of JSONL")
    args = parser.parse_args(argv)

    records = parse_file(args.input, args.helper)
    if args.pretty:
        print(json.dumps(records, indent=2))
    else:
        for record in records:
            print(json.dumps(record, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
