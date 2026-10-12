"""AI spend's arithmetic: what each figure is, and how it was arrived at. TASK-P13-007.

FEAT-081 to 085, P13 spec section 5.7. Cost is the bill's. Tokens are the bill's where its line
counts them, measured, and a usage report's where it does not, modelled. Requests and a caller's
cost are modelled always. A model named one way in a log matches the way the bill names it, and a
GPU instance that published nothing is not published, never nought percent.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_query import ai

DAY = date(2026, 7, 30)
AT = datetime(2026, 7, 31, tzinfo=UTC)
REGION = "us-fake-1"


def line(**overrides: Any) -> ai.Line:
    values: dict[str, Any] = {
        "source": ai.CLOUD_BILL,
        "provider": "AWS",
        "account": "111122223333",
        "workspace": REGION,
        "day": DAY,
        "model": "ClaudeSonnet4",
        "token_type": "input",
        "tokens": Decimal("1000000"),
        "caller": "arn:aws:iam::111122223333:role/support",
        "resource_id": None,
        "tags": {},
        "cost": Decimal("3"),
        "as_of": AT,
        "collected_at": AT,
    }
    values.update(overrides)
    return ai.Line(**values)


def used(**overrides: Any) -> ai.Usage:
    values: dict[str, Any] = {
        "source": "logs",
        "account": "111122223333",
        "workspace": REGION,
        "day": DAY,
        "model": "publisher.claude-sonnet-4-20250514-v1:0",
        "caller": "arn:aws:sts::111122223333:assumed-role/support/triage",
        "application": "support",
        "tokens": {"input": 600000, "output": 0, "cache_read": 0, "cache_write": 0},
        "requests": 100,
    }
    values.update(overrides)
    return ai.Usage(**values)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("ClaudeSonnet4", "publisher.claude-sonnet-4-20250514-v1:0"),
        ("ClaudeSonnet4", "eu.publisher.claude-sonnet-4-20250514-v1:0"),
        ("NovaPro", "arn:aws:bedrock:eu-west-1::foundation-model/maker.nova-pro-v1:0"),
        ("Claude3.7Sonnet", "publisher.claude-3-7-sonnet-20250219-v1:0"),
        ("gpt-4o-2024-08-06", "gpt-4o-2024-08-06"),
    ],
)
def test_a_model_named_two_ways_is_one_model(one: str, other: str) -> None:
    assert ai.model_key(one) == ai.model_key(other) != ""


def test_different_models_stay_different() -> None:
    assert ai.model_key("ClaudeSonnet4") != ai.model_key("ClaudeHaiku4")
    assert ai.model_key(None) == ""


# --- spend -----------------------------------------------------------------------------------


def test_the_bills_own_tokens_give_a_measured_cost_per_token() -> None:
    (row,) = ai.spend([line()], [], "model")
    assert (row.name, row.cost, row.tokens, row.tokens_basis) == (
        "ClaudeSonnet4",
        Decimal("3"),
        Decimal("1000000"),
        ai.MEASURED,
    )
    assert (row.cost_per_1k_tokens, row.cost_per_1k_tokens_basis) == (
        Decimal("0.003000"),
        ai.MEASURED,
    )
    assert (row.requests, row.cost_per_request, row.cost_per_request_basis) == (None, None, None)


def test_requests_from_the_logs_give_a_modelled_cost_per_request() -> None:
    (row,) = ai.spend([line()], [used(), used(caller="someone", requests=50)], "model")
    assert (row.requests, row.cost_per_request, row.cost_per_request_basis) == (
        150,
        Decimal("0.020000"),
        ai.MODELLED,
    )
    # The bill's own tokens stay the measured figure; the log's count does not replace it.
    assert (row.tokens, row.tokens_basis) == (Decimal("1000000"), ai.MEASURED)


def test_a_providers_tokens_come_from_its_usage_report_and_are_modelled() -> None:
    provider = line(
        source="provider-x",
        provider="Provider X",
        account="org-1",
        workspace="proj-a",
        model="model-m",
        tokens=None,
        caller=None,
        cost=Decimal("2"),
    )
    usage = used(
        source="provider-x",
        account="org-1",
        workspace="proj-a",
        model="model-m",
        tokens={"input": 4000, "output": 0, "cache_read": 0, "cache_write": 0},
        requests=8,
    )
    (row,) = ai.spend([provider], [usage], "provider", self_billed={"provider-x"})
    assert (row.tokens, row.tokens_basis, row.cost_per_1k_tokens) == (
        Decimal("4000"),
        ai.MODELLED,
        Decimal("0.500000"),
    )
    assert (row.requests, row.cost_per_request) == (8, Decimal("0.250000"))


def test_a_count_shared_by_two_lines_is_split_by_cost_and_never_doubled() -> None:
    shared = {"source": "p", "account": "o", "workspace": "w", "model": "m", "tokens": None}
    first = line(**shared, cost=Decimal("3"))
    second = line(**shared, cost=Decimal("1"), caller="another")
    usage = used(source="p", account="o", workspace="w", model="m", requests=40)
    rows = ai.spend([first, second], [usage], "caller", self_billed={"p"})
    assert sorted(row.requests or 0 for row in rows) == [10, 30]


def test_a_line_nothing_counted_has_no_tokens_rather_than_none() -> None:
    (row,) = ai.spend([line(tokens=None, token_type=None, model=None)], [], "model")
    assert (row.name, row.tokens, row.tokens_basis, row.cost_per_1k_tokens) == (
        ai.UNNAMED,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("overrides", "feature"),
    [
        ({"tags": {"feature": "search"}}, "search"),
        ({"resource_id": f"arn:x:{ai.PROFILE}support-bot"}, "support-bot"),
        ({"source": "p", "workspace": "proj-a"}, "proj-a"),
        ({"source": "p", "workspace": None}, ai.DEFAULT_WORKSPACE),
        ({}, ai.UNNAMED),
    ],
)
def test_a_feature_is_a_tag_a_profile_a_project_or_not_named(
    overrides: dict[str, Any], feature: str
) -> None:
    (row,) = ai.spend([line(**overrides)], [], "feature", tag_key="feature")
    assert row.name == feature


def test_groups_are_worst_first_and_a_mixed_group_says_so() -> None:
    rows = ai.spend(
        [
            line(cost=Decimal("1"), model="a"),
            line(cost=Decimal("5"), model="b"),
            line(cost=Decimal("2"), model="b", provider="Other", source="x"),
        ],
        [],
        "model",
    )
    assert [(row.name, row.cost, row.provider) for row in rows] == [
        ("b", Decimal("7"), ai.SEVERAL),
        ("a", Decimal("1"), "AWS"),
    ]


def test_an_unknown_grouping_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot group"):
        ai.spend([line()], [], "region")


# --- callers ---------------------------------------------------------------------------------


def test_a_callers_cost_is_its_tokens_at_the_bills_unit_cost() -> None:
    rows = ai.callers([line()], [used(), used(caller="b", application="")])
    by_caller = {row.caller: row for row in rows}
    triage = by_caller["arn:aws:sts::111122223333:assumed-role/support/triage"]
    # Three dollars for a million input tokens on the bill; 600,000 of them used.
    assert (triage.tokens, triage.requests, triage.modelled_cost) == (
        600000,
        100,
        Decimal("1.800000"),
    )


def test_a_caller_the_bill_priced_nothing_for_has_no_cost_and_comes_last() -> None:
    priced = used()
    unpriced = used(caller="z", model="another-model")
    rows = ai.callers([line()], [unpriced, priced])
    assert rows[-1].caller == "z" and rows[-1].modelled_cost is None


def test_a_self_billed_providers_unit_cost_spreads_its_bill_over_its_usage() -> None:
    shared = {"source": "p", "account": "o", "workspace": "w", "model": "m"}
    bill = line(**shared, tokens=None, cost=Decimal("10"))
    one = used(**shared, caller="u1", tokens={"input": 3000})
    two = used(**shared, caller="u2", tokens={"input": 1000}, requests=None)
    rows = ai.callers([bill], [one, two], self_billed={"p"})
    costs = {row.caller: row.modelled_cost for row in rows}
    assert costs == {"u1": Decimal("7.500000"), "u2": Decimal("2.500000")}
    assert {row.caller: row.requests for row in rows}["u2"] is None


def test_a_usage_source_that_does_not_bill_itself_is_priced_from_the_cloud_bill() -> None:
    assert ai.bill_source("logs", {"p"}) == ai.CLOUD_BILL
    assert ai.bill_source("p", {"p"}) == "p"


# --- GPU -------------------------------------------------------------------------------------


def gpu_line(instance: str, day: int, usage_type: str = "USF1-BoxUsage:g5.xlarge") -> ai.GpuLine:
    return ai.GpuLine(
        account="a",
        region=REGION,
        instance_id=instance,
        usage_type=usage_type,
        day=date(2026, 7, day),
        hours=Decimal("24"),
        cost=Decimal("24"),
    )


def published(instance: str, day: date, average: str, peak: str) -> ai.GpuDay:
    return ai.GpuDay(
        account="a",
        instance_id=instance,
        day=day,
        average_percent=Decimal(average),
        peak_percent=Decimal(peak),
    )


def test_an_instance_is_published_partly_published_or_not() -> None:
    rows = ai.gpu(
        [
            gpu_line("i-busy", 1),
            gpu_line("i-busy", 2),
            gpu_line("i-quiet", 1, "USF1-BoxUsage:p4d.24xlarge"),
            gpu_line("i-cpu", 1, "USF1-BoxUsage:m5.large"),
        ],
        [
            published("i-busy", date(2026, 7, 1), "20", "90"),
            published("i-busy", date(2026, 7, 2), "30", "70"),
            # A day the bill does not name is not counted.
            published("i-quiet", date(2026, 6, 30), "5", "5"),
        ],
    )
    by_id = {row.instance_id: row for row in rows}
    assert set(by_id) == {"i-busy", "i-quiet"}, "a CPU instance is not a GPU instance"
    busy = by_id["i-busy"]
    assert (busy.instance_type, busy.hours, busy.cost, busy.days_billed, busy.days_published) == (
        "g5.xlarge",
        Decimal("48"),
        Decimal("48"),
        2,
        2,
    )
    assert (busy.average_percent, busy.peak_percent) == (Decimal("25.00"), Decimal("90"))
    quiet = by_id["i-quiet"]
    assert (quiet.days_published, quiet.average_percent, quiet.peak_percent) == (0, None, None)
