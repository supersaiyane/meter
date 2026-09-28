"""The seven causes are spelled the same in Python and in TypeScript.

ADR-0026 promises this test by name. The vocabulary lives in five places and they move together
or not at all: `finops_core/errors.py`, the mirror in `finops_api/db/models.py`, three database
check constraints, and the `Cause` union the frontend renders from.

A seventh value reaching one and not another is how a collector writes a row nothing can read
back, and it fails in the least visible way available: the collector succeeds, the database
accepts the row, and a screen renders a cause it has no label for. Nothing in a type checker or a
migration catches that, because the two halves are different languages.

The database half is covered by `tests/db/test_models.py`. This is the half that crosses the
language boundary.
"""

from __future__ import annotations

import pathlib
import re

from finops_api.db import models
from finops_core import errors

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROVENANCE = ROOT / "finops-web" / "src" / "components" / "provenance.ts"


def declared_in_typescript() -> set[str]:
    """The members of the `Cause` union, read from the source the frontend actually compiles.

    Read rather than duplicated here, because a copy in this file would be a fourth place to
    forget and would pass while the frontend was wrong, which is the exact failure being guarded.
    """
    text = PROVENANCE.read_text(encoding="utf-8")
    block = re.search(r"export type Cause =(.*?);", text, re.S)
    assert block is not None, f"{PROVENANCE} no longer declares a Cause union"
    return set(re.findall(r"'([A-Za-z]+)'", block.group(1)))


def test_python_and_typescript_name_the_same_causes() -> None:
    in_python = {subclass.__name__ for subclass in errors.CollectionError.__subclasses__()}
    in_typescript = declared_in_typescript()
    assert in_python == in_typescript, (
        f"the cause vocabularies have diverged. Only in Python: "
        f"{sorted(in_python - in_typescript)}. Only in TypeScript: "
        f"{sorted(in_typescript - in_python)}. A cause the backend can write and the frontend "
        f"cannot name renders as a chip with no label. ADR-0026."
    )


def test_the_database_mirror_names_them_too() -> None:
    """The third copy. `ERROR_TYPES` is what the check constraints are built from."""
    in_python = {subclass.__name__ for subclass in errors.CollectionError.__subclasses__()}
    assert set(models.ERROR_TYPES) == in_python


def test_every_cause_except_nodata_has_a_label_to_render() -> None:
    """A cause with no label renders as an empty chip, which reads as a rendering fault.

    `NoData` is excluded on purpose and is the one cause that may be drawn as a number: it means
    we looked and there was nothing, which is a fact and not a refusal.
    """
    text = PROVENANCE.read_text(encoding="utf-8")
    block = re.search(r"CAUSE_LABEL[^=]*=\s*\{(.*?)\};", text, re.S)
    assert block is not None, f"{PROVENANCE} no longer declares CAUSE_LABEL"
    labelled = set(re.findall(r"^\s*([A-Za-z]+):", block.group(1), re.M))
    expected = {
        subclass.__name__
        for subclass in errors.CollectionError.__subclasses__()
        if subclass.__name__ != "NoData"
    }
    assert labelled == expected, (
        f"missing a label: {sorted(expected - labelled)}. A cause with no label renders as an "
        f"empty chip."
    )
