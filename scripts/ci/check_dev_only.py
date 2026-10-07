#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Enforces the development only claims the accepted npm findings depend
# on. A package accepted because it never ships must fail the build the day it starts to.
# Grade B here: copy it, then replace the frontend directory and the package to advisory map.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Enforce the development only claims in security/policy/accepted.yaml.

ADR-0018 accepts an unfixable npm finding when the package is only ever a development
dependency: it runs in the build and the tests, and `docker/Dockerfile.web` copies nothing but
the built `dist` into the image that serves the application. That stays true only while no
production dependency pulls the package in, so each such package becomes a build failure the
moment npm's production tree contains it.

The map below and the acceptance file must agree, as in check_forbidden_imports.py: a rule
whose acceptance was withdrawn fails as well.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
ACCEPTED = ROOT / "security" / "policy" / "accepted.yaml"
FRONTEND = ROOT / "finops-web"

# package -> the advisory whose acceptance depends on the package never shipping
DEVELOPMENT_ONLY = {
    "source-map-js": "1241209",
}

Tree = Mapping[str, Any]


def production_tree(frontend: Path = FRONTEND) -> Tree:
    """npm's dependency tree with the development dependencies left out."""
    result = subprocess.run(
        ["npm", "ls", "--omit=dev", "--all", "--json"],
        cwd=frontend,
        capture_output=True,
        text=True,
        check=False,
    )
    # npm ls exits 1 for a problem in a tree it still prints, so the exit code says nothing on
    # its own. A tree that does not parse does.
    try:
        tree = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"npm ls printed no tree: {result.stderr.strip()}") from exc
    if not isinstance(tree, dict):
        raise RuntimeError("npm ls printed something other than a tree")
    return tree


def packages_in(tree: Tree) -> Iterator[str]:
    for name, node in (tree.get("dependencies") or {}).items():
        yield name
        yield from packages_in(node)


def accepted_ids(path: Path = ACCEPTED) -> set[str]:
    data = yaml.safe_load(path.read_text()) or {}
    return {str(entry.get("id")) for entry in data.get("accepted") or []}


def problems(tree: Tree, accepted: set[str]) -> list[str]:
    shipped = set(packages_in(tree))
    found: list[str] = []
    for package, advisory in DEVELOPMENT_ONLY.items():
        if package in shipped:
            found.append(
                f"`{package}` is in the production dependency tree.\n"
                f"    Advisory {advisory} is accepted as unfixable ONLY because the package is a\n"
                f"    development dependency and never ships. Either keep it out of the\n"
                f"    production tree, or withdraw the acceptance in\n"
                f"    security/policy/accepted.yaml and find another answer."
            )
        if advisory not in accepted:
            found.append(
                f"`{package}` is held to development only for advisory {advisory}, which is no\n"
                f"    longer in security/policy/accepted.yaml. Remove the rule or restore the\n"
                f"    acceptance."
            )
    return found


def main(
    tree_of: Callable[[], Tree] = production_tree,
    accepted: Path = ACCEPTED,
) -> int:
    try:
        tree = tree_of()
    except (RuntimeError, OSError) as exc:
        print(f"FAIL: could not read npm's production tree. {exc}")
        return 2
    found = problems(tree, accepted_ids(accepted))
    if found:
        print(f"FAIL: {len(found)} problem(s)\n")
        for problem in found:
            print(f"  {problem}")
        print("\nSee ADR-0018 and security/policy/accepted.yaml.")
        return 1
    print(
        f"OK: none of the {len(DEVELOPMENT_ONLY)} packages accepted as development only is in "
        f"the production tree"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
