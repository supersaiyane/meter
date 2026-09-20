"""The index checker is what stops a merge, so its failure paths are tested.

A checker nobody has watched fail is a checker nobody knows still fails. This
one guards the claim that INDEX.md is the entry point and that everything in the
project is reachable from it, which is worth nothing the moment the check
quietly stops firing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "docs" / "check_index.py"

spec = importlib.util.spec_from_file_location("check_index", SCRIPT)
assert spec and spec.loader
check_index = importlib.util.module_from_spec(spec)
sys.modules["check_index"] = check_index
spec.loader.exec_module(check_index)


def build(tmp_path: Path, index: str, documents: dict[str, str]) -> Path:
    (tmp_path / "INDEX.md").write_text(index, encoding="utf-8")
    for rel, body in documents.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def test_passes_on_the_repository_as_it_stands() -> None:
    assert check_index.problems_in() == []


def test_fails_with_a_clear_message_when_a_linked_path_is_missing(tmp_path: Path) -> None:
    root = build(tmp_path, "# Index\n\n[Goal](docs/00-GOAL.md)\n", {})
    problems = check_index.problems_in(root)
    assert problems is not None
    assert any("missing path: docs/00-GOAL.md" in problem for problem in problems)


def test_fails_when_a_document_is_not_linked_from_the_index(tmp_path: Path) -> None:
    # A document nothing points at is a document nobody finds, which is the same
    # as not having written it.
    root = build(tmp_path, "# Index\n", {"docs/orphan.md": "# Orphan\n"})
    problems = check_index.problems_in(root)
    assert problems is not None
    assert any("Not referenced from INDEX.md: docs/orphan.md" in p for p in problems)


def test_accepts_a_consistent_tree(tmp_path: Path) -> None:
    root = build(tmp_path, "# Index\n\n[Goal](docs/goal.md)\n", {"docs/goal.md": "# Goal\n"})
    assert check_index.problems_in(root) == []


def test_reports_a_missing_index_as_absent_rather_than_as_consistent(tmp_path: Path) -> None:
    # An empty tree must not read as a passing one.
    assert check_index.problems_in(tmp_path) is None


def test_ignores_external_links(tmp_path: Path) -> None:
    root = build(tmp_path, "# Index\n\n[Spec](https://example.invalid/thing)\n", {})
    assert check_index.problems_in(root) == []


def test_exit_code_is_one_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without this CI prints a complaint and carries on."""
    monkeypatch.setattr(check_index, "ROOT", tmp_path)
    monkeypatch.setattr(check_index, "INDEX", tmp_path / "INDEX.md")
    assert check_index.main() == 1


def test_every_plan_file_reaches_the_task_table() -> None:
    """The sub project list used to be a literal, ("P0", "P2").

    P1's plan was written on 2026-09-18 and the table did not mention it.
    Thirteen tasks were absent rather than shown as not started, which
    understates the work by a whole sub project and reads exactly like a sub
    project nobody has planned. Derived now, and held to it here, so the next
    plan is counted the day it is added rather than the day somebody notices.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    plans = {
        path.name.split("-", 1)[0] for path in root.glob("docs/plans/P*-implementation-plan.md")
    }
    assert plans, "no plan files found, which means this test is checking nothing"

    status = (root / "tasks" / "STATUS.md").read_text(encoding="utf-8")
    missing = {sub for sub in plans if f"| {sub} |" not in status}
    assert not missing, (
        f"these sub projects have a plan and are absent from the task table in "
        f"tasks/STATUS.md: {sorted(missing)}. Run make doc-sync."
    )
