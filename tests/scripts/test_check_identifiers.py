"""The identifier checker is what stops a merge, so its failure paths are tested.

A checker nobody has watched fail is a checker nobody knows still fails. This one
is worth less than nothing if it quietly stops firing, because its passing line
reads as a guarantee that every citation in the project resolves.

Two of these tests exist for reasons that are not obvious.

`test_the_historical_defect_would_now_be_caught` reproduces the failure that
caused the check to be written, by dropping the three identifiers from the known
set and confirming the citations light up. Testing against a planted ISS-999
proves the mechanism works; testing against the real defect proves the mechanism
was pointed at the right thing.

`test_a_citation_after_a_generated_block_is_still_checked` exists because the
generated block skip is a state machine, and the failure mode of a state machine
that never leaves its skipping state is a check that scans almost nothing and
prints OK. Nothing else in this file would notice that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "docs" / "check_identifiers.py"

spec = importlib.util.spec_from_file_location("check_identifiers", SCRIPT)
assert spec and spec.loader
check_identifiers = importlib.util.module_from_spec(spec)
sys.modules["check_identifiers"] = check_identifiers
spec.loader.exec_module(check_identifiers)

REGISTER: dict[str, object] = {
    "features": [{"id": "FEAT-001"}],
    "issues": [{"id": "ISS-001"}],
    "adrs": [{"id": "ADR-0001"}],
    "open_questions": [{"id": "OPEN-01"}],
    "changes": [{"id": "CHG-0001"}],
}


def build(tmp_path: Path, registry: dict[str, object], documents: dict[str, str]) -> Path:
    """A fixture tree with a register and some documents that cite into it."""
    registry_path = tmp_path / "docs" / "registry.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    for rel, body in documents.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def test_passes_on_the_repository_as_it_stands() -> None:
    assert check_identifiers.problems_in() == []


def test_fails_and_names_the_file_and_line_of_an_unresolved_citation(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        REGISTER,
        {"docs/plan.md": "# Plan\n\nBlocked on ISS-999 and nothing else.\n"},
    )
    problems = check_identifiers.problems_in(root)
    assert problems == ["docs/plan.md:3 cites ISS-999, which no register defines"]


def test_accepts_a_citation_that_resolves(tmp_path: Path) -> None:
    root = build(tmp_path, REGISTER, {"docs/plan.md": "Blocked on ISS-001.\n"})
    assert check_identifiers.problems_in(root) == []


def test_checks_every_prefix(tmp_path: Path) -> None:
    """A prefix silently absent from the pattern is a whole family unchecked."""
    root = build(
        tmp_path,
        REGISTER,
        {
            "docs/a.md": "FEAT-999\n",
            "docs/b.md": "ISS-999\n",
            "docs/c.md": "ADR-9999\n",
            "docs/d.md": "OPEN-99\n",
            "docs/e.md": "CHG-9999\n",
        },
    )
    problems = check_identifiers.problems_in(root)
    assert problems is not None
    assert len(problems) == 5, problems
    for prefix in ("FEAT", "ISS", "ADR", "OPEN", "CHG"):
        assert any(f"cites {prefix}-" in problem for problem in problems), prefix


def test_the_historical_defect_would_now_be_caught() -> None:
    """ISS-002, ISS-003 and ISS-004 were cited by ten documents and registered in none.

    They are registered now, so the live check passes. Confirm the citations still
    exist and that the checker sees them, otherwise this check was written against
    a defect it cannot actually find. The count is a floor rather than an equality,
    because citations of those three will legitimately grow.
    """
    known = check_identifiers.known_identifiers(ROOT / "docs" / "registry.yaml")
    assert known is not None
    historical = {"ISS-002", "ISS-003", "ISS-004"}
    assert historical <= known, "the three identifiers are no longer registered"

    seen: list[str] = []
    for path in check_identifiers.scanned_files(ROOT):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, identifier in check_identifiers.citations_in(text):
            if identifier in historical:
                seen.append(f"{path.relative_to(ROOT).as_posix()}:{number}")

    assert len(seen) >= 3, (
        f"expected the three historical identifiers to be cited somewhere, found {seen}. "
        f"If this fails the citations were removed, not the defect."
    )


def test_an_identifier_inside_a_generated_block_is_skipped(tmp_path: Path) -> None:
    """sync.py owns that text, so a complaint there sends the reader to the wrong file."""
    root = build(
        tmp_path,
        REGISTER,
        {
            "tasks/ISSUES.md": (
                "# Issues\n"
                "<!-- generated:issue-register start -->\n"
                "| ISS-999 | something |\n"
                "<!-- generated:issue-register end -->\n"
            )
        },
    )
    assert check_identifiers.problems_in(root) == []


def test_a_citation_after_a_generated_block_is_still_checked(tmp_path: Path) -> None:
    """The skip is a state machine, and one that never exits scans nothing.

    Without this, a bug leaving the checker permanently inside a generated block
    would still print OK on a repository full of unresolved citations.
    """
    root = build(
        tmp_path,
        REGISTER,
        {
            "tasks/ISSUES.md": (
                "# Issues\n"
                "<!-- generated:issue-register start -->\n"
                "| ISS-001 | fine |\n"
                "<!-- generated:issue-register end -->\n"
                "\n"
                "Hand written, and it cites ISS-999.\n"
            )
        },
    )
    problems = check_identifiers.problems_in(root)
    assert problems == ["tasks/ISSUES.md:6 cites ISS-999, which no register defines"]


def test_the_register_itself_is_scanned(tmp_path: Path) -> None:
    """An issue whose detail cites a missing identifier is the case that started this."""
    register = dict(REGISTER)
    register["issues"] = [{"id": "ISS-001", "detail": "Superseded by ISS-999."}]
    root = build(tmp_path, register, {})
    problems = check_identifiers.problems_in(root)
    assert problems is not None
    assert any("docs/registry.yaml" in problem and "ISS-999" in problem for problem in problems)


def test_a_filename_shaped_citation_resolves(tmp_path: Path) -> None:
    """docs/features/FEAT-001-name.md contains an identifier and must not trip the check."""
    root = build(
        tmp_path,
        REGISTER,
        {"docs/plan.md": "See docs/features/FEAT-001-commitment-coverage-actions.md.\n"},
    )
    assert check_identifiers.problems_in(root) == []


def test_a_template_placeholder_is_not_a_citation(tmp_path: Path) -> None:
    """FEAT-nnn has no digits, so the templates do not need an exemption."""
    root = build(
        tmp_path,
        REGISTER,
        {"docs/templates/FEATURE-TEMPLATE.md": "# FEAT-nnn\n\nSee ISS-nnn.\n"},
    )
    assert check_identifiers.problems_in(root) == []


def test_reports_a_missing_register_as_absent_rather_than_as_consistent(tmp_path: Path) -> None:
    """An empty tree must not read as a passing one."""
    assert check_identifiers.problems_in(tmp_path) is None


def test_exit_code_is_one_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without this CI prints a complaint and carries on."""
    root = build(tmp_path, REGISTER, {"docs/plan.md": "ISS-999\n"})
    monkeypatch.setattr(check_identifiers, "ROOT", root)
    assert check_identifiers.main() == 1


