#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Fails on a value that belongs in configuration: a region, an account id,
# an ARN, an endpoint, a role name or a bare threshold.
# Grade B here: copy it, then replace the six patterns, which are shaped for AWS.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Fail the build on a value that belongs in configuration.

Documentation alone does not prevent hardcoding. This is the third rule in this
project that needed a check to become real, after the writing rules and the
generated documents. See ADR-0017.

Six patterns, chosen because each one has bitten a real project:

  region          "eu-west-1" in code means the second region silently does not
                  work, and the failure is a missing row rather than an error
  account id      a 12 digit literal is either a real account in source control
                  or a test fixture that will one day be mistaken for one
  arn             embeds an account, a region and a partition all at once
  endpoint url    an https:// literal is an outbound call nobody reviewed
  role name       must match the StackSet, and a drift between the two is an
                  AccessDenied nobody can explain
  bare threshold  a magic number in a comparison is a policy decision hidden in
                  an expression

Scans application packages only. The settings module, tests, and anything
generated are exempt, because a value has to be written down somewhere and the
settings module is that place.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Every application package. `finops_query` was missing until 2026-09-03, so
#: TASK-P2-002's criterion that this gate passes was being satisfied over code
#: the gate never read. `check_forbidden_imports.py` had already been given the
#: package and this one had not, which is what two lists of one thing does.
PACKAGES = (
    "finops_core",
    "finops_providers",
    "finops_ingest",
    "finops_api",
    "finops_mcp",
    "finops_query",
    "finops_relay",
)

EXEMPT_FILES = {
    "finops_core/config.py",  # the one place values are declared
    "finops_core/constants.py",  # genuine domain constants, closed sets
}
EXEMPT_DIRS = ("tests", "migrations", "__pycache__")

CHECKS = [
    (
        "region",
        re.compile(
            r'["\'](?:us|eu|ap|sa|ca|me|af|il)-(?:north|south|east|west|central|northeast|southeast)-[1-9]["\']'
        ),
        "AWS region literal. Use settings.regions, from METER_REGIONS.",
    ),
    (
        "account id",
        re.compile(r'["\'](?!0{12})\d{12}["\']'),
        "12 digit account identifier. Accounts come from the organization tree.",
    ),
    (
        "arn",
        re.compile(r'["\']arn:aws[a-z-]*:'),
        "ARN literal. Build it from settings, or read it from the provider.",
    ),
    (
        "endpoint url",
        re.compile(r'["\']https?://(?!127\.0\.0\.1|localhost)[^"\']+["\']'),
        "URL literal. Put it in settings, so an outbound call is reviewable.",
    ),
    (
        "role name",
        re.compile(r'["\'](?:FinOps[A-Za-z]*Role)["\']'),
        "Role name literal. Use settings.collector_role_name, so it cannot drift "
        "from the StackSet.",
    ),
    (
        "bare threshold",
        re.compile(r"(?<![\w.])(?:>=|<=|>|<)\s*(?!0\b|1\b|2\b|100\b)\d{2,}(?![\w.])"),
        "Numeric threshold in a comparison. A magic number in an expression is a "
        "policy decision in hiding. Move it to settings.",
    ),
]

# A line carrying this marker is accepted, with its reason recorded inline.
ALLOW = re.compile(r"#\s*allow-hardcoded:\s*(\S.*)")


def main() -> int:
    findings: list[str] = []
    scanned = 0

    for package in PACKAGES:
        base = ROOT / package
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT_FILES or any(d in path.parts for d in EXEMPT_DIRS):
                continue
            scanned += 1
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or ALLOW.search(line):
                    continue
                for name, pattern, advice in CHECKS:
                    match = pattern.search(line)
                    if match:
                        findings.append(f"{rel}:{number}  {name}: {match.group(0)}\n    {advice}")
                        break

    if findings:
        print(f"FAIL: {len(findings)} hardcoded value(s)\n")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nEvery value comes from the settings object, documented in "
            "\n.env.example with what it is, what it does, and which file reads "
            "it.\nSee ADR-0017.\n"
            "\nIf a literal is genuinely correct, mark the line:"
            "\n    VALUE  # allow-hardcoded: <reason>"
        )
        return 1

    if scanned == 0:
        print("OK: no application code yet, nothing to scan")
    else:
        print(f"OK: {scanned} files scanned, no hardcoded values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
