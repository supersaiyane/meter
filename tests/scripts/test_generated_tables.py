"""Every table the documentation generator writes renders as a table.

GitHub draws a Markdown table only when its delimiter row has as many cells as its header, and a
row with more cells than the header loses the rest. The change log's delimiter had seven cells
under a six cell header from the day `scripts/docs/sync.py` was written, so INDEX.md showed the
whole log as raw text, found by the owner on 2026-10-17. Every renderer's output is held to it
here, and so is every table in the documents the generator writes, where a pipe inside a
registry entry would break a row the same way. The generator is loaded by path, as the other
script tests load theirs, because `scripts` is not a package.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: A cell boundary: a pipe nobody escaped.
PIPE = re.compile(r"(?<!\\)\|")
#: A table's delimiter row, `| --- | :---: |`.
DELIMITER = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
#: The documents `make doc-sync` writes tables into.
GENERATED = ("INDEX.md", "tasks/STATUS.md", "tasks/ISSUES.md", "docs/01-ROADMAP.md")


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sync = load("sync", ROOT / "scripts" / "docs" / "sync.py")
RENDERERS = sorted(name for name in vars(sync) if name.startswith("render_"))


def cells(line: str) -> int:
    """How many cells a table row has: `| a | b |` has two."""
    return len(PIPE.split(line.strip())) - 2


def mismatches(text: str) -> list[str]:
    """Each delimiter or row whose cell count differs from its table's header, by line."""
    found: list[str] = []
    header: int | None = None
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.startswith("|"):
            header = None
        elif DELIMITER.match(line) and number > 1 and lines[number - 2].startswith("|"):
            header = cells(lines[number - 2])
            if cells(line) != header:
                found.append(f"{number}: a delimiter of {cells(line)} cells under {header}")
        elif header is not None and cells(line) != header:
            found.append(f"{number}: a row of {cells(line)} cells under a header of {header}")
    return found


def test_the_check_finds_the_fault_it_exists_for() -> None:
    table = "| a | b |\n| --- | --- | --- |\n| 1 | 2 |\n| 1 | 2 | 3 |\n\n| c |\n| --- |\n| 4 |"
    assert mismatches(table) == [
        "2: a delimiter of 3 cells under 2",
        "4: a row of 3 cells under a header of 2",
    ]
    assert mismatches("| a \\| b |\n| --- |\n| one \\| cell |") == []


def test_there_are_renderers_to_check() -> None:
    assert "render_changes" in RENDERERS and len(RENDERERS) > 5


@pytest.mark.parametrize("name", RENDERERS)
def test_every_table_a_renderer_writes_has_as_many_cells_as_its_header(name: str) -> None:
    assert mismatches(getattr(sync, name)(sync.load())) == []


@pytest.mark.parametrize("document", GENERATED)
def test_every_table_in_a_generated_document_renders(document: str) -> None:
    assert mismatches((ROOT / document).read_text(encoding="utf-8")) == []
