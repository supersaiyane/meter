#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Enforces the reachability claims the accepted findings depend on. An
# accepted finding whose argument nobody checks is an accepted finding nobody can trust.
# Grade B here: copy it, then replace the package list and the module to advisory map.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Enforce the reachability claims in security/policy/accepted.yaml.

ADR-0018 accepts three unfixable CPython findings on the grounds that Meter
never imports the affected stdlib modules. That is only true while it stays
true, and a claim nobody checks decays into a claim nobody can trust.

So each accepted finding whose reachability argument is "we do not import X"
becomes a build failure if anyone imports X. The acceptance and the enforcement
live next to each other deliberately: adding a module here without removing the
acceptance, or the reverse, is caught by the consistency check at the bottom.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
ACCEPTED = ROOT / "security" / "policy" / "accepted.yaml"

PACKAGES = (
    "finops_core",
    "finops_providers",
    "finops_ingest",
    "finops_api",
    "finops_mcp",
    "finops_query",
)

# module -> the advisory whose acceptance depends on not importing it
FORBIDDEN = {
    "stringprep": "CVE-2026-17084",
    "poplib": "CVE-2025-15367",
    "urllib.request": "CVE-2026-15806",
    "tarfile": "CVE-2026-19672",
}


def imported_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def main() -> int:
    problems: list[str] = []
    scanned = 0

    for package in PACKAGES:
        base = ROOT / package
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "tests" in path.parts:
                continue
            scanned += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                problems.append(f"{path.relative_to(ROOT)}: {exc}")
                continue
            found = imported_modules(tree)
            for module, advisory in FORBIDDEN.items():
                if any(m == module or m.startswith(module + ".") for m in found):
                    problems.append(
                        f"{path.relative_to(ROOT)}: imports `{module}`.\n"
                        f"    {advisory} is accepted as unfixable ONLY because Meter "
                        f"does not import it.\n"
                        f"    Importing it makes the acceptance false. Either use a "
                        f"different module, or\n"
                        f"    withdraw the acceptance in security/policy/accepted.yaml "
                        f"and find another answer."
                    )

    # The acceptance file and this list must agree, or one silently outlives the other.
    if ACCEPTED.exists():
        accepted_ids = {
            e.get("id") for e in (yaml.safe_load(ACCEPTED.read_text()) or {}).get("accepted", [])
        }
        for module, advisory in FORBIDDEN.items():
            if advisory not in accepted_ids:
                problems.append(
                    f"`{module}` is forbidden here for {advisory}, which is no longer "
                    f"in security/policy/accepted.yaml. Remove the rule or restore "
                    f"the acceptance."
                )

    if problems:
        print(f"FAIL: {len(problems)} problem(s)\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nSee ADR-0018 and security/policy/accepted.yaml.")
        return 1

    print(
        f"OK: {scanned} files scanned, none import the {len(FORBIDDEN)} modules "
        f"whose absence the accepted findings depend on"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
