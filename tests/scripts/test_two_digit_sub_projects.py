"""Two digit sub projects in the memory gate and the generated task table. TASK-P10-001.

P10 is the first sub project with two digits. The memory gate's pattern took one digit after P,
so a citation of TASK-P10-001 was neither checked nor refused, simply unseen; and the task table
sorted plan files as text, which puts P10 between P1 and P2. Both scripts are loaded by path,
as the other script tests load theirs, because `scripts` is not a package.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_memory = load("check_memory", SCRIPTS / "ci" / "check_memory.py")
sync = load("sync", SCRIPTS / "docs" / "sync.py")


def row(cites: str) -> list[str]:
    return ["2026-10-07", "a task", "Done", cites, ""]


class TestTheMemoryGateSeesTwoDigits:
    def test_a_two_digit_task_is_an_identifier(self) -> None:
        assert check_memory.IDENTIFIER.findall("TASK-P10-001 and TASK-P9-013") == [
            "TASK-P10-001",
            "TASK-P9-013",
        ]

    def test_a_two_digit_task_defined_nowhere_is_refused(self) -> None:
        found = check_memory.check_row(row("built TASK-P10-999"), haystack="TASK-P10-001")
        assert found == ["2026-10-07 a task: cites TASK-P10-999, which is defined nowhere"]

    def test_a_two_digit_task_that_exists_passes(self) -> None:
        assert check_memory.check_row(row("built TASK-P10-001"), haystack="TASK-P10-001") == []


class TestPlansSortByNumber:
    def test_a_plan_is_ordered_by_its_number(self) -> None:
        names = [f"P{n}-implementation-plan.md" for n in (10, 1, 9, 0, 2)]
        ordered = sorted((Path("docs/plans") / name for name in names), key=sync.plan_order)
        assert [path.name.split("-", 1)[0] for path in ordered] == ["P0", "P1", "P2", "P9", "P10"]

    def test_the_task_table_lists_p10_after_p9(self) -> None:
        table = sync.render_task_status(None)
        assert table.index("| P9 |") < table.index("| P10 |")
