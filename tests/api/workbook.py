"""A workbook read back the way a spreadsheet reads it, with the standard library. FEAT-067.

A workbook is a zip of XML. A cell's type is an attribute and a formula is an element of its
own, so a test can ask whether a cell is a number, a string or a formula without a second
spreadsheet package in the dependency tree.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass(frozen=True)
class Cell:
    """One written cell: `kind` is the type attribute, None for a number."""

    kind: str | None
    text: str
    is_formula: bool


def sheet_names(body: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [sheet.get("name", "") for sheet in root.iter(f"{MAIN}sheet")]


def cells(body: bytes, sheet: int) -> dict[str, Cell]:
    """Every written cell of the sheet at position `sheet`, counted from one, by reference."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
    found: dict[str, Cell] = {}
    for cell in root.iter(f"{MAIN}c"):
        kind = cell.get("t")
        value = cell.find(f"{MAIN}v")
        if kind == "inlineStr":
            text = "".join(part.text or "" for part in cell.iter(f"{MAIN}t"))
        else:
            text = "" if value is None or value.text is None else value.text
        found[cell.get("r", "")] = Cell(
            kind=kind, text=text, is_formula=cell.find(f"{MAIN}f") is not None
        )
    return found


def column(written: dict[str, Cell], letter: str) -> list[str]:
    """One column's texts, top to bottom."""
    rows = sorted(
        (int(re.sub(r"[A-Z]+", "", reference)), cell.text)
        for reference, cell in written.items()
        if re.sub(r"\d+", "", reference) == letter
    )
    return [text for _, text in rows]


def pairs(written: dict[str, Cell]) -> dict[str, str]:
    """The About sheet's fields and values, by field."""
    return dict(zip(column(written, "A"), column(written, "B"), strict=False))
