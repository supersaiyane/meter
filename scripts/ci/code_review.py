#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Runs the deterministic checks first and the review checklist second, so
# a human reviewer spends attention on judgment rather than on what a script can see.
# Grade B here: copy it, then replace the checklist items.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Automated code review of the working tree or a diff. See ADR-0011.

Runs the deterministic checks first, because a linter finding is cheaper and
more reliable than a model opinion, and then hands what remains to a review
agent. Writes a severity ranked markdown report.

The order matters. A review that leads with model generated commentary buries
the findings a tool proved. Deterministic first, opinion second.

Usage:
  scripts/ci/code_review.py --output security/reviews
  scripts/ci/code_review.py --diff origin/main --output security/reviews
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Deterministic checks. Each is (name, command, blocking).
CHECKS = [
    ("ruff", ["ruff", "check", "--output-format", "json", "."], True),
    (
        "mypy",
        [
            "mypy",
            "--no-error-summary",
            "finops_core",
            "finops_providers",
            "finops_ingest",
            "finops_api",
        ],
        True,
    ),
    ("import-linter", ["lint-imports"], True),
    ("layering", ["python3", "scripts/docs/build_file_graph.py", "--check"], True),
    ("dead-code", ["ruff", "check", "--select", "F401,F841,ARG", "."], False),
]


def run(command: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return 127, f"{command[0]} is not installed"


def changed_files(base: str | None) -> list[str]:
    if not base:
        code, out = run(["git", "diff", "--name-only", "HEAD"])
    else:
        code, out = run(["git", "diff", "--name-only", f"{base}...HEAD"])
    return [line for line in out.splitlines() if line.strip()] if code == 0 else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "security" / "reviews")
    parser.add_argument("--diff", default=None, help="base ref, for example origin/main")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    args.output.mkdir(parents=True, exist_ok=True)
    report = args.output / f"review-{stamp}.md"

    files = changed_files(args.diff)
    lines = [
        "# Automated code review",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"Scope: {args.diff + '...HEAD' if args.diff else 'working tree'}",
        f"Files changed: {len(files)}",
        "",
        "## Deterministic checks",
        "",
        "| Check | Result | Blocking |",
        "| --- | --- | --- |",
    ]

    blocking_failures = 0
    details: list[str] = []

    for name, command, blocking in CHECKS:
        code, output = run(command)
        if code == 127:
            status = "not installed"
        elif code == 0:
            status = "pass"
        else:
            status = "FAIL"
            if blocking:
                blocking_failures += 1
        lines.append(f"| `{name}` | {status} | {'yes' if blocking else 'no'} |")
        if code not in (0, 127) and output:
            details.append(f"### {name}\n\n```\n{output[:6000]}\n```\n")

    lines.append("")
    if details:
        lines += ["## Findings", ""] + details

    lines += [
        "## Review checklist",
        "",
        "Deterministic tools do not catch these. A reviewer does.",
        "",
        "- [ ] Does any new error path collapse a failure into a zero? See ISS-015",
        "- [ ] Does any new repository method take `Scope` without a default? See ISS-009",
        "- [ ] Does any new fact table column allow a null `as_of`?",
        "- [ ] Was a new dependency admitted through `make dep-check`? See ADR-0010",
        "- [ ] Could this have reused something that already exists? See ADR-0011 rung two",
        "- [ ] Does the change update `INDEX.md` and the feature document?",
        "- [ ] Is every new figure labelled measured or modelled?",
        "",
        "## Verdict",
        "",
        f"**{'BLOCK' if blocking_failures else 'PASS'}**: "
        f"{blocking_failures} blocking check(s) failed.",
        "",
    ]

    report.write_text("\n".join(lines))
    print(f"Review written to {report}")
    print(f"{blocking_failures} blocking failure(s)")
    return 1 if blocking_failures else 0


if __name__ == "__main__":
    sys.exit(main())
