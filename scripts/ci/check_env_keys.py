#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade A
# Why this file exists: Reports keys the example has gained that the local .env never did, so a
# new setting fails with its own name before the stack fails with a wall of pydantic errors.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Name the settings a local .env is missing, before anything tries to start.

`.env` is copied from `.env.example` once and never again, so every setting added afterwards is
present in the example, absent locally, and invisible until somebody runs the stack. On
2026-09-27 eleven had accumulated over one session, and `make up` failed inside the migration
container with eleven lines of "Field required" and no indication that the cause was a file on
the developer's own disk rather than anything in the image.

It reports and does not write. A script that edited `.env` would be editing a file that holds
whatever somebody put there by hand, and the one thing worse than a missing key is a
credential quietly replaced with an example value.

Values are never read and never printed. Only the key names are compared, because this runs in
a terminal somebody may be sharing.

Usage:
  scripts/ci/check_env_keys.py           report, exit non zero if any are missing
  scripts/ci/check_env_keys.py --quiet   report only when something is missing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"
LOCAL = ROOT / ".env"

KEY = re.compile(r"^([A-Z0-9_]+)=", re.MULTILINE)


def keys(path: Path) -> set[str]:
    return set(KEY.findall(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not LOCAL.exists():
        # Not a fault. `make up` creates it, and saying so is more useful than a missing file
        # error from a script nobody asked to run.
        if not args.quiet:
            print("OK: no .env yet, 'make up' will create it from the example")
        return 0

    missing = sorted(keys(EXAMPLE) - keys(LOCAL))
    if not missing:
        if not args.quiet:
            print(f"OK: .env has every key .env.example declares, {len(keys(EXAMPLE))} of them")
        return 0

    print(f"FAIL: .env is missing {len(missing)} key(s) that .env.example declares:")
    for key in missing:
        print(f"  {key}")
    print()
    print("Copy each line from .env.example into .env. Nothing here writes to .env, because it")
    print("holds whatever you put there and a script that edited it could replace a credential")
    print("with an example value.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
