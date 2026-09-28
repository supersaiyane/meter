#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Fails the build when a document cites an identifier that no register
# defines. A citation nobody can follow is worse than no citation.
# Grade B here: copy it, then replace the prefixes and the register keys it reads.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Fail if any FEAT, ISS, ADR, OPEN or CHG identifier cited anywhere resolves to nothing.

One check: every identifier written down in a scanned file exists in
`docs/registry.yaml`.

Why it exists. On 2026-09-28, while planning P6 and P7, three issue identifiers
turned out to have been cited by ten documents since 2026-08-23 and recorded in
no register. A reader chasing ISS-003 out of `docs/plans/P6-implementation-plan.md`,
which names it as that sub project's only blocker, found nothing at all. They
have since been registered. Nothing prevented a recurrence, which is what this
does. The lesson is in `tasks/lessons.md` under the 2026-09-28 heading about an
identifier copied from nearby prose instead of resolved in the register.

What it cannot do, stated plainly so nobody trusts it further than it goes.
It catches an identifier that resolves to nothing. It cannot catch an
identifier that resolves correctly and means something else, which was the
larger half of the same defect: FEAT-041 was used in ten places for realized
savings, which is FEAT-029, and every one of those citations would pass this
check because FEAT-041 is a real entry. Only reading the entry catches that.
The same shape had already happened twice before, to ISS-110 and ISS-111, and
`scripts/docs/sync.py` records it.

Two scoping decisions worth knowing about.

`docs/registry.yaml` is scanned rather than skipped. It defines the entries, so
its own identifiers resolve by construction, but its prose fields carry
citations too: an issue's `detail` or an open question's `blocks` can name
another identifier, and that is a citation like any other. Skipping the register
would lose exactly the case that started this.

Generated blocks are skipped. `scripts/docs/sync.py` writes them from the
register, so an identifier inside one either came from a register entry or came
from a register entry's prose, and in the second case the same text is caught in
`docs/registry.yaml` where somebody can actually edit it. Reporting it against a
generated document would send the reader to fix a file they must not touch.

Run via `make check-docs`. Exits 1 on failure, so CI stops.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = ROOT / "docs" / "registry.yaml"

# Which register defines each prefix. A prefix absent from here is not checked,
# so adding a family of identifiers means adding it here as well.
REGISTERS = {
    "FEAT": "features",
    "ISS": "issues",
    "ADR": "adrs",
    "OPEN": "open_questions",
    "CHG": "changes",
}

# The same file types `make check-writing` scans, so the two checks cover the
# same ground and a file cannot be subject to one and not the other.
SCANNED_SUFFIXES = (".md", ".py", ".ts", ".tsx", ".tf", ".yml", ".yaml")
SKIPPED_DIRS = {"node_modules", ".git", ".venv", "__pycache__", "dist", "coverage"}

IDENTIFIER = re.compile(rf"\b(?:{'|'.join(REGISTERS)})-\d+\b")

# A generated block, as scripts/docs/sync.py writes it.
BLOCK_START = re.compile(r"<!--\s*generated:[a-z0-9-]+\s+start\s*-->")
BLOCK_END = re.compile(r"<!--\s*generated:[a-z0-9-]+\s+end\s*-->")

# Files allowed to cite an identifier that resolves to nothing, with the reason.
# On 2026-09-28 the repository contained no unresolved citation at all, so the only
# entry here is this check's own test, which has to write citation shaped text that
# is deliberately unresolvable in order to watch the check fail. The alternative was
# to assemble those identifiers from fragments so the literal never appears, which
# hides the intent from the next reader to prop up an empty list. Every future entry
# is a real decision somebody has to defend rather than inherited noise.
EXEMPT: dict[str, str] = {
    "tests/scripts/test_check_identifiers.py": (
        "fixture data: it cites unresolvable identifiers on purpose, to prove this "
        "check still fails"
    ),
}


def known_identifiers(registry: Path) -> set[str] | None:
    """Every identifier the register defines, or None when the register is absent.

    Absent is distinguished from empty because an empty set would mark every
    citation in the project as unresolved, which reads as a catastrophe rather
    than as a missing file.
    """
    if not registry.exists():
        return None
    loaded = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    known: set[str] = set()
    for key in REGISTERS.values():
        for entry in loaded.get(key) or ():
            identifier = entry.get("id")
            if identifier:
                known.add(str(identifier))
    return known


def citations_in(text: str) -> list[tuple[int, str]]:
    """Every identifier cited in `text`, as (line number, identifier).

    Line numbers count every line including the generated ones that are skipped,
    so a reported location matches what an editor shows.
    """
    found: list[tuple[int, str]] = []
    inside_generated = False
    for number, line in enumerate(text.splitlines(), 1):
        if BLOCK_START.search(line):
            inside_generated = True
            continue
        if BLOCK_END.search(line):
            inside_generated = False
            continue
        if inside_generated:
            continue
        for match in IDENTIFIER.finditer(line):
            found.append((number, match.group(0)))
    return found


def scanned_files(root: Path) -> list[Path]:
    """Every file under `root` this check reads, sorted so output is stable."""
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in SCANNED_SUFFIXES
        and not any(part in SKIPPED_DIRS for part in path.relative_to(root).parts)
    )


def audit(root: Path | None = None) -> tuple[list[str], int, int, int] | None:
    """Unresolved citations plus the counts, or None when the register is absent.

    One pass, because the failure list and the numbers on the success line are
    two readings of the same scan and computing them separately invites them to
    disagree.
    """
    root = ROOT if root is None else root
    known = known_identifiers(root / "docs" / "registry.yaml")
    if known is None:
        return None

    problems: list[str] = []
    # Counted as it goes rather than from len(scanned_files), so the number on the
    # success line means files whose citations were actually read. Counting a file
    # that was skipped would overstate the check in the one line anybody reads.
    checked = 0
    citations = 0
    for path in scanned_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in EXEMPT:
            continue
        checked += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            problems.append(f"{relative}: cannot be read, so its citations are unchecked: {error}")
            continue
        for number, identifier in citations_in(text):
            citations += 1
            if identifier not in known:
                problems.append(
                    f"{relative}:{number} cites {identifier}, which no register defines"
                )
    return problems, len(known), checked, citations


def problems_in(root: Path | None = None) -> list[str] | None:
    """Every unresolved citation under `root`, or None when the register is absent.

    The root is a parameter so this can be pointed at a fixture tree. A checker
    with no test of its own failure paths is a checker nobody knows still fails,
    and this one is the reason a merge stops.
    """
    result = audit(root)
    return None if result is None else result[0]


def main() -> int:
    result = audit()
    if result is None:
        print("FAIL: docs/registry.yaml is missing. Every identifier resolves through it.")
        return 1

    problems, registered, files, citations = result
    if problems:
        print(f"FAIL: {len(problems)} citation(s) that no register defines\n")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nAdd the entry to docs/registry.yaml and run make doc-sync, or correct the "
            "citation. See docs/03-CHANGE-CONTROL.md for the routing rule."
        )
        return 1

    print(
        f"OK: {citations} citations across {files} files, "
        f"all resolving to {registered} registered identifiers"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
