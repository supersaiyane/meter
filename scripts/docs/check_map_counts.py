#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Every count in project_map.md is derived from the source here, so a
# stale number fails the build instead of waiting for somebody to sweep the file.
# Grade B here: copy it, then replace the COUNTS table with this project's own derivations.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Derive every count in project_map.md from the source, and refuse a stale one.

**Why this exists, from the record rather than from principle.** Three sweeps of
`project_map.md` on 2026-09-26 and 2026-09-27 found stale counts every time. The suite count
was two sub projects behind. The journey count was nine behind, written when there was one
spec file. The screens count, the route count and the migrations list were all wrong on the
third sweep, and the migrations list was the worst of them: a list of revisions that silently
stops being a list of revisions is how a reader concludes the schema has not changed.

The lesson of 2026-08-23 already said to commit documentation with the change that made it
stale, and it was broken three times, so the rule was wrong rather than under-applied. It asked
somebody to remember, at the end of a task, which prose numbers a change had moved. Nothing
surfaced them and nothing failed. This is the thing that fails.

**Two checks, and the second is the one that caught the worst defect.**

The counts, written into a generated block so no prose line carries a number that can drift.

And the completeness of the migrations listing: every revision file has to be named somewhere
in the map. A count alone would have passed a listing that stopped at 0014 while the directory
held sixteen files, because the count and the listing were two different claims and only one of
them was being made.

**What is deliberately not checked.** The pytest collected total, which is what `make verify`
prints and includes every parametrised expansion. Only pytest can produce it, and shelling out
to collect the suite inside a documentation check would make the fast gate slow. So the map
states what is statically countable, test files and test functions, and does not repeat a
figure it cannot verify.

Usage:
  scripts/docs/check_map_counts.py            write the generated block
  scripts/docs/check_map_counts.py --check    fail if it would change
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "project_map.md"

START = "<!-- generated:map-counts start -->"
END = "<!-- generated:map-counts end -->"
NOTICE = (
    "<!-- This block is GENERATED from the source by scripts/docs/check_map_counts.py. "
    "Hand edits here are overwritten and make check-docs will fail. Every figure below is "
    "derived, which is the point: three sweeps in two days found stale counts in this file "
    "when they were written by hand. See ADR-0014 and tasks/lessons.md. -->"
)

#: The interface declaration, which is not a nav entry. Counting it would report one screen
#: more than exists, forever, and the number would look plausible.
DECLARATION = "readonly arrives:"


def _sections() -> tuple[int, int]:
    """Screens built and screens declared, from the `arrives` field in sections.ts.

    `arrives: null` means built. The field exists precisely so this figure is derived rather
    than stated, which the map's own line has said for three sub projects while stating it
    anyway.
    """
    text = (ROOT / "finops-web/src/shell/sections.ts").read_text(encoding="utf-8")
    entries = [line for line in text.splitlines() if "arrives:" in line and DECLARATION not in line]
    built = [line for line in entries if "arrives: null" in line]
    return len(built), len(entries)


def _journeys() -> tuple[int, int]:
    """Playwright journeys and the files holding them.

    Counted by the `test(` call rather than by the file, because the map said five journeys for
    three sub projects while there were fifteen across four files, and the file count was the
    number that happened to be right when the line was written.
    """
    files = sorted((ROOT / "finops-web/e2e").glob("*.spec.ts"))
    calls = sum(
        len(re.findall(r"^\s*test\(", path.read_text(encoding="utf-8"), re.MULTILINE))
        for path in files
    )
    return calls, len(files)


def _routes(module: str) -> int:
    path = ROOT / "finops_api/routes" / module
    return len(re.findall(r"^@router\.", path.read_text(encoding="utf-8"), re.MULTILINE))


def _collectors() -> int:
    return len(
        [
            path
            for path in (ROOT / "finops_ingest/collectors").glob("*.py")
            if path.name != "__init__.py"
        ]
    )


def _revisions() -> list[str]:
    return sorted(path.stem for path in (ROOT / "migrations/versions").glob("*.py"))


def _test_files() -> int:
    return len(list((ROOT / "tests").rglob("test_*.py")))


