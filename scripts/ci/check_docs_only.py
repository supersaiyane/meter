#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Lets a change to documents alone skip the code suites, and refuses that
# shortcut to any change that touches anything else, naming the file that needs the full gate.
# Grade B here: copy it, then replace the document suffixes and directories named below.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Refuse `make verify-docs` to any change that is not documents alone.

`make verify` runs every test the project has, about fifteen minutes of backend tests alone, and
on 2026-10-07 it ran that long for a thirteen line change to `project_map.md`. A change to
documents alone cannot fail a code test, because no code test reads a document; what it can fail
are the writing rules, the generated documents and the memory, and `make verify-docs` runs those.

The shortcut is only safe while nothing but documents changed, so this decides that, from git
rather than from anybody's word: every path committed since the branch left its base, every
staged or unstaged change, and every untracked file. A symbolic link is not counted, because a
worktree links the main checkout's `.venv` and `node_modules` rather than installing its own,
and that is tooling rather than a change. Anything else refuses the shortcut by name.

Usage:
  scripts/ci/check_docs_only.py                 against main
  scripts/ci/check_docs_only.py --base BRANCH   against the branch this one will merge into
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: A file with one of these endings is a document wherever it lives.
DOCUMENT_SUFFIXES = (".md", ".txt")
#: Everything under these is a document: the registry, specs, plans, ADRs, status and issues.
DOCUMENT_DIRECTORIES = ("docs/", "tasks/")

DEFAULT_BASE = "main"


class GitError(RuntimeError):
    """git could not answer, so whether the change is documents alone is unknown."""


def is_document(path: str) -> bool:
    """Whether a repository relative path is a document."""
    return path.endswith(DOCUMENT_SUFFIXES) or path.startswith(DOCUMENT_DIRECTORIES)


def not_documents(paths: Iterable[str]) -> list[str]:
    """The paths that are not documents, sorted, each once."""
    return sorted({path for path in paths if not is_document(path)})


def _git(*args: str, cwd: Path) -> list[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def changed_paths(base: str, cwd: Path = ROOT) -> set[str]:
    """Every path this branch changes against `base`, committed or not, links aside."""
    fork = _git("merge-base", "HEAD", base, cwd=cwd)[0]
    committed = _git("diff", "--name-only", "--no-renames", fork, "HEAD", cwd=cwd)
    working = _git("diff", "--name-only", "--no-renames", "HEAD", cwd=cwd)
    untracked = [
        path
        for path in _git("ls-files", "--others", "--exclude-standard", cwd=cwd)
        if not (cwd / path.rstrip("/")).is_symlink()
    ]
    return {*committed, *working, *untracked}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args()
    try:
        changed = changed_paths(args.base)
    except GitError as error:
        print(f"FAIL: cannot tell what changed against {args.base}, so run make verify. {error}")
        return 2
    refused = not_documents(changed)
    if refused:
        print(
            f"FAIL: these are not documents, so this change needs make verify: {', '.join(refused)}"
        )
        return 1
    print(f"OK: {len(changed)} changed files against {args.base}, all documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
