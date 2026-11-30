#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade A
# Why this file exists: The gate that keeps memory true. Resume vectors must point somewhere
# real, cited commits must resolve, identifiers must be defined, and a lesson must be finished.
# Without it the memory layer rots silently.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Fail the build on a memory entry that has stopped being true.

The checkpoint log makes exactly one promise, stated in its own header: a
resume vector is precise enough that a cold session can continue without re
reading the project. Nothing ever checked that promise, so it decayed.

Same mechanism as scripts/ci/check_forbidden_imports.py, and for the reason
written there: a claim nobody checks decays into a claim nobody can trust. A
resume vector is a claim, and a rotten one is worse than no resume vector at
all, because it sends a fresh context to a dead address.

Five checks:

  paths        a repository path in an entry must exist
  commits      a commit sha cited in an entry must resolve in git
  identifiers  a TASK, ISS, ADR, CHG, FEAT or OPEN reference must be defined
  lessons      every lesson carries Mistake, Correction, Rule and Triggers,
               an absolute date, and no leftover placeholder
  harvest      the ratio of lessons to completed tasks, reported every run

Scope. Only the live window, the latest 20 entries the archive rule keeps, is
a build failure. Older rows still awaiting rotation are a warning, because
nobody resumes from forty tasks back, and failing the build over history is
how a check gets deleted in week two. Rows already in the archive are exempt
entirely: history is allowed to reference what no longer exists.

A bare filename carrying no directory separator is not validated. It cannot be
told apart from a reference to a file outside this repository, and the entries
contain both.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINT = ROOT / "docs" / "checkpoint.md"
LESSONS = ROOT / "tasks" / "lessons.md"
PLANS = ROOT / "docs" / "plans"

# Where an identifier may be defined. Membership is a substring test on
# purpose: it couples to no schema, so a change to the shape of registry.yaml
# cannot turn this check into a false failure.
DEFINITION_SOURCES = (
    ROOT / "docs" / "registry.yaml",
    ROOT / "tasks" / "STATUS.md",
    ROOT / "tasks" / "ISSUES.md",
)

LIVE_WINDOW = 20
HARVEST_RATIO = 10
LESSON_FIELDS = ("Mistake", "Correction", "Rule", "Triggers")
PLACEHOLDERS = ("TODO", "FIXME", "XXX")

BACKTICKED = re.compile(r"`([^`]+)`")
SHA = re.compile(r"^[0-9a-f]{7,40}$")
IDENTIFIER = re.compile(
    r"\b(?:TASK-P\d-\d{3}|ISS-\d{3}|ADR-\d{4}|CHG-\d{4}|FEAT-\d{3}|OPEN-\d{2})\b"
)


def table_rows(text: str) -> list[list[str]]:
    """Every data row of the checkpoint table, oldest first."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("| 20"):
            continue
        parts = [part.strip() for part in line.split("|")][1:-1]
        if len(parts) < 5:
            continue
        if len(parts) > 5:
            parts = parts[:4] + ["|".join(parts[4:])]
        rows.append(parts)
    return rows


def repo_paths(cell: str) -> list[str]:
    """Backticked tokens in a cell that are claims about a path in this repo."""
    found: list[str] = []
    for raw in BACKTICKED.findall(cell):
        token = raw.strip().rstrip(".,;:")
        if not token or " " in token or "$" in token:
            continue
        if token.startswith(("~", "/", "http")):
            continue
        if "/" not in token:
            continue
        found.append(token)
    return found


def sha_resolves(sha: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def known_identifiers() -> str:
    chunks = [p.read_text(encoding="utf-8") for p in DEFINITION_SOURCES if p.exists()]
    if PLANS.exists():
        chunks.extend(p.read_text(encoding="utf-8") for p in sorted(PLANS.glob("*.md")))
    return "\n".join(chunks)


def check_row(row: list[str], haystack: str) -> list[str]:
    date, task = row[0], row[1]
    label = f"{date} {task[:48]}"
    found: list[str] = []
    joined = " ".join(row)

    for path in repo_paths(row[4]):
        if not (ROOT / path).exists():
            found.append(f"{label}: resume vector points at '{path}', which does not exist")
    for path in repo_paths(row[3]):
        if not (ROOT / path).exists():
            found.append(f"{label}: cites '{path}', which does not exist")

    for token in BACKTICKED.findall(joined):
        token = token.strip()
        if SHA.match(token) and not sha_resolves(token):
            found.append(f"{label}: cites commit {token}, which does not resolve")

    for ident in sorted(set(IDENTIFIER.findall(joined))):
        if ident not in haystack:
            found.append(f"{label}: cites {ident}, which is defined nowhere")

    return found


def check_lessons() -> tuple[list[str], int, str]:
    if not LESSONS.exists():
        return ([f"{LESSONS} is missing"], 0, "never")
    text = LESSONS.read_text(encoding="utf-8")
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    problems: list[str] = []
    dates: list[str] = []

    for block in blocks:
        title = block.splitlines()[0].strip()
        for field in LESSON_FIELDS:
            if f"**{field}:**" not in block:
                problems.append(f"lesson '{title}': missing the {field} field")
        for marker in PLACEHOLDERS:
            if marker in block:
                problems.append(
                    f"lesson '{title}': still holds the placeholder {marker}. "
                    f"An unfinished skeleton is not a rule."
                )
                break
        match = re.match(r"(\d{4}-\d{2}-\d{2})", title)
        if match:
            dates.append(match.group(1))
        else:
            problems.append(f"lesson '{title}': the heading must open with an absolute date")

    return problems, len(blocks), max(dates) if dates else "never"


def main() -> int:
    if not CHECKPOINT.exists():
        print(f"FAIL: {CHECKPOINT} is missing")
        return 1

    rows = table_rows(CHECKPOINT.read_text(encoding="utf-8"))
    haystack = known_identifiers()
    live = rows[-LIVE_WINDOW:]
    stale = rows[:-LIVE_WINDOW]

    problems: list[str] = []
    warnings: list[str] = []
    for row in live:
        problems.extend(check_row(row, haystack))
    for row in stale:
        warnings.extend(check_row(row, haystack))

    lesson_problems, lesson_count, last_lesson = check_lessons()
    problems.extend(lesson_problems)

    if len(rows) and lesson_count * HARVEST_RATIO < len(rows):
        warnings.append(
            f"{lesson_count} lessons across {len(rows)} completed tasks. "
            f"The target is one per {HARVEST_RATIO}. Corrections are being "
            f"received and not recorded. Use 'make lesson'."
        )
    if len(stale):
        warnings.append(
            f"{len(stale)} entries are older than the live window of {LIVE_WINDOW}, "
            f"so they warn rather than fail. They leave for the archive at 50."
        )

    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    if problems:
        print(f"FAIL: {len(problems)} rotten memory claim(s)\n")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nA memory entry nobody can act on is worse than no entry. "
            "Fix the entry, do not delete the check."
        )
        return 1

    print(
        f"OK: {len(rows)} checkpoint entries ({len(live)} live), "
        f"{lesson_count} lessons, last on {last_lesson}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
