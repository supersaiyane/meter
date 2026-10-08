"""The sizing rule that names a target, held to spec section 5.5. TASK-P9-007.

The offers are the fake estate's types at the fake catalog's prices, so the planted m5.2xlarge at
7 percent CPU with no agent is the case the plan names: it is offered m5.xlarge, one size down in
its family, and saves the price difference rather than 90.9 percent of its cost.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finops_query.targets import (
    HOURS_PER_MONTH,
    Demand,
    Target,
    TypeOffer,
    candidates,
    choose,
    family_of,
    hours_per_month,
    misfit,
    saving,
)

GIB = 1024


def offer(
    name: str,
    vcpus: int,
    memory_gib: int,
    price: str | None,
    *,
    arm: bool = False,
    burstable: bool = False,
    network: str | None = None,
    ebs: int | None = None,
) -> TypeOffer:
    return TypeOffer(
        instance_type=name,
        vcpus=vcpus,
        memory_mib=memory_gib * GIB,
        architectures=("arm64",) if arm else ("x86_64",),
        burstable=burstable,
        hourly_price=None if price is None else Decimal(price),
        sku_price_id=None if price is None else f"SKU-{name}",
        network_baseline_gbps=None if network is None else Decimal(network),
        ebs_baseline_mbps=ebs,
    )


M5_2XL = offer("m5.2xlarge", 8, 32, "0.3894")
OFFERED = (
    M5_2XL,
    offer("m5.xlarge", 4, 16, "0.1947"),
    offer("m5.large", 2, 8, "0.0974"),
    offer("m5.4xlarge", 16, 64, "0.7788"),
    offer("m6i.xlarge", 4, 16, "0.2028"),
    offer("m6i.2xlarge", 8, 32, "0.4056"),
    offer("m6a.xlarge", 4, 16, "0.1800"),
    offer("m6g.xlarge", 4, 16, "0.1600", arm=True),
    offer("m6g.large", 2, 8, None, arm=True),
    offer("m5d.xlarge", 4, 16, "0.1500"),
    offer("c5.2xlarge", 8, 16, "0.3400"),
    offer("t3.large", 2, 8, "0.0832", burstable=True),
    offer("m4.xlarge", 4, 16, "0.1000"),
)


# --- names ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "series", "generation", "processor", "features", "size"),
    [
        ("m5.2xlarge", "m", 5, "", "", "2xlarge"),
        ("m6i.large", "m", 6, "", "", "large"),
        ("m6a.large", "m", 6, "a", "", "large"),
        ("m6gd.large", "m", 6, "g", "d", "large"),
        ("c7gn.xlarge", "c", 7, "g", "n", "xlarge"),
        ("r6idn.large", "r", 6, "", "dn", "large"),
        ("g4dn.xlarge", "g", 4, "", "dn", "xlarge"),
        ("g5g.xlarge", "g", 5, "g", "", "xlarge"),
    ],
)
def test_a_type_is_read_as_its_series_generation_processor_and_size(
    name: str, series: str, generation: int, processor: str, features: str, size: str
) -> None:
    found = family_of(name)
    assert found is not None
    assert (found.series, found.generation, found.processor, found.features, found.size) == (
        series,
        generation,
        processor,
        features,
        size,
    )


@pytest.mark.parametrize("name", ["db.m5.large", "u-6tb1.metal", "m5", "large"])
def test_a_name_outside_the_ec2_grammar_is_none(name: str) -> None:
    assert family_of(name) is None


# --- candidates ---------------------------------------------------------------------------


def test_with_memory_known_the_family_its_newer_generations_and_variants_are_candidates() -> None:
    found = {o.instance_type for o in candidates(M5_2XL, OFFERED, memory_known=True)}
    assert found == {
        "m5.xlarge",
        "m5.large",
        "m6i.xlarge",
        "m6i.2xlarge",
        "m6a.xlarge",
        "m6g.xlarge",
        "m6g.large",
    }


def test_with_no_memory_figure_only_one_size_down_in_the_family_is_a_candidate() -> None:
    found = {o.instance_type for o in candidates(M5_2XL, OFFERED, memory_known=False)}
    assert found == {"m5.xlarge"}


def test_a_burstable_type_is_never_offered_for_a_steady_one() -> None:
    found = candidates(offer("m5.large", 2, 8, "0.0974"), OFFERED, memory_known=True)
    assert all(not o.burstable for o in found)


def test_an_older_generation_or_another_series_or_feature_is_not_a_candidate() -> None:
    found = {o.instance_type for o in candidates(M5_2XL, OFFERED, memory_known=True)}
    assert {"m4.xlarge", "c5.2xlarge", "m5d.xlarge", "m5.4xlarge"}.isdisjoint(found)


def test_a_type_outside_the_grammar_has_no_candidates() -> None:
    assert candidates(offer("u-6tb1.metal", 448, 6144, "1"), OFFERED, memory_known=True) == []


# --- fit ---------------------------------------------------------------------------------


def test_cpu_is_sized_at_p99_with_headroom() -> None:
    # 8 vCPUs at a p99 of 30 percent need 3.12 with 30 percent headroom: four fit, two do not.
    demand = Demand(cpu_p99_percent=Decimal(30), memory_peak_percent=Decimal(10))
    assert misfit(M5_2XL, offer("m5.xlarge", 4, 16, "0.19"), demand) is None
    found = misfit(M5_2XL, offer("m5.large", 2, 8, "0.09"), demand)
    assert "2 vCPUs and 3.12 are needed" in str(found)


@pytest.mark.parametrize(("oom", "fits"), [(False, True), (True, False)])
def test_memory_is_sized_at_its_peak_with_more_after_an_oom_kill(oom: bool, fits: bool) -> None:
    # 32 GiB peaking at 42 percent is 13.4 GiB: 15.5 with 15 percent headroom, 16.8 with 25.
    demand = Demand(cpu_p99_percent=Decimal(5), memory_peak_percent=Decimal(42), oom_killed=oom)
    found = misfit(M5_2XL, offer("m5.xlarge", 4, 16, "0.19"), demand)
    assert (found is None) is fits
    if not fits:
        assert "MiB" in str(found)


def test_network_and_ebs_are_held_to_the_baseline_not_the_burst() -> None:
    target = offer("m5.xlarge", 4, 16, "0.19", network="1.25", ebs=1150)
    quiet = Decimal(5), Decimal(10)
    busy_network = Demand(*quiet, network_p99_gbps=Decimal(2))
    busy_disk = Demand(*quiet, ebs_p99_mbps=Decimal(2000))
    within = Demand(*quiet, network_p99_gbps=Decimal("0.5"), ebs_p99_mbps=Decimal(500))
    assert "network baseline" in str(misfit(M5_2XL, target, busy_network))
    assert "EBS baseline" in str(misfit(M5_2XL, target, busy_disk))
    assert misfit(M5_2XL, target, within) is None


# --- choosing ---------------------------------------------------------------------------


def test_the_planted_m5_2xlarge_with_no_agent_is_offered_m5_xlarge() -> None:
    chosen = choose(M5_2XL, OFFERED, Demand(cpu_p99_percent=Decimal(7)))
    assert isinstance(chosen, Target)
    assert chosen.offer.instance_type == "m5.xlarge"
    assert any("no agent publishes memory" in note for note in chosen.notes)


def test_with_memory_known_the_cheapest_fit_is_chosen_and_its_differences_named() -> None:
    chosen = choose(
        M5_2XL, OFFERED, Demand(cpu_p99_percent=Decimal(7), memory_peak_percent=Decimal(10))
    )
    assert isinstance(chosen, Target)
    # m6g.large is unpriced, so the cheapest priced fit is m5.large at 2 vCPUs.
    assert chosen.offer.instance_type == "m5.large"
    assert chosen.notes == ()


def test_a_graviton_target_says_so() -> None:
    offered = (M5_2XL, offer("m6g.xlarge", 4, 16, "0.1600", arm=True))
    chosen = choose(
        M5_2XL, offered, Demand(cpu_p99_percent=Decimal(20), memory_peak_percent=Decimal(30))
    )
    assert isinstance(chosen, Target)
    assert chosen.notes == (
        "vCPUs are not equivalent across a generation or an architecture",
        "Graviton needs arm64 builds of everything the instance runs",
    )


def test_an_unpublished_baseline_is_said_rather_than_passed() -> None:
    demand = Demand(
        Decimal(7), Decimal(10), network_p99_gbps=Decimal("0.1"), ebs_p99_mbps=Decimal(5)
    )
    chosen = choose(M5_2XL, OFFERED, demand)
    assert isinstance(chosen, Target)
    assert any("no network baseline" in note for note in chosen.notes)
    assert any("no EBS baseline" in note for note in chosen.notes)


@pytest.mark.parametrize(
    ("current", "offered", "demand", "says"),
    [
        (offer("m5.2xlarge", 8, 32, None), OFFERED, Demand(Decimal(7)), "no price for m5.2xlarge"),
        (M5_2XL, (M5_2XL,), Demand(Decimal(7)), "at no lower price"),
        (M5_2XL, OFFERED, Demand(Decimal(70), Decimal(90)), "no cheaper type fits"),
    ],
)
def test_no_target_is_a_sentence_saying_why(
    current: TypeOffer, offered: tuple[TypeOffer, ...], demand: Demand, says: str
) -> None:
    chosen = choose(current, offered, demand)
    assert isinstance(chosen, str)
    assert says in chosen


# --- the saving -------------------------------------------------------------------------


def test_an_always_on_instance_runs_the_whole_month() -> None:
    assert hours_per_month(points=24 * 30, observation_days=30) == HOURS_PER_MONTH
    assert hours_per_month(points=12 * 30, observation_days=30) == HOURS_PER_MONTH / 2
    assert hours_per_month(points=10, observation_days=0) == 0


def test_the_saving_is_the_price_difference_scaled_to_the_bill_never_up() -> None:
    hours = HOURS_PER_MONTH
    discounted = saving(
        current_hourly=Decimal("0.3894"),
        target_hourly=Decimal("0.1947"),
        hours=hours,
        paid_monthly=Decimal("0.3894") * hours * Decimal("0.8"),
    )
    assert discounted.at_list == Decimal("142.13")
    assert discounted.paid_ratio == Decimal("0.8")
    assert discounted.as_paid == Decimal("113.70")
    above = saving(
        current_hourly=Decimal("0.3894"),
        target_hourly=Decimal("0.1947"),
        hours=hours,
        paid_monthly=Decimal(999),
    )
    assert above.paid_ratio == 1
    assert above.as_paid == above.at_list
