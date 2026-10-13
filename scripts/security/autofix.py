#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade A
# Why this file exists: Applies available fixes on a branch, runs the tests, re scans, and never
# merges.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Propose and apply the available security fixes, on a branch, with tests.

The requirement was that a fix should be applied after the scan. It is, with
one deliberate constraint.

  **Fixes are applied to a branch and gated on the full test suite. They are
  never applied to the default branch, and never auto merged.**

An unattended dependency upgrade that breaks production is a worse outcome than
the vulnerability it closed, particularly in a financial services environment
where the change also has to be evidenced. So this script does the tedious part
in full, and a person approves the merge.

What is applied automatically:
  * patch and minor upgrades to a published fixed version

What is proposed but never applied automatically:
  * major version upgrades, which carry breaking changes by definition
  * findings with no published fix
  * anything in a transitive dependency that has no direct pin

Usage:
  scripts/security/autofix.py --summary security/reports/latest/summary.json
  scripts/security/autofix.py --summary ... --apply        actually edit files
  scripts/security/autofix.py --summary ... --apply --branch security/fix-2026-08-23
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent


def parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts[:3]) or (0,)


def is_major_bump(installed: str, fixed: str) -> bool:
    a, b = parse_version(installed), parse_version(fixed)
    return bool(a and b and b[0] > a[0])


def classify(findings: list[dict[str, Any]]) -> tuple[list, list]:
    """Split findings into automatically applicable and human decisions."""
    auto, manual = [], []
    for finding in findings:
        fixed = finding.get("fixed_in")
        if not fixed:
            finding["blocked_because"] = "no published fix"
            manual.append(finding)
        elif is_major_bump(finding.get("installed", ""), fixed):
            finding["blocked_because"] = (
                f"major version bump {finding.get('installed')} to {fixed}, "
                f"breaking changes are expected"
            )
            manual.append(finding)
        elif finding.get("ecosystem") not in ("python", "python-pkg", "npm", "node-pkg"):
            finding["blocked_because"] = (
                "fix is in the base image, rebuild against the current Minimus tag"
            )
            manual.append(finding)
        else:
            auto.append(finding)
    return auto, manual


def apply_python(finding: dict[str, Any], pyproject: Path) -> bool:
    """Raise the lower bound of a direct pin. Returns True when a change was made."""
    package, fixed = finding["package"], finding["fixed_in"]
    text = pyproject.read_text()
    pattern = re.compile(
        rf'(["\']){re.escape(package)}(\[[^\]]*\])?\s*>=\s*[^"\',]+(["\'])'
    )
    match = pattern.search(text)
    if not match:
        finding["blocked_because"] = (
            f"{package} is not a direct pin in pyproject.toml, it arrives "
            f"transitively. Pin it explicitly or upgrade its parent."
        )
        return False
    extras = match.group(2) or ""
    replacement = f'{match.group(1)}{package}{extras}>={fixed}{match.group(3)}'
    pyproject.write_text(text[: match.start()] + replacement + text[match.end() :])
    return True


def apply_npm(finding: dict[str, Any]) -> bool:
    package, fixed = finding["package"], finding["fixed_in"]
    result = subprocess.run(
        ["npm", "install", f"{package}@{fixed}", "--package-lock-only"],
        cwd=ROOT / "finops-web",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        finding["blocked_because"] = f"npm install failed: {result.stderr.strip()[:200]}"
        return False
    return True


def run(command: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--branch", default=None)
    parser.add_argument("--skip-tests", action="store_true",
                        help="Only for a dry run. Never use when applying.")
    args = parser.parse_args()

    if not args.summary.exists():
        print(f"FAIL: {args.summary} is missing. Run 'make security-scan' first.")
        return 1

    findings = json.loads(args.summary.read_text()).get("findings", [])
    if not findings:
        print("Nothing to fix. The posture is already zero.")
        return 0

    auto, manual = classify(findings)

    print(f"{len(findings)} unresolved finding(s)")
    print(f"  {len(auto)} can be applied automatically")
    print(f"  {len(manual)} need a human decision\n")

    for finding in manual:
        print(f'  MANUAL  {finding["id"]:<20} {finding["package"]:<24} '
              f'{finding.get("blocked_because", "")}')
    if manual:
        print()

    if not args.apply:
        for finding in auto:
            print(f'  WOULD APPLY  {finding["package"]} '
                  f'{finding.get("installed")} -> {finding["fixed_in"]}')
        print("\nDry run. Pass --apply to make the changes on a branch.")
        return 0

    branch = args.branch or f"security/autofix-{args.summary.parent.name}"
    code, output = run(["git", "checkout", "-b", branch])
    if code != 0 and "already exists" not in output:
        print(f"FAIL: could not create branch {branch}\n{output}")
        return 1
    print(f"Working on branch {branch}\n")

    pyproject = ROOT / "pyproject.toml"
    applied, failed = [], []
    for finding in auto:
        ok = (
            apply_python(finding, pyproject)
            if finding["ecosystem"] in ("python", "python-pkg")
            else apply_npm(finding)
        )
        (applied if ok else failed).append(finding)
        verb = "APPLIED" if ok else "SKIPPED"
        print(f'  {verb}  {finding["package"]} -> {finding["fixed_in"]}'
              + ("" if ok else f'  ({finding.get("blocked_because", "")})'))

    if not applied:
        print("\nNo change made.")
        return 1

    if args.skip_tests:
        print("\nWARNING: tests skipped. Do not merge this branch.")
        return 0

    print("\nRunning the full test suite against the upgraded dependencies")
    code, output = run(["make", "verify"])
    print(output[-4000:])
    if code != 0:
        print(
            "\nFAIL: the upgrade broke the tests. The branch is left in place so "
            "the failure can be inspected. Do not merge it, and do not lower the "
            "security threshold to avoid the upgrade."
        )
        return 1

    print("\nRe scanning to confirm the findings are actually closed")
    code, output = run(["bash", "scripts/security/scan.sh"])
    print(output[-2000:])

    print(
        f"\n{len(applied)} fix(es) applied on {branch}, tests pass, scan re run.\n"
        f"Open a merge request. This is never merged automatically."
    )
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
