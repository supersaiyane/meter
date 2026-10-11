"""Rotation is the only thing in the project that deletes memory.

`scripts/docs/rotate_checkpoint.py` rewrites `docs/checkpoint.md` in place and
moves rows out of it. If it drops a row, the record of what happened is gone
and there is nothing to restore it from. Its real path had never executed
before these tests, because the live log sat at 47 entries against a threshold
of 50, so every one of these cases is a path that had never run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "docs" / "rotate_checkpoint.py"

spec = importlib.util.spec_from_file_location("rotate_checkpoint", SCRIPT)
assert spec and spec.loader
rotate = importlib.util.module_from_spec(spec)
sys.modules["rotate_checkpoint"] = rotate
spec.loader.exec_module(rotate)

PREAMBLE = ["# Checkpoint log", "", "Some prose.", "", rotate.HEADER, rotate.SEPARATOR]
TAIL = ["", "## A prose section after the table", "", "Words."]


def build(count: int) -> list[str]:
    rows = [
        f"| 2026-08-{i:02d} | Task {i} | Done | Changed {i} | Vector {i} |"
        for i in range(1, count + 1)
    ]
    return PREAMBLE + rows + TAIL


def test_below_threshold_is_a_no_operation() -> None:
    lines = build(47)
    kept, moved = rotate.plan_rotation(lines)
    assert moved == []
    assert kept == lines


def test_exactly_at_the_threshold_does_not_rotate() -> None:
    _kept, moved = rotate.plan_rotation(build(50))
    assert moved == []


def test_above_the_threshold_keeps_the_latest_twenty() -> None:
    kept, moved = rotate.plan_rotation(build(51))
    assert len(moved) == 31
    assert len(rotate.row_indexes(kept)) == 20


def test_no_entry_is_ever_lost() -> None:
    original = build(80)
    kept, moved = rotate.plan_rotation(original)
    rows_before = [original[i] for i in rotate.row_indexes(original)]
    rows_after = moved + [kept[i] for i in rotate.row_indexes(kept)]
    assert rows_after == rows_before


def test_the_oldest_rows_are_the_ones_that_move() -> None:
    kept, moved = rotate.plan_rotation(build(60))
    assert "Task 1 " in moved[0]
    assert "Task 60 " in kept[rotate.row_indexes(kept)[-1]]


def test_prose_around_the_table_survives() -> None:
    kept, _ = rotate.plan_rotation(build(60))
    assert kept[: len(PREAMBLE)] == PREAMBLE
    assert kept[-len(TAIL) :] == TAIL


def test_a_split_table_is_refused_rather_than_guessed() -> None:
    lines = build(60)
    lines.insert(rotate.row_indexes(lines)[10], "An interrupting paragraph.")
    with pytest.raises(ValueError):
        rotate.plan_rotation(lines)


def test_a_log_with_no_entries_is_left_alone() -> None:
    kept, moved = rotate.plan_rotation(PREAMBLE + TAIL)
    assert moved == []
    assert kept == PREAMBLE + TAIL
