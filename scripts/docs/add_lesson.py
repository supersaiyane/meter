#!/usr/bin/env python3
"""Append a lesson skeleton, so recording one costs a single command.

Two lessons across forty seven completed tasks is the measured failure in this
project's memory layer. `make session-end` has printed a reminder to write one
since the day it was created. A reminder ignored forty five times is not a
mechanism, and friction is the reason. This removes the friction.

Deliberately not automatic, and deliberately not filled in. A lesson is a rule
the recipient of a correction has to formulate. A generated one would be a
feeling, which CLAUDE.md bans, and `scripts/ci/check_memory.py` fails the
build while the placeholders are still here.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LESSONS = ROOT / "tasks" / "lessons.md"

TEMPLATE = """
---

## {today}: {name}

**Mistake:** TODO what I did wrong

**Correction:** TODO what the user actually said, quoted

**Rule:** TODO the rule that prevents a repeat. A rule, not a feeling.
"Be more careful" is banned.

**Triggers:** TODO the keywords or situations that should fire this rule
"""


def main(argv: list[str]) -> int:
    name = " ".join(argv[1:]).strip()
    if not name:
        print('Usage: make lesson m="short name for the pattern"')
        return 1
    if not LESSONS.exists():
        print(f"FAIL: {LESSONS} is missing")
        return 1

    body = TEMPLATE.format(today=date.today().isoformat(), name=name)
    with LESSONS.open("a", encoding="utf-8") as handle:
        handle.write(body)

    print(f"Appended a skeleton to tasks/lessons.md: {name}")
    print("Fill in the four fields. The build fails while TODO is still there.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
