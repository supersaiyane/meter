"""The export names collectors the way the screens do. FEAT-067, ISS-246.

The web holds the names in `finops-web/src/components/displayNames.ts`, and the About sheet needs
the same ones on the server. The two copies are held equal here rather than trusted to stay so,
the way the MCP drift gate holds the facade to the API.
"""

from __future__ import annotations

import re
from pathlib import Path

from finops_api.exports.cells import COLLECTOR_NAMES, collector_name, in_words

DISPLAY_NAMES = (
    Path(__file__).resolve().parents[2] / "finops-web" / "src" / "components" / "displayNames.ts"
)


def web_names() -> dict[str, str]:
    source = DISPLAY_NAMES.read_text(encoding="utf-8")
    body = re.search(r"export const COLLECTOR_NAMES: Names = \{(.*?)\n\};", source, re.S)
    assert body is not None, "COLLECTOR_NAMES moved, so this test would compare nothing"
    return dict(re.findall(r"^\s*(\w+): '([^']*)',$", body.group(1), re.M))


def test_the_server_names_every_collector_the_web_names_and_the_same_way() -> None:
    names = web_names()
    assert len(names) > 20
    assert dict(COLLECTOR_NAMES) == names


def test_a_named_collector_is_given_its_name() -> None:
    assert collector_name("account_health") == "Account health"
    assert collector_name("finops_score") == "FinOps Score"


def test_a_collector_nobody_named_is_put_in_words_as_the_web_does() -> None:
    assert collector_name("new_collector") == "New collector"
    assert in_words("NotOptedIn") == "Not opted in"
    assert in_words("cost-focus_daily") == "Cost focus daily"
