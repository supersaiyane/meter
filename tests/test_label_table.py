"""Every label TASK-P8-004's table approved is drawn, P8 spec section 12 item 2.

`docs/specs/2026-10-05-p8-label-table.md` lists each label as it was, what it became and why,
and the owner approved it as written. A label the table changed that the web source never
draws is a change that did not happen, so each approved label is looked for, as written, in
the source every screen is drawn from. That no code or collector is shown raw is held over the
rendered screens by `finops-web/src/screens/__tests__/rawIdentifiers.test.tsx`.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "docs" / "specs" / "2026-10-05-p8-label-table.md"
WEB = ROOT / "finops-web" / "src"

#: The column that names what a row was, and the one that names what it became, by table.
HEADERS = {"Today", "Code", "Kind"}
UNCHANGED = "unchanged"

#: Approved and then superseded, each for the reason given. The Overview this label named was
#: redrawn by TASK-P8-012 as drawn on 2026-10-05: its tile reads Effective Cost with the period
#: beneath it, and Cost Explorer composes the same words from the measure it shows.
SUPERSEDED = frozenset({"Effective Cost, this period"})


def _approved() -> list[tuple[str, str]]:
    """Each label the table changed, as what it was and what it became."""
    approved: list[tuple[str, str]] = []
    header: list[str] = []
    for line in TABLE.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] in HEADERS:
            header = cells
            continue
        row = dict(zip(header, cells, strict=False))
        became = (row.get("Proposed") or row.get("Display name") or "").strip("`")
        if became and became != UNCHANGED:
            approved.append((row.get("Today") or row.get("Code") or "", became))
    return approved


def _drawn() -> str:
    """The source every screen is drawn from, without the tests that quote it."""
    return "\n".join(
        path.read_text()
        for path in sorted(WEB.rglob("*.ts*"))
        if "__tests__" not in path.parts and ".test." not in path.name
    )


def test_the_table_has_labels_to_hold() -> None:
    assert _approved()


def test_every_approved_label_is_drawn() -> None:
    drawn = _drawn()
    missing = [
        f"{was} became {became}"
        for was, became in _approved()
        if became not in SUPERSEDED and became not in drawn
    ]
    assert missing == []


def test_a_superseded_label_still_needs_its_excuse() -> None:
    """An exception that no longer excuses anything is removed rather than kept."""
    drawn = _drawn()
    approved = {became for _, became in _approved()}
    assert approved >= SUPERSEDED
    assert [label for label in SUPERSEDED if label in drawn] == []
