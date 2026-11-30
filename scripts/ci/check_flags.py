#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade A
# Why this file exists: Fails on an expired flag, or on one missing an owner, a reason or a
# removal plan.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Validate the feature flag register, and fail on an expired flag.

Same mechanism as the security allowlist, deliberately, because both solve the
same problem: a temporary decision quietly becoming permanent. An expired flag
breaks the build rather than lapsing into a permanent branch nobody dares
remove. See ADR-0017.

Also checks that every flag in the register has a matching METER_FEATURE_ entry
in .env.example, and the reverse, so the two cannot drift.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTER = ROOT / "docs" / "feature-flags.yaml"
ENV_EXAMPLE = ROOT / ".env.example"

REQUIRED = ("key", "default", "owner", "reason", "expires", "removal")
SOFT_LIMIT = 15


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []
    data = yaml.safe_load(REGISTER.read_text(encoding="utf-8")) or {}
    flags = data.get("flags") or []
    today = date.today()

    for index, flag in enumerate(flags):
        label = flag.get("key", f"entry {index}")
        for field in REQUIRED:
            if flag.get(field) in (None, ""):
                problems.append(f"{label}: missing required field '{field}'")

        expires = flag.get("expires")
        if isinstance(expires, date) and expires < today:
            problems.append(
                f"{label}: EXPIRED on {expires}. Either delete the flag and its "
                f"false branch, or make a fresh decision with a new expiry and a "
                f"reason that is still true."
            )

        owner = str(flag.get("owner", ""))
        if owner.startswith("PLACEHOLDER"):
            # A warning, not a failure. Only the project owner can supply real
            # names, and failing the build on day one for something the
            # engineer cannot fix is how a check gets disabled in week two.
            # Tracked as ISS-087, and it becomes an error before the first
            # merge request.
            warnings.append(
                f"{label}: owner is still a placeholder. A flag with no named "
                f"owner is a branch nobody will ever remove. ISS-087."
            )

    env = ENV_EXAMPLE.read_text(encoding="utf-8")
    in_env = {
        m.group(1).lower() for m in re.finditer(r"^METER_FEATURE_([A-Z0-9_]+)=", env, re.MULTILINE)
    }
    in_register = {str(f.get("key", "")).lower() for f in flags}

    for key in sorted(in_register - in_env):
        problems.append(f"{key}: in the register, missing from .env.example")
    for key in sorted(in_env - in_register):
        problems.append(
            f"{key}: in .env.example, missing from docs/feature-flags.yaml. "
            f"Every flag needs an owner, a reason, an expiry and a removal plan."
        )

    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    if problems:
        print(f"FAIL: {len(problems)} problem(s) with the feature flag register\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nSee ADR-0017.")
        return 1

    note = ""
    if len(flags) > SOFT_LIMIT:
        note = (
            f"\nWARNING: {len(flags)} flags, above the target of {SOFT_LIMIT}. "
            f"The review is which have outlived their reason, not how to organise them."
        )
    print(f"OK: {len(flags)} feature flags, all valid, none expired{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