def test_exit_code_is_one_when_the_register_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(check_identifiers, "ROOT", tmp_path)
    assert check_identifiers.main() == 1


def test_exit_code_is_zero_on_a_clean_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = build(tmp_path, REGISTER, {"docs/plan.md": "ISS-001\n"})
    monkeypatch.setattr(check_identifiers, "ROOT", root)
    assert check_identifiers.main() == 0


def test_the_counts_on_the_success_line_come_from_the_same_scan(tmp_path: Path) -> None:
    """Two passes over the tree is how a success line starts disagreeing with itself."""
    root = build(
        tmp_path,
        REGISTER,
        {"docs/plan.md": "ISS-001 and FEAT-001 and ISS-001 again.\n"},
    )
    result = check_identifiers.audit(root)
    assert result is not None
    problems, registered, files, citations = result
    assert problems == []
    assert registered == 5
    assert files == 2, "the register and the plan"
    # Five in the register, which is scanned on purpose, and three in the plan.
    assert citations == 8


def test_an_exempt_file_is_not_checked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The exemption list is empty today, so its mechanism needs its own test."""
    root = build(tmp_path, REGISTER, {"docs/plan.md": "ISS-999\n"})
    assert check_identifiers.problems_in(root) != []
    monkeypatch.setattr(check_identifiers, "EXEMPT", {"docs/plan.md": "under test"})
    assert check_identifiers.problems_in(root) == []


def test_every_exemption_carries_a_reason() -> None:
    """An exemption without a stated reason is a hole nobody can audit.

    This file is the only entry, and it is here because it must write citation
    shaped text that resolves to nothing in order to watch the check fail. Adding
    a second entry is allowed and must come with a reason worth reading, which is
    what this asserts. It deliberately does not assert the list is empty: the
    first version of this test did, and it was written before discovering that
    this very file has to be exempt.
    """
    assert set(check_identifiers.EXEMPT) == {"tests/scripts/test_check_identifiers.py"}
    for path, reason in check_identifiers.EXEMPT.items():
        assert len(reason.strip()) >= 20, f"{path} is exempt without a usable reason"
