"""The two export files, read back. FEAT-067, TASK-P8-009, P8 spec section 5.5 items 2 to 4.

The writers on their own, against a row model built here, so every type a route can hand them
is met once: money, counts, booleans, dates, times with an offset, an optional nested model, a
list that is not a cell, and text that opens with a character a spreadsheet would run.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel, computed_field

from finops_api.exports.cells import columns_of, flatten, header
from finops_api.exports.writers import (
    ABOUT_SHEET,
    DATA_SHEET,
    HOSTILE,
    Sheet,
    csv_file,
    neutralised,
    xlsx,
)
from tests.api.workbook import cells, column, sheet_names

#: 14:30 in India is 09:00 UTC, so a time that kept its zone would show as the wrong hour.
AT = datetime(2026, 10, 5, 14, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
EXCEL_EPOCH = datetime(1899, 12, 30)


class Span(BaseModel):
    low: Decimal
    high: Decimal


class Line(BaseModel):
    name: str
    effective_cost: Decimal
    line_items: int
    shared: bool
    day: date
    as_of: datetime
    figure: Span | None = None
    history: list[Decimal] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def doubled(self) -> Decimal:
        return self.effective_cost * 2


def line(name: str = "Amazon EC2", cost: str = "12.50", **changes: object) -> Line:
    values: dict[str, object] = {
        "name": name,
        "effective_cost": Decimal(cost),
        "line_items": 3,
        "shared": True,
        "day": date(2026, 10, 4),
        "as_of": AT,
    }
    return Line.model_validate({**values, **changes})


def sheet_of(*rows: Line) -> Sheet:
    columns = tuple(columns_of(Line))
    return Sheet(columns=columns, headers=tuple(header(path) for path in columns), rows=rows)


def workbook(*rows: Line, limit: int = 100) -> bytes:
    return xlsx(sheet_of(*rows), (("View", "Lines"),), (), limit).body


def csv_rows(*rows: Line) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_file(sheet_of(*rows)).body.decode("utf-8-sig"))))


def serial(moment: datetime) -> float:
    """A naive time as the day number a workbook stores."""
    return (moment - EXCEL_EPOCH).total_seconds() / 86400


class TestColumns:
    def test_a_nested_model_is_columns_of_its_own_and_a_list_is_none(self) -> None:
        assert columns_of(Line) == [
            "name",
            "effective_cost",
            "line_items",
            "shared",
            "day",
            "as_of",
            "figure.low",
            "figure.high",
            "doubled",
        ]

    def test_a_row_flattens_to_the_same_paths(self) -> None:
        flat = flatten(line(figure=Span(low=Decimal(1), high=Decimal(2))))
        assert flat["figure.low"] == Decimal(1)
        assert flat["doubled"] == Decimal("25.00")
        assert "history" not in flat

    def test_a_heading_is_the_route_s_name_then_the_focus_name_then_its_words(self) -> None:
        assert header("effective_cost") == "Effective Cost"
        assert header("account_id") == "Sub Account ID"
        assert header("figure.low") == "Figure low"
        assert header("name", {"name": "Service Name"}) == "Service Name"


class TestTheWorkbook:
    def test_it_has_a_data_sheet_and_an_about_sheet(self) -> None:
        assert sheet_names(workbook(line())) == [DATA_SHEET, ABOUT_SHEET]

    def test_the_headings_are_focus_names(self) -> None:
        assert column(cells(workbook(line()), 1), "B")[0] == "Effective Cost"

    def test_money_is_a_number_a_spreadsheet_can_sum(self) -> None:
        data = cells(workbook(line(cost="12.50")), 1)
        assert data["B2"].kind is None
        assert float(data["B2"].text) == pytest.approx(12.5)
        assert float(data["C2"].text) == 3

    def test_a_boolean_is_a_boolean(self) -> None:
        data = cells(workbook(line()), 1)
        assert (data["D2"].kind, data["D2"].text) == ("b", "1")

    def test_a_time_is_written_in_utc_and_a_day_as_a_day(self) -> None:
        data = cells(workbook(line()), 1)
        assert float(data["F2"].text) == pytest.approx(serial(datetime(2026, 10, 5, 9, 0)))
        assert float(data["E2"].text) == pytest.approx(serial(datetime(2026, 10, 4)))

    def test_an_empty_nested_model_leaves_its_cells_empty(self) -> None:
        data = cells(workbook(line()), 1)
        assert "G2" not in data
        assert "H2" not in data

    @pytest.mark.parametrize("lead", HOSTILE)
    def test_a_hostile_cell_is_text_and_never_a_formula(self, lead: str) -> None:
        data = cells(workbook(line(name=f"{lead}cmd|' /C calc'!A0")), 1)
        assert data["A2"].kind == "inlineStr"
        assert not data["A2"].is_formula
        assert data["A2"].text.endswith("cmd|' /C calc'!A0")

    def test_the_workbook_stops_at_the_row_limit_and_says_it_did(self) -> None:
        written = xlsx(sheet_of(*(line(name=f"s{n}") for n in range(5))), (), (), 3)
        data = cells(written.body, 1)
        assert (written.rows, written.truncated) == (3, True)
        assert column(data, "A") == ["Name", "s0", "s1", "s2"]

    def test_a_workbook_within_the_limit_is_whole(self) -> None:
        written = xlsx(sheet_of(line(), line()), (), (), 2)
        assert (written.rows, written.truncated) == (2, False)

    def test_the_about_sheet_holds_its_fields_then_every_failure(self) -> None:
        about = (("View", "Cost by service"), ("Scope", "Every account in the organisation"))
        failures = (("cost_cur", "AccessDenied", "aws:fake-platform-b", "Grant the role."),)
        notes = cells(xlsx(sheet_of(line()), about, failures, 10).body, 2)
        assert column(notes, "A")[:3] == ["Field", "View", "Scope"]
        assert column(notes, "B")[1] == "Cost by service"
        assert column(notes, "A")[3:] == ["Failing collector", "cost_cur"]
        assert column(notes, "B")[3:] == ["Cause", "AccessDenied"]


class TestTheCsv:
    def test_every_row_is_written_whatever_the_workbook_limit(self) -> None:
        written = csv_file(sheet_of(*(line(name=f"s{n}") for n in range(5))))
        assert (written.rows, written.truncated) == (5, False)

    def test_it_opens_as_utf8_without_the_reader_choosing_an_encoding(self) -> None:
        assert csv_file(sheet_of(line())).body.startswith(b"\xef\xbb\xbf")

    @pytest.mark.parametrize("lead", HOSTILE)
    def test_a_hostile_cell_is_led_by_an_apostrophe(self, lead: str) -> None:
        value = f"{lead}cmd|' /C calc'!A0"
        assert csv_rows(line(name=value))[1][0] == f"'{value}"

    def test_a_negative_number_stays_a_number(self) -> None:
        assert csv_rows(line(cost="-3.20"))[1][1] == "-3.20"

    def test_a_time_keeps_its_offset_and_is_given_in_utc(self) -> None:
        assert csv_rows(line())[1][5] == "2026-10-05T09:00:00+00:00"

    def test_an_empty_cell_is_empty_rather_than_none(self) -> None:
        assert csv_rows(line())[1][6] == ""

    def test_ordinary_text_is_left_alone(self) -> None:
        assert neutralised("Amazon EC2") == "Amazon EC2"
        assert neutralised("-x") == "'-x"
