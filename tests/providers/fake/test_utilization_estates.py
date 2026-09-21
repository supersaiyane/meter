"""The fake utilization, container, topology and quota estates.

These tests hold the estates to the properties the P3 to P6 plans ask of their
fakes: deterministic, incomplete by default, refusing where a real estate
refuses, and containing both the waste and the decoys a detector must tell
apart. Most read a short window, because a property that holds for any hour
does not need two years to prove it. The ones that need the whole window say so.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from finops_core.errors import AccessDenied, NotOptedIn
from finops_providers.fake import containers, cur, fixtures, planted, quotas, topology, utilization
from finops_providers.fake import estate_shape as shape

START, END = shape.window(fixtures.AS_OF)
LAST_WEEK = END - timedelta(days=7)
MODULES = ("estate_shape", "utilization", "containers", "topology", "quotas", "planted")
FAKE_DIR = Path(utilization.__file__).parent


def _points(
    resource_id: str, metric: str, statistic: str, start: datetime = LAST_WEEK
) -> list[float]:
    s = utilization.spec(resource_id)
    return [
        float(p.point.value)
        for p in utilization.series_for(s.account_id, s.region_id, start=start, end=END)
        if p.resource_id == resource_id
        and p.point.metric_name == metric
        and p.point.statistic == statistic
    ]


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(0.95 * len(ordered)) - 1)]


# ------------------------------------------------------------- determinism


def test_the_window_is_two_years_ending_at_the_clock() -> None:
    assert fixtures.AS_OF.replace(minute=0) == END
    assert (END - START).days == shape.WINDOW_DAYS


def test_the_same_clock_produces_the_same_series() -> None:
    first = [
        (p.resource_id, p.point.metric_name, p.point.value)
        for p in utilization.series(start=LAST_WEEK)
    ]
    second = [
        (p.resource_id, p.point.metric_name, p.point.value)
        for p in utilization.series(start=LAST_WEEK)
    ]
    assert first == second


@pytest.mark.parametrize("module", MODULES)
def test_no_clock_and_no_random_source(module: str) -> None:
    tree = ast.parse((FAKE_DIR / f"{module}.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    called = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "random" not in imported and "secrets" not in imported
    assert not {"now", "utcnow", "today"} & called


@pytest.mark.parametrize("module", MODULES)
def test_no_twelve_digit_literal_and_no_real_region(module: str) -> None:
    text = (FAKE_DIR / f"{module}.py").read_text(encoding="utf-8")
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", text)
    assert not re.search(r"\b(us|eu|ap|sa|ca|me|af)-(east|west|north|south|central)-\d\b", text)


# ---------------------------------------------------------------- refusals


def test_the_denied_account_raises_before_yielding_anything() -> None:
    with pytest.raises(AccessDenied):
        next(utilization.series_for(shape.DENIED_ACCOUNT, shape.REGION_A))
    with pytest.raises(AccessDenied):
        quotas.current(shape.DENIED_ACCOUNT, shape.REGION_A)


def test_the_refusing_region_raises_rather_than_returning_nothing() -> None:
    with pytest.raises(NotOptedIn):
        next(utilization.series_for("fake-platform-a", shape.REFUSING_REGION))
    with pytest.raises(NotOptedIn):
        quotas.current("fake-platform-a", shape.REFUSING_REGION)


def test_no_resource_lives_in_the_denied_account_or_the_refusing_region() -> None:
    for s in utilization.SPECS:
        assert s.account_id != shape.DENIED_ACCOUNT
        assert s.region_id != shape.REFUSING_REGION


# ------------------------------------------------------------- P3 decoys


def test_the_under_floor_instance_has_less_than_fourteen_days() -> None:
    s = utilization.spec("amazonec2/fake-product-b/0003")
    first = min(
        p.point.at
        for p in utilization.series_for(s.account_id, s.region_id, start=END - timedelta(days=30))
        if p.resource_id == s.resource_id
    )
    assert (END - first).days < shape.MINIMUM_HISTORY_DAYS


def test_the_burstable_instance_never_runs_short_of_credits() -> None:
    assert min(_points("amazonec2/fake-product-a/0002", "CPUCreditBalance", "Average")) > 400
    assert 15 < _p95(_points("amazonec2/fake-product-a/0002", "CPUUtilization", "Average")) < 25


def test_the_dev_box_is_busy_by_day_and_idle_at_night() -> None:
    values = _points("amazonec2/fake-product-b/0001", "CPUUtilization", "Average")
    assert min(values) < 3 and _p95(values) > 45


def test_the_memory_bound_instance_looks_idle_on_cpu_alone() -> None:
    assert _p95(_points("amazonec2/fake-product-a/0004", "CPUUtilization", "Average")) < 15
    assert min(_points("amazonec2/fake-product-a/0004", "mem_used_percent", "Average")) > 85


def test_an_instance_without_the_agent_publishes_no_memory_series_at_all() -> None:
    assert _points("amazonec2/fake-product-b/0004", "mem_used_percent", "Average") == []
    assert _points("amazonec2/fake-product-b/0004", "CPUUtilization", "Average")


def test_an_unattached_volume_publishes_nothing_and_is_found_by_configuration() -> None:
    s = utilization.spec("amazonebs/fake-platform-b/0001")
    assert not [
        p
        for p in utilization.series_for(s.account_id, s.region_id, start=LAST_WEEK)
        if p.resource_id == s.resource_id
    ]
    assert utilization.configuration(s.resource_id)["attached_to"] is None


def test_the_product_api_scales_out_on_the_day_the_bill_spikes() -> None:
    day = cur.spike_day()
    counts = {
        p.point.at.date(): float(p.point.value)
        for p in utilization.series_for(
            "fake-product-a", shape.REGION_A, start=END - timedelta(days=3)
        )
        if p.resource_id == "amazonec2/fake-product-a/0001"
        and p.point.metric_name == "GroupInServiceInstances"
    }
    assert counts[day] >= 4 * counts[day - timedelta(days=1)]


# -------------------------------------------------------------------- P6


def _number(row: Mapping[str, object], key: str) -> float:
    """One numeric cell of an exported row.

    The row mappings are deliberately `Mapping[str, object]`, because a CSV row
    holds strings, numbers and nulls side by side. A test comparing two of them has
    to say which it is reading, and saying it once here beats a cast at each site.
    """
    value = row[key]
    # Decimal included, and it is the common case: the exported cells carry Decimal
    # so a byte count survives the round trip without a float rounding it. bool is
    # excluded because it is an int in Python and is never a measurement here.
    assert isinstance(value, int | float | Decimal) and not isinstance(value, bool), (key, value)
    return float(value)


def _usage(workload: str) -> list[Mapping[str, object]]:
    return [
        r
        for r in containers.usage_rows()
        if r["workload"] == workload and str(r["usage_date"]) >= "2026-07-25"
    ]


def test_ledger_requests_about_five_times_what_it_uses() -> None:
    rows = _usage("ledger-api")
    use = sum(_number(r, "cpu_used_avg_millicores") for r in rows) / len(rows)
    assert _number(rows[0], "cpu_request_millicores") / use > 4


def test_channels_is_sized_correctly() -> None:
    rows = _usage("web-bff")
    use = sum(_number(r, "cpu_used_avg_millicores") for r in rows) / len(rows)
    assert _number(rows[0], "cpu_request_millicores") / use < 2.5


def test_a_cluster_without_enhanced_observability_reports_use_and_no_request() -> None:
    rows = _usage("risk-batch")
    assert all(
        r["cpu_request_millicores"] is None and r["memory_request_mib"] is None for r in rows
    )
    assert all(_number(r, "cpu_used_avg_millicores") > 0 for r in rows)


def test_a_zero_request_never_sits_beside_a_positive_use() -> None:
    for r in _usage("payments-api") + _usage("risk-batch") + _usage("statements-renderer"):
        assert r["cpu_request_millicores"] != 0


def test_all_three_oom_states_occur_over_the_whole_window() -> None:
    states = {r["was_oom_killed"] for r in containers.usage_rows()}
    assert states == {True, False, None}


def test_node_counts_follow_the_pods_at_quarter_end() -> None:
    quiet = next(
        h
        for h in shape.hours(START, END)
        if not shape.is_quarter_end(h.date()) and not shape.is_month_end(h.date())
    )
    busy = next(h for h in shape.hours(START, END) if shape.is_quarter_end(h.date()))
    assert containers.nodes(containers.BATCH_EKS, busy) > 2 * containers.nodes(
        containers.BATCH_EKS, quiet
    )


# -------------------------------------------------------------------- P4


def test_every_edge_joins_two_known_nodes() -> None:
    ids = {n.node_id for n in topology.nodes()}
    assert len(ids) == len(topology.nodes())
    for e in topology.edges():
        assert e.from_node_id in ids and e.to_node_id in ids


def test_a_security_group_references_itself() -> None:
    assert any(e.from_node_id == e.to_node_id for e in topology.edges())


def test_edges_are_directed_and_distinct() -> None:
    keys = [(e.from_node_id, e.to_node_id, e.edge_kind) for e in topology.edges()]
    assert len(keys) == len(set(keys))


def test_cross_account_edges_exist_and_name_their_source() -> None:
    cross = [r for r in topology.edge_rows() if r["is_cross_account"]]
    assert {r["source"] for r in cross} >= {
        topology.TGW_API,
        topology.ENDPOINT_API,
        topology.TRUST_API,
    }


def test_every_slice_has_exactly_one_coverage_row_and_a_cause_when_not_complete() -> None:
    rows = list(topology.coverage_rows())
    assert len(rows) == len(fixtures.ACCOUNT_IDS) * len(shape.REGIONS)
    assert {r["state"] for r in rows} == {"COMPLETE", "PARTIAL", "UNREAD"}
    for r in rows:
        assert (r["state"] == "COMPLETE") == (r["cause"] is None)


# -------------------------------------------------------------------- P5


def test_current_usage_never_exceeds_its_limit_and_source_matches_value() -> None:
    for r in quotas.usage_rows():
        assert (r["usage_source"] == quotas.NONE) == (r["used_value"] is None)
        if r["used_value"] is not None:
            assert _number(r, "used_value") <= _number(r, "limit_value")


def test_unmeasurable_quotas_are_a_real_share_not_a_token() -> None:
    rows = list(quotas.usage_rows())
    assert sum(r["used_value"] is None for r in rows) / len(rows) > 0.35


def test_trusted_advisor_quota_is_unmeasurable_without_business_support() -> None:
    rows = {(r["sub_account_id"], r["quota_code"]): r for r in quotas.usage_rows()}
    assert rows[("fake-platform-a", "L-53DA6B97")]["usage_source"] == quotas.TRUSTED_ADVISOR
    assert rows[("fake-product-a", "L-53DA6B97")]["usage_source"] == quotas.NONE


def test_a_quota_that_lost_its_source_is_null_rather_than_stale() -> None:
    row = next(
        r
        for r in quotas.usage_rows()
        if r["sub_account_id"] == "fake-product-b" and r["quota_code"] == "L-B99A9384"
    )
    assert row["used_value"] is None and row["usage_source"] == quotas.NONE


def test_nothing_records_a_request_as_submitted_by_meter() -> None:
    assert not any(r["submitted_by_meter"] for r in quotas.request_rows())
    assert {r["status"] for r in quotas.request_rows()} >= {
        "APPROVED",
        "DENIED",
        "PENDING",
        "CASE_OPENED",
    }


def test_no_day_in_the_whole_history_exceeds_its_limit() -> None:
    """Two years, every quota, about four seconds. A single violating day is the bug."""
    for r in quotas.history_rows():
        if r["used_value"] is not None:
            assert _number(r, "used_value") <= _number(r, "limit_value"), r


# -------------------------------------------------------------- manifest


def test_every_planted_code_on_a_spec_or_workload_is_in_the_manifest() -> None:
    used = {s.planted for s in utilization.SPECS if s.planted}
    used |= {w.planted for w in containers.WORKLOADS if w.planted}
    assert used <= set(planted.BY_CODE)


def test_every_planted_resource_subject_exists() -> None:
    known = {s.resource_id for s in utilization.SPECS} | {w.key for w in containers.WORKLOADS}
    known |= {n.node_id for n in topology.nodes()}
    for p in planted.PLANTED:
        for subject in p.subjects:
            if "/" in subject and not subject.startswith(("fake-", "*")):
                assert subject in known, (p.code, subject)
