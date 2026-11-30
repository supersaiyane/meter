#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Fails the build when the index and the documents disagree. An index is
# only useful while it is true.
# Grade B here: copy it, then replace the paths it checks.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Fail if INDEX.md and the documents it indexes have drifted apart.

Two checks, both cheap and both worth having:

1. Every path INDEX.md links to actually exists.
2. Every markdown document under docs/ and tasks/ is linked from INDEX.md.

The second check is the one that matters. A document nobody links to is a
document nobody reads, and it rots into a source of confident wrong answers.

Run via `make check-docs`. Exits 1 on failure, so CI stops.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "INDEX.md"

# Directories whose markdown must be reachable from INDEX.md.
INDEXED_DIRS = ("docs", "tasks")

# Files exempt from the reachability check, with the reason.
EXEMPT = {
    "docs/templates/README.md": "templates are reached through their directory entry",
    "docs/templates/FEATURE-TEMPLATE.md": "template",
    "docs/features/README.md": "reached through the feature tables",
    "docs/architecture/file-graph.md": "generated, linked from INDEX section 10",
    "docs/templates/SPEC-TEMPLATE.md": "template",
    "docs/templates/TASK-TEMPLATE.md": "template",
    "docs/templates/ADR-TEMPLATE.md": "template",
    "docs/templates/CHANGE-TEMPLATE.md": "template",
    "docs/templates/ISSUE-TEMPLATE.md": "template",
    "docs/adr/README.md": "reached through the ADR directory entry",
    "docs/plans/README.md": "reached through the plans directory entry",
}

LINK = re.compile(r"\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")
BACKTICK_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.md)`")


def problems_in(root: Path | None = None) -> list[str] | None:
    """Everything wrong with the index under `root`, or None when it is absent.

    The root is a parameter so this can be pointed at a fixture tree. A checker
    with no test of its own failure paths is a checker nobody knows still fails,
    and this one is the reason a merge stops.
    """
    # Read at call time rather than bound as a default, so a test can point the
    # checker at a fixture tree.
    root = ROOT if root is None else root
    index = root / "INDEX.md"
    if not index.exists():
        return None

    text = index.read_text(encoding="utf-8")
    referenced: set[str] = set()
    problems: list[str] = []

    for match in list(LINK.finditer(text)) + list(BACKTICK_PATH.finditer(text)):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        referenced.add(target.lstrip("./"))

    # Check 1: every referenced path exists.
    for target in sorted(referenced):
        candidate = root / target
        if not candidate.exists() and not target.endswith("/"):
            problems.append(f"INDEX.md references a missing path: {target}")

    # Check 2: every indexed document is referenced.
    for directory in INDEXED_DIRS:
        for path in sorted((root / directory).rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            if rel in EXEMPT:
                continue
            if rel not in referenced:
                problems.append(f"Not referenced from INDEX.md: {rel}")

    return problems


def main() -> int:
    problems = problems_in()
    if problems is None:
        print("FAIL: INDEX.md is missing. It is the entry point for the project.")
        return 1
    if problems:
        print("FAIL: INDEX.md is out of step with the documents it indexes.\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nSee docs/03-CHANGE-CONTROL.md for the routing rule.")
        return 1

    print("OK: INDEX.md is consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
