#!/usr/bin/env python3
"""Rotate the checkpoint log, so its own archive rule stops being a rule.

docs/checkpoint.md has stated since the day it was created that at 50 entries
the oldest move to docs/checkpoint_archive.md and the latest 20 stay. The file
reached 47 entries and the archive was never created, because the rule had no
mechanism behind it. This is the mechanism.

No format change. The table is already machine readable, and converting the
entries to structured fields would make writing one slower, on the layer whose
measured problem is that too few get written.

Idempotent. Below the threshold it does nothing and says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINT = ROOT / "docs" / "checkpoint.md"
ARCHIVE = ROOT / "docs" / "checkpoint_archive.md"

THRESHOLD = 50
KEEP = 20

HEADER = "| Date and time | Task | Status | What changed | Resume vector |"
SEPARATOR = "| --- | --- | --- | --- | --- |"

ARCHIVE_PREAMBLE = f"""# Checkpoint archive

Rotated out of `docs/checkpoint.md` by `scripts/docs/rotate_checkpoint.py` at
{THRESHOLD} entries, oldest first. This is history, kept for the record.

Entries here are not validated by `scripts/ci/check_memory.py`. History is
allowed to reference files, commits and directories that no longer exist.

{HEADER}
{SEPARATOR}
"""


def row_indexes(lines: list[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if line.startswith("| 20")]


def plan_rotation(
    lines: list[str], threshold: int = THRESHOLD, keep: int = KEEP
) -> tuple[list[str], list[str]]:
    """Split a checkpoint file into what stays and what moves. No file access.

    The pure half is separated from the writing half because this is the only
    script in the project that deletes rows from the memory log, and a rewrite
    that loses an entry is unrecoverable by definition: the log is the record
    of what happened.

    Returns the new file lines and the rows to append to the archive. The rows
    to move are empty below the threshold, which is the common case and must
    be a no operation.
    """
    indexes = row_indexes(lines)
    if not indexes:
        return list(lines), []

    first, last = indexes[0], indexes[-1]
    if indexes != list(range(first, last + 1)):
        raise ValueError("the checkpoint table is not one contiguous block of rows")

    rows = lines[first : last + 1]
    if len(rows) <= threshold:
        return list(lines), []

    move, stay = rows[:-keep], rows[-keep:]
    return lines[:first] + stay + lines[last + 1 :], move


def main() -> int:
    if not CHECKPOINT.exists():
        print(f"FAIL: {CHECKPOINT} is missing")
        return 1

    lines = CHECKPOINT.read_text(encoding="utf-8").splitlines()
    total = len(row_indexes(lines))
    if total == 0:
        print("OK: no checkpoint entries to rotate")
        return 0

    try:
        rotated, move = plan_rotation(lines)
    except ValueError as error:
        print(f"FAIL: {error}")
        return 1

    if not move:
        print(f"OK: {total} entries, below the rotation threshold of {THRESHOLD}")
        return 0

    if not ARCHIVE.exists():
        ARCHIVE.write_text(ARCHIVE_PREAMBLE, encoding="utf-8")
    existing = ARCHIVE.read_text(encoding="utf-8").rstrip("\n")
    ARCHIVE.write_text(existing + "\n" + "\n".join(move) + "\n", encoding="utf-8")

    CHECKPOINT.write_text("\n".join(rotated) + "\n", encoding="utf-8")

    print(
        f"OK: moved {len(move)} entries to docs/checkpoint_archive.md, "
        f"{total - len(move)} remain live"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
