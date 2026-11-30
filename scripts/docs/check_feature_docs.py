#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Fails when a feature has no document, or a document has no feature.
# Grade B here: copy it, then replace the feature identifier scheme and the required section set.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Every feature in INDEX.md must have a document, and vice versa.

A feature listed in the index with no document is a promise with nothing behind
it. A document for a feature the index does not list is orphaned and will rot.
Both fail this check.

It also enforces that a feature marked Specified or beyond carries the sections
a specified feature needs. A Planned feature is held to a lighter standard on
purpose: inventing detail ahead of the decision produces a document that is
worse than a short one, because it will be believed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "INDEX.md"
FEATURES = ROOT / "docs" / "features"

FEAT_ID = re.compile(r"\bFEAT-(\d{3})\b")
STATUS = re.compile(r"^\|\s*Status\s*\|\s*([A-Za-z ]+?)\s*\|", re.MULTILINE)

SPECIFIED_SECTIONS = (
    "## What it does",
    "## Why it exists",
    "## How it works",
    "## Failure behaviour",
    "## Security considerations",
    "## Interface",
    "## Not doing",
)
PLANNED_SECTIONS = ("## What it does", "## Why it exists")


def main() -> int:
    problems: list[str] = []

    index_ids = {f"FEAT-{n}" for n in FEAT_ID.findall(INDEX.read_text(encoding="utf-8"))}
    doc_by_id: dict[str, Path] = {}
    for path in sorted(FEATURES.glob("FEAT-*.md")):
        match = FEAT_ID.match(path.name)
        if not match:
            problems.append(f"{path.name}: filename does not start with a FEAT id")
            continue
        doc_by_id[f"FEAT-{match.group(1)}"] = path

    for feature_id in sorted(index_ids - doc_by_id.keys()):
        problems.append(f"{feature_id} is in INDEX.md but has no document under docs/features/")
    for feature_id in sorted(doc_by_id.keys() - index_ids):
        problems.append(
            f"{feature_id} has a document but is not listed in INDEX.md, so nobody will find it"
        )

    for feature_id, path in sorted(doc_by_id.items()):
        text = path.read_text(encoding="utf-8")
        status_match = STATUS.search(text)
        status = status_match.group(1).strip() if status_match else ""
        if not status:
            problems.append(f"{feature_id}: no Status row in the field table")
            continue
        required = PLANNED_SECTIONS if status == "Planned" else SPECIFIED_SECTIONS
        for section in required:
            if section not in text:
                problems.append(f"{feature_id} is {status} but is missing the '{section}' section")

    if problems:
        print(f"FAIL: {len(problems)} problem(s) with feature documentation\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nTemplate: docs/templates/FEATURE-TEMPLATE.md")
        return 1

    print(f"OK: {len(doc_by_id)} feature documents, all present and complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
