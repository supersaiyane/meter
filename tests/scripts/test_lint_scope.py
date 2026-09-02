"""Everything Python in this repository is linted and type checked.

`scripts/` and `migrations/` sat outside `PY_SRC` for long enough to accumulate
ten ruff findings and thirty six mypy errors that nothing ever reported. Two of
those were real defects rather than style: a list annotated flat while it held
groups, and an allowlist loader whose signature said its key was a string while
the code keyed on a tuple.

That second one matters more than it looks. The signature is the only place a
reader can learn what an allowlist or acceptance entry has to match on, and it
was wrong, which is an afternoon of entries that silently match nothing.

The directories that were missed are the scripts that implement the gates. A
gate nobody checks is the failure this project keeps finding, and leaving the
checkers themselves unchecked was an instance of it. So this test does not
assert that those two directories are listed: it asks the filesystem which
directories hold Python and asserts that each one is covered, so the next
directory somebody adds cannot be forgotten in the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"

#: Directories that hold Python and are deliberately not linted. Empty, and it
#: should stay that way. An entry here needs a reason next to it.
EXEMPT: frozenset[str] = frozenset()

#: Not source. Build output, caches, the virtualenv and the frontend's own tree,
#: which has its own linter.
IGNORED = {".venv", "node_modules", "__pycache__", ".git", "finops-web", "docs", "infra"}


def makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _assignment(name: str) -> list[str]:
    found = re.search(rf"^{name} :?= (.+)$", makefile(), re.M)
    assert found is not None, f"{name} is not defined in the Makefile"
    return found.group(1).split()


def expand(entries: list[str]) -> set[str]:
    """Resolve `$(PY_PKGS)` and `$(PY_SRC)` to the directories they name."""
    resolved: set[str] = set()
    for entry in entries:
        if entry == "$(PY_PKGS)":
            resolved |= expand(_assignment("PY_PKGS"))
        elif entry == "$(PY_SRC)":
            resolved |= expand(_assignment("PY_SRC"))
        else:
            resolved.add(entry)
    return resolved


def linted_paths() -> set[str]:
    """What `ruff` is pointed at."""
    return expand(_assignment("PY_SRC"))


def type_checked_paths() -> set[str]:
    """What `mypy` is pointed at in the lint target."""
    found = re.search(r"^\t\$\(BIN\)/mypy (.+)$", makefile(), re.M)
    assert found is not None, "the lint target no longer runs mypy"
    return expand(found.group(1).split())


def directories_holding_python() -> set[str]:
    """Top level directories with a .py file somewhere under them."""
    found = set()
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if len(relative.parts) < 2 or set(relative.parts) & IGNORED:
            continue
        found.add(relative.parts[0])
    return found


def test_every_python_directory_is_linted() -> None:
    missed = directories_holding_python() - linted_paths() - EXEMPT

    assert directories_holding_python(), "expected to find Python, not an empty tree"
    assert missed == set(), f"these hold Python and ruff never sees them: {sorted(missed)}"


def test_every_python_directory_is_type_checked() -> None:
    """mypy was pointed at four packages by name and silently skipped
    finops_mcp as well as the two directories this test was written for."""
    missed = directories_holding_python() - type_checked_paths() - EXEMPT

    assert missed == set(), f"these hold Python and mypy never sees them: {sorted(missed)}"


def test_the_two_scopes_are_the_same() -> None:
    """Two lists of what to check is how one of them falls behind.

    They were different: ruff covered five packages plus tests, and mypy covered
    four packages by name, silently skipping finops_mcp as well as scripts,
    migrations and the whole test suite. Both now expand the same variable.
    """
    assert linted_paths() == type_checked_paths()


def test_nothing_is_exempt_without_a_reason() -> None:
    """The exemption set exists so an exemption is a visible decision. It is
    empty, and a future entry should arrive with a comment beside it."""
    assert frozenset() == EXEMPT