def _test_functions() -> int:
    """Test functions, not the pytest collected total.

    The two differ by every parametrised expansion, and only pytest can produce the second.
    Counting functions here is the honest version of a number a documentation check can verify,
    and the map says which of the two it is stating.
    """
    found = 0
    for path in (ROOT / "tests").rglob("test_*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            # A test file that does not parse is a problem for the linter rather than for this
            # check, and failing here would report it as a documentation fault.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                found += 1
    return found


@dataclass(frozen=True)
class Count:
    """One figure, how it is derived, and the words the map uses for it.

    `derivation` is not decoration. A reader who disagrees with a number needs to know which
    command would settle it, and a generated figure with no stated source is one they have to
    trust.
    """

    label: str
    value: Callable[[], str]
    derivation: str


COUNTS: tuple[Count, ...] = (
    Count(
        "Screens built",
        lambda: "{} of {}".format(*_sections()),
        "`arrives: null` in finops-web/src/shell/sections.ts",
    ),
    Count(
        "Playwright journeys",
        lambda: "{} in {} spec files".format(*_journeys()),
        "`test(` calls in finops-web/e2e/*.spec.ts",
    ),
    Count(
        "Inventory routes",
        lambda: str(_routes("inventory.py")),
        "`@router.` in finops_api/routes/inventory.py",
    ),
    Count(
        "Collectors",
        lambda: str(_collectors()),
        "modules in finops_ingest/collectors, excluding __init__",
    ),
    Count(
        "Migration revisions",
        lambda: str(len(_revisions())),
        "files in migrations/versions, all of which are listed below in this file",
    ),
    Count(
        "Test files",
        lambda: str(_test_files()),
        "test_*.py under tests/",
    ),
    Count(
        "Test functions",
        lambda: str(_test_functions()),
        (
            "functions named test_* under tests/. Not the pytest collected total, which "
            "counts every parametrised expansion and which only `make verify` can report"
        ),
    ),
)


def render() -> str:
    lines = [
        START,
        NOTICE,
        "",
        "| Counted | Now | Derived from |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {one.label} | {one.value()} | {one.derivation} |" for one in COUNTS]
    lines += [
        "",
        "No prose line in this file repeats a figure from this table. That is the rule, and it",
        "exists because the figures in the prose were wrong on three consecutive sweeps.",
        "",
        END,
    ]
    return "\n".join(lines)


def unlisted_revisions(text: str) -> list[str]:
    """Revisions the map never names.

    The check that caught the worst of the three sweeps. A count alone passes a listing that
    stopped at 0014 while the directory held sixteen files, because the count and the listing
    are two different claims and only one of them was being made.
    """
    return [revision for revision in _revisions() if revision not in text]


def replaced(text: str, block: str) -> str:
    if START not in text or END not in text:
        raise SystemExit(
            f"FAIL: project_map.md has no {START} block. Add the markers where the counts "
            "should appear, then run 'make doc-sync'."
        )
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    return f"{head}{block}{tail}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    current = MAP.read_text(encoding="utf-8")
    wanted = replaced(current, render())
    missing = unlisted_revisions(current)

    if not args.check:
        MAP.write_text(wanted, encoding="utf-8")
        print(f"project_map.md counts regenerated, {len(COUNTS)} figures")
        if missing:
            # Written anyway, then reported. The counts being right is worth having even on a
            # run where the listing is incomplete, and the next line says what is still wrong.
            print(f"WARN: these revisions are not named anywhere in the map: {missing}")
        return 0

    # Each fault carries its own remediation. A single line naming both fixes would send
    # somebody to run doc-sync for a missing revision, which doc-sync cannot add, and ISS-152
    # is the record of what naming the wrong cause costs.
    problems: list[tuple[str, str]] = []
    if current != wanted:
        problems.append(("the counts are out of step with the source", "Run 'make doc-sync'."))
    if missing:
        problems.append(
            (
                f"these revisions are not named anywhere in the map: {missing}",
                "Add a line for each under migrations/versions in the map, by hand. "
                "doc-sync cannot write prose and will not fix this.",
            )
        )

    if problems:
        for problem, remediation in problems:
            print(f"FAIL: project_map.md, {problem}.")
            print(f"  {remediation}")
        return 1
    print(f"OK: project_map.md, {len(COUNTS)} counts match the source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
