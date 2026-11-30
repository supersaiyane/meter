#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade A
# Why this file exists: Fails when an allowlist entry is malformed or has expired.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Validate security/policy/allowlist.yaml and emit grype ignore rules.

An allowlist entry is a decision by a named person to ship a known finding. It
carries an owner and an expiry so the decision is revisited rather than
forgotten.

This fails when an entry is malformed, when it has expired, or when its expiry
is more than 90 days after it was added. An expired entry breaking the build is
the point: a silent lapse into permanent acceptance is exactly what an
allowlist is meant to prevent.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

REQUIRED = ("id", "package", "target", "reason", "owner", "added", "expires")
MAX_WINDOW = timedelta(days=90)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("--emit-grype-ignore", type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    if not args.allowlist.exists():
        print(f"FAIL: {args.allowlist} is missing")
        return 1

    data = yaml.safe_load(args.allowlist.read_text()) or {}
    entries = data.get("exceptions") or []
    problems: list[str] = []

    for index, entry in enumerate(entries):
        label = entry.get("id", f"entry {index}")
        for field in REQUIRED:
            if not entry.get(field):
                problems.append(f"{label}: missing required field '{field}'")

        added, expires = entry.get("added"), entry.get("expires")
        if isinstance(added, date) and isinstance(expires, date):
            if expires < args.today:
                problems.append(
                    f"{label}: EXPIRED on {expires}. Make a fresh decision and add a "
                    f"new entry. Do not edit the date."
                )
            if expires - added > MAX_WINDOW:
                problems.append(f"{label}: expiry {expires} is more than 90 days after {added}")

    if problems:
        print(f"FAIL: {len(problems)} problem(s) in {args.allowlist}\n")
        for problem in problems:
            print(f"  {problem}")
        return 1

    if args.emit_grype_ignore:
        rules = [{"vulnerability": e["id"], "package": {"name": e["package"]}} for e in entries]
        args.emit_grype_ignore.write_text(yaml.safe_dump({"ignore": rules}))

    plural = "y" if len(entries) == 1 else "ies"
    print(f"OK: {len(entries)} allowlist entr{plural}, all valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
