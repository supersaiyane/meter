"""What a saved view may name and hold, checked without a database. FEAT-068, TASK-P8-010.

`finops_api.screens` copies the navigation's paths out of `finops-web/src/shell/sections.ts`, and
the first test fails the moment the two disagree. The database's copy, the constraint on
`saved_view`, is held by `test_saved_views.py`, which needs a database to read it. The rest
hold the bounds a view's body is refused at, each from both sides, so a bound that moved
would fail rather than pass.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from finops_api.schemas import (
    VIEW_QUERY_MAX_KEY_LENGTH,
    VIEW_QUERY_MAX_KEYS,
    VIEW_QUERY_MAX_VALUE_LENGTH,
    VIEW_QUERY_MAX_VALUES,
    SavedViewIn,
    SavedViewPatchIn,
)
from finops_api.screens import SCREEN_PATHS

SECTIONS = Path(__file__).resolve().parents[2] / "finops-web" / "src" / "shell" / "sections.ts"
TOKEN = re.compile(r"path: '([^']+)'|arrives:")
PATH = re.compile(r"path: '([^']+)'")


def between(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def navigation() -> list[str]:
    """Every screen in GROUPS and every tab in TABS, read out of sections.ts.

    A screen is the entry its `arrives` field closes, so its path is the last one before that
    field. A group's own path is always followed by its first screen's before any `arrives`, so
    a group is never taken for a screen, and the Overview, whose group and screen are both `/`,
    is counted once.
    """
    text = SECTIONS.read_text(encoding="utf-8")
    screens: list[str] = []
    latest: str | None = None
    for match in TOKEN.finditer(between(text, "export const GROUPS", "export const TABS")):
        if match.group(1) is not None:
            latest = match.group(1)
            continue
        assert latest is not None, "an arrives field with no path before it"
        screens.append(latest)
        latest = None
    tabs = PATH.findall(between(text, "export const TABS", "export const REDIRECTS"))
    return list(dict.fromkeys([*screens, *tabs]))


def test_the_list_is_the_navigations_screens_and_tabs() -> None:
    found = navigation()
    # A parse that found nothing would agree with a list that held nothing.
    assert len(found) > 20
    assert sorted(SCREEN_PATHS) == sorted(found)


def test_the_list_names_each_screen_once() -> None:
    assert len(SCREEN_PATHS) == len(set(SCREEN_PATHS))


def body(**change: object) -> dict[str, object]:
    return {"name": "Accounts", "screen_path": "/inventory/accounts", **change}


def test_a_view_is_private_and_queries_nothing_unless_told_otherwise() -> None:
    view = SavedViewIn.model_validate(body(name="  Accounts \t"))
    assert (view.name, view.query, view.visibility) == ("Accounts", {}, "PRIVATE")


@pytest.mark.parametrize(
    ("query", "kept"),
    [
        ({f"k{index}": "v" for index in range(VIEW_QUERY_MAX_KEYS)}, True),
        ({f"k{index}": "v" for index in range(VIEW_QUERY_MAX_KEYS + 1)}, False),
        ({"k" * VIEW_QUERY_MAX_KEY_LENGTH: "v"}, True),
        ({"k" * (VIEW_QUERY_MAX_KEY_LENGTH + 1): "v"}, False),
        ({"": "v"}, False),
        ({"k": ["v"] * VIEW_QUERY_MAX_VALUES}, True),
        ({"k": ["v"] * (VIEW_QUERY_MAX_VALUES + 1)}, False),
        ({"k": "v" * VIEW_QUERY_MAX_VALUE_LENGTH}, True),
        ({"k": "v" * (VIEW_QUERY_MAX_VALUE_LENGTH + 1)}, False),
        ({"k": ["v", "v" * (VIEW_QUERY_MAX_VALUE_LENGTH + 1)]}, False),
        ({"k": {"nested": "v"}}, False),
    ],
    ids=[
        "keys-at",
        "keys-over",
        "key-length-at",
        "key-length-over",
        "key-empty",
        "values-at",
        "values-over",
        "value-length-at",
        "value-length-over",
        "listed-value-over",
        "nested",
    ],
)
def test_a_query_is_kept_up_to_each_bound_and_refused_past_it(
    query: dict[str, object], kept: bool
) -> None:
    if kept:
        assert SavedViewIn.model_validate(body(query=query)).query == query
    else:
        with pytest.raises(ValidationError):
            SavedViewIn.model_validate(body(query=query))


@pytest.mark.parametrize("name", ["", "   ", "two\nlines", "tab\tinside", "x" * 121])
def test_a_name_is_one_line_that_is_not_blank(name: str) -> None:
    with pytest.raises(ValidationError):
        SavedViewIn.model_validate(body(name=name))
    with pytest.raises(ValidationError):
        SavedViewPatchIn.model_validate({"name": name})


def test_a_change_names_something_to_change() -> None:
    with pytest.raises(ValidationError):
        SavedViewPatchIn.model_validate({})
    assert SavedViewPatchIn.model_validate({"visibility": "SHARED"}).name is None
    assert SavedViewPatchIn.model_validate({"name": " Renamed "}).name == "Renamed"


@pytest.mark.parametrize("field", ["screen_path", "query", "owner_id"])
def test_a_change_cannot_reach_what_the_view_is(field: str) -> None:
    with pytest.raises(ValidationError):
        SavedViewPatchIn.model_validate({"name": "Renamed", field: "/"})
