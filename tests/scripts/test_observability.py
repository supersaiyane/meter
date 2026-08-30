"""The alarms, the dashboards and the runbooks, held against each other.

None of these three are executed by anything in this repository, so nothing else
would notice them drifting apart. The failure they drift into is specific: a
paging alert whose runbook was renamed, which is discovered at three in the
morning by the person the page woke up.

The dashboard rules are here for a second reason. FEAT-014 is a control this
product sells to its users, and Meter's own dashboards are subject to it. A team
that exempts itself from the control it sells has already lost the argument, so
the rule is enforced on our own JSON by a test rather than by intention.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "infra" / "terraform" / "hub"
DASHBOARDS = HUB / "dashboards"
RUNBOOKS = ROOT / "docs" / "runbooks"

#: FEAT-014, applied to us. Both numbers come from docs/10-OBSERVABILITY.md.
MINIMUM_REFRESH = "1m"
MAXIMUM_WINDOW_HOURS = 24


def observability() -> str:
    return (HUB / "observability.tf").read_text(encoding="utf-8")


def alarm_names() -> list[str]:
    return re.findall(r'resource "aws_cloudwatch_metric_alarm" "(\w+)"', observability())


def test_there_are_ten_alarms() -> None:
    """Ten, per the alert table. Counted so that deleting one is a decision."""
    assert len(alarm_names()) == 10


def declared_runbooks() -> dict[str, str]:
    """The `runbooks` map in the locals block, which is where the paths live."""
    return dict(re.findall(r"(\w+)\s+=\s+\"(docs/runbooks/[\w.-]+)\"", observability()))


def test_every_declared_runbook_exists() -> None:
    """An alert shipped without a runbook is a page that wakes someone who then
    has to work out what to do."""
    declared = declared_runbooks()

    assert len(declared) >= 3, "expected the paging alarms to cite their runbooks"
    for key, path in sorted(declared.items()):
        assert (ROOT / path).is_file(), f"{key} cites {path}, which does not exist"


def test_every_paging_alarm_cites_one() -> None:
    """The citation is in the alarm description, so it reaches the person the
    page woke up rather than only the person reading the Terraform."""
    for name in sorted(n for n in alarm_names() if _is_paging(n)):
        assert "local.runbooks." in _block_for(name), f"{name} pages and names no runbook"


def test_the_paging_alarms_are_the_four_the_specification_names() -> None:
    """Four page. The runbook index and the plan both said two for a while,
    which was a misreading of 'two of these are unusual'. ISS-121."""
    paging = {name for name in alarm_names() if _is_paging(name)}

    assert paging == {
        "collection_stalled",
        "collection_stalled_widespread",
        "api_5xx",
        "platform_cost_anomaly",
    }


def _is_paging(name: str) -> bool:
    block = _block_for(name)
    return re.search(r"alarm_actions\s+=\s+local\.page", block) is not None


def _block_for(name: str) -> str:
    text = observability()
    start = text.index(f'resource "aws_cloudwatch_metric_alarm" "{name}"')
    following = text.find('\nresource "', start + 1)
    return text[start:] if following == -1 else text[start:following]


def test_the_collection_alarms_treat_a_missing_datapoint_as_breaching() -> None:
    """A stalled metric publisher is the same class of failure as a stalled
    collector. Treating its absence as healthy would make this alarm survive
    only while the thing it watches is working."""
    for name in ("collection_stalled", "collection_stalled_widespread"):
        setting = re.search(r"treat_missing_data\s+=\s+\"(\w+)\"", _block_for(name))
        assert setting is not None and setting.group(1) == "breaching", name


@pytest.mark.parametrize("path", sorted(DASHBOARDS.glob("*.json")), ids=lambda p: p.stem)
def test_a_dashboard_obeys_the_control_we_sell(path: Path) -> None:
    dashboard = json.loads(path.read_text(encoding="utf-8"))

    assert dashboard["refresh"] == MINIMUM_REFRESH, "FEAT-014: minimum refresh interval"
    assert dashboard["panels"], "a dashboard with no panels is not a dashboard"

    for option in dashboard["timepicker"]["time_options"]:
        hours = _hours(option)
        assert hours <= MAXIMUM_WINDOW_HOURS, f"{option} exceeds the FEAT-014 window"


def _hours(option: str) -> int:
    value, unit = int(option[:-1]), option[-1]
    return {"h": value, "d": value * 24}[unit]


def test_there_are_three_dashboards() -> None:
    assert {p.stem for p in DASHBOARDS.glob("*.json")} == {
        "collection-health",
        "service-health",
        "platform-cost",
    }


def test_the_runbook_index_lists_every_runbook() -> None:
    """An index that has fallen behind is worse than none, because it is read."""
    index = (RUNBOOKS / "README.md").read_text(encoding="utf-8")
    files = {p.name for p in RUNBOOKS.glob("*.md")} - {"README.md"}

    for name in sorted(files):
        assert name in index, f"{name} exists and the index does not mention it"
