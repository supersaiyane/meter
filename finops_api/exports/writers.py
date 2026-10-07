"""The two files an export is written as. FEAT-067, TASK-P8-009, P8 spec section 5.5.

**A hostile cell stays text.** Tag values come from member accounts, and a value that starts with
`=` is a formula to a spreadsheet. XlsxWriter's string to formula, string to number and string to
URL conversions are off and every text cell goes through `write_string`. A CSV has no types at
all, so there a text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is led
by an apostrophe, which a spreadsheet reads as "this is text" and does not display.

**A number stays a number.** Money is written as a number, so a column of Effective Cost sums in
the spreadsheet, and its currency is stated once on the About sheet rather than glued into
every cell as text.

**Times are UTC.** A workbook cell has no time zone, so every time is converted to UTC before it
is written and the About sheet says so. A CSV keeps the offset in the text.

**Memory stays flat.** The workbook is written in XlsxWriter's constant memory mode, a row at a
time through a temporary file, so a 100,000 row export costs a row's memory rather than the
sheet's. Rows are flattened as they are written for the same reason.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Final

import xlsxwriter
from pydantic import BaseModel

from finops_api.exports.cells import flatten, text_of

#: The leading characters a spreadsheet would read as the start of a formula or a command.
HOSTILE: Final = ("=", "+", "-", "@", "\t", "\r")

#: Both within Excel's 31 character limit on a sheet name.
DATA_SHEET: Final = "Data"
ABOUT_SHEET: Final = "About this export"

FAILURE_HEADINGS: Final = ("Failing collector", "Cause", "Where", "What to do")


@dataclass(frozen=True)
class Sheet:
    """The view's rows, the dotted paths that pick their cells, and what each column is called."""

    columns: tuple[str, ...]
    headers: tuple[str, ...]
    rows: Sequence[BaseModel]


@dataclass(frozen=True)
class Written:
    """A file and what went into it."""

    body: bytes
    rows: int
    truncated: bool


def xlsx(
    sheet: Sheet,
    about: Sequence[tuple[str, str]],
    failures: Sequence[tuple[str, str, str, str]],
    limit: int,
) -> Written:
    """A workbook: the Data sheet, stopped at `limit` rows, and the About this export sheet."""
    buffer = io.BytesIO()
    book: Any = xlsxwriter.Workbook(
        buffer,
        {
            "constant_memory": True,
            "strings_to_formulas": False,
            "strings_to_numbers": False,
            "strings_to_urls": False,
            "nan_inf_to_errors": True,
        },
    )
    bold = book.add_format({"bold": True})
    day = book.add_format({"num_format": "yyyy-mm-dd"})
    moment = book.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    data = book.add_worksheet(DATA_SHEET)
    if sheet.headers:
        data.set_column(0, len(sheet.headers) - 1, 18)
    data.freeze_panes(1, 0)
    for column, title in enumerate(sheet.headers):
        data.write_string(0, column, title, bold)
    kept = sheet.rows[:limit]
    for number, row in enumerate(kept, start=1):
        cells = flatten(row)
        for column, path in enumerate(sheet.columns):
            _write(data, number, column, cells.get(path), day, moment)
    _about(book.add_worksheet(ABOUT_SHEET), about, failures, bold)
    book.close()
    return Written(body=buffer.getvalue(), rows=len(kept), truncated=len(sheet.rows) > limit)


def csv_file(sheet: Sheet) -> Written:
    """Every row, as UTF-8 with a byte order mark so a spreadsheet does not guess the encoding."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(sheet.headers)
    for row in sheet.rows:
        cells = flatten(row)
        writer.writerow([_csv_cell(cells.get(path)) for path in sheet.columns])
    return Written(
        body=buffer.getvalue().encode("utf-8-sig"), rows=len(sheet.rows), truncated=False
    )


def neutralised(text: str) -> str:
    """Text a spreadsheet will read as text, whatever character it starts with."""
    return f"'{text}" if text.startswith(HOSTILE) else text


def utc_naive(moment: datetime) -> datetime:
    """A time in UTC with its zone removed, the only kind a workbook cell holds."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def _write(sheet: Any, row: int, column: int, value: object, day: Any, moment: Any) -> None:
    # A bool is an int and a datetime is a date, so each is matched before the wider type.
    match value:
        case None:
            return
        case bool():
            sheet.write_boolean(row, column, value)
        case Decimal() | int() | float():
            sheet.write_number(row, column, float(value))
        case datetime():
            sheet.write_datetime(row, column, utc_naive(value), moment)
        case date():
            sheet.write_datetime(row, column, datetime.combine(value, time()), day)
        case _:
            sheet.write_string(row, column, text_of(value))


def _csv_cell(value: object) -> str:
    match value:
        case None:
            return ""
        case bool():
            return "TRUE" if value else "FALSE"
        case Decimal():
            return format(value, "f")
        case int() | float():
            return str(value)
        case datetime():
            return value.astimezone(UTC).isoformat() if value.tzinfo else value.isoformat()
        case date():
            return value.isoformat()
        case _:
            return neutralised(text_of(value))


def _about(
    notes: Any,
    about: Sequence[tuple[str, str]],
    failures: Sequence[tuple[str, str, str, str]],
    bold: Any,
) -> None:
    """What the file is, then every typed failure in the view, a row each."""
    notes.set_column(0, 0, 24)
    notes.set_column(1, 1, 60)
    notes.set_column(2, 3, 40)
    notes.write_string(0, 0, "Field", bold)
    notes.write_string(0, 1, "Value", bold)
    for number, (field, value) in enumerate(about, start=1):
        notes.write_string(number, 0, field)
        notes.write_string(number, 1, value)
    if not failures:
        return
    start = len(about) + 2
    for column, title in enumerate(FAILURE_HEADINGS):
        notes.write_string(start, column, title, bold)
    for number, failure in enumerate(failures, start=start + 1):
        for column, value in enumerate(failure):
            notes.write_string(number, column, value)
