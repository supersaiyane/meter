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
#: A git object name, which is 7 to 40 hex characters. Bounded at 40 on purpose:
#: a 64 character token is a sha256 file digest rather than a commit, and
#: checkpoint entries do cite those. Widening this would send every file hash to
#: `git cat-file` and report each one as a commit that does not resolve.
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
            parts = [*parts[:4], "|".join(parts[4:])]
        rows.append(parts)
    return rows


def repo_paths(cell: str) -> list[tuple[str, int | None]]:
    """Backticked tokens in a cell that are claims about a path in this repo.

    A token may carry a line number as `path.py:88`. CLAUDE.md asks a resume
    vector for "exact files and line numbers", and this used to treat the suffix
    as part of the filename, so the one format the convention requires was the
    one format that failed. Now it is split off and checked, which verifies more
    than the path alone did: a line number past the end of a file is a citation
    that will send the next reader to nothing.
    """
    found: list[tuple[str, int | None]] = []
    for raw in BACKTICKED.findall(cell):
        token = raw.strip().rstrip(".,;")
        if not token or " " in token or "$" in token:
            continue
        if token.startswith(("~", "/", "http")):
            continue

        line: int | None = None
        path, _, suffix = token.rpartition(":")
        if path and suffix.isdigit():
            token, line = path, int(suffix)
        token = token.rstrip(":")

        if "/" not in token or not claims_a_path(token):
            continue
        found.append((token, line))
    return found


def claims_a_path(token: str) -> bool:
    """Whether a slashed token is claiming to be a file in this repo.

    A resume vector legitimately backticks things that are not paths, and a
    branch name is the common one: `feat/ui-navigation-groups` has a slash in
    it and is not a file. Reporting it as a missing file trained the reader to
    ignore the whole check, which is how a real dead reference gets through.

    Two ways to qualify. Either the last segment has an extension, which is what
    a file reference looks like, or the first segment is something that exists
    at the top of the repo, which is what a directory reference looks like. A
    path under a directory that was deleted wholesale is the case this misses,
    and it is the price of not crying wolf on every branch name.
    """
    head, _, _ = token.partition("/")
    if (ROOT / head).exists():
        return True
    return "." in token.rsplit("/", 1)[-1]


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

    for path, line in repo_paths(row[4]):
        target = ROOT / path
        if not target.exists():
            found.append(f"{label}: resume vector points at '{path}', which does not exist")
            continue
        if line is None or target.is_dir():
            continue
        # A line past the end of a file sends the next reader to nothing, which
        # is the same failure as a path that does not exist, one step later.
        total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        if line > total:
            found.append(
                f"{label}: resume vector cites '{path}:{line}' and the file has {total} lines"
            )
    # The "what changed" cell, where a line number is noise rather than a claim.
    for path, _ in repo_paths(row[3]):
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


def check_next_action(text: str) -> list[str]:
    """The "Next action" section must not propose work that is already done.

    Added 2026-09-28 after that section went stale twice in two days, both times the same way:
    it named issues as the next thing to do, the work was done, and nobody rewrote the section.
    It is the one part of the checkpoint a cold session reads first, so a wrong candidate list
    sends a fresh start at a task that finished.

    Checkable because the registry knows. Every `ISS-nnn` the section names is looked up, and a
    FIXED one is a proposal to redo finished work. Naming a fixed issue to say it is finished is
    the legitimate case, so the line has to be read: the check only objects when the mention sits
    in a numbered candidate.
    """
    import re

    import yaml

    start = text.find("## Next action")
    if start == -1:
        return ["docs/checkpoint.md has no 'Next action' section for a cold session to read"]
    end = text.find("### Where the project is", start)
    section = text[start : end if end != -1 else len(text)]

    registry = yaml.safe_load((ROOT / "docs" / "registry.yaml").read_text(encoding="utf-8"))
    status = {one["id"]: one.get("status") for one in registry.get("issues", [])}

    problems: list[str] = []
    for line in section.splitlines():
        if not re.match(r"^\s*\d+\.", line):
            continue
        for named in re.findall(r"ISS-\d+", line):
            if status.get(named) == "FIXED":
                problems.append(
                    f"'Next action' proposes {named} as a candidate and it is FIXED. "
                    f"Rewrite the section: a cold session reads it first and would start "
                    f"work that is finished."
                )
    return problems


def main() -> int:
    if not CHECKPOINT.exists():
        print(f"FAIL: {CHECKPOINT} is missing")
        return 1

    checkpoint_text = CHECKPOINT.read_text(encoding="utf-8")
    rows = table_rows(checkpoint_text)
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
    problems.extend(check_next_action(checkpoint_text))

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
