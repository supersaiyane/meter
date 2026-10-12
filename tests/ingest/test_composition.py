"""Every collector the worker runs is composed, for a deployment and for the local stack.

TASK-P12-001, P12 spec section 5.1 and ADR-0022. Until this composition nothing outside the tests
assembled a registry, ISS-182, so a deployed worker would have run nothing. These hold the two
compositions to the schedule, each other's scopes, and the rule that a collector with no AWS
adapter fails typed rather than runs on something invented.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.errors import Misconfigured
from finops_fakes.composition import builders, fake_bindings, fake_registry
from finops_ingest.composition import (
    PER_ACCOUNT,
    RETENTION,
    production_bindings,
    production_registry,
    worker_collectors,
)
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorScope

AT = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
UNIT = WorkUnit(
    tenant_id=uuid4(),
    collector="quotas",
    window_start=AT,
    window_end=AT,
    account=AccountKey(provider=Provider.AWS, account_id="111111111111"),
    region="eu-west-1",
)


def context(settings: Any = None) -> CollectorContext:
    return CollectorContext(unit=UNIT, connection=None, settings=settings)


def test_a_deployment_composes_every_collector_the_schedule_runs_in_the_worker() -> None:
    assert set(production_registry().names()) == worker_collectors()


def test_the_local_stack_composes_the_same_collectors() -> None:
    assert set(fake_registry(lambda: AT).names()) == worker_collectors()


def test_a_collector_is_bound_once_and_retention_is_left_to_the_registry() -> None:
    for bindings in (production_bindings(), fake_bindings(lambda: AT)):
        names = [one.name for one in bindings]
        assert len(names) == len(set(names))
        assert not RETENTION & set(names)


def test_both_compositions_agree_on_what_one_unit_covers() -> None:
    production = {one.name: one.scope for one in production_bindings()}
    fake = {one.name: one.scope for one in fake_bindings(lambda: AT)}
    assert production == fake
    assert {name for name, scope in production.items() if scope is CollectorScope.ACCOUNT} == (
        PER_ACCOUNT
    )


def test_a_collector_with_no_aws_adapter_fails_typed_naming_what_it_lacks() -> None:
    quotas = production_registry().get("quotas")
    with pytest.raises(Misconfigured, match="Service Quotas") as raised:
        quotas.run(context())
    assert raised.value.scope_key == UNIT.scope_key


def test_a_collector_that_reads_only_meter_is_built_for_real_in_a_deployment() -> None:
    built = {one.name: one.build for one in production_bindings()}
    for name in ("savings_ledger", "finops_score", "realized_savings", "ownership"):
        assert callable(built[name](context()))


def test_every_fake_builds_its_collector_for_a_unit(settings: Settings) -> None:
    for name, build in builders(lambda: AT).items():
        assert callable(build(context(settings))), name


def test_a_per_account_fake_is_handed_only_its_own_accounts_candidates() -> None:
    from finops_fakes.composition import _compute_candidates
    from finops_fakes.estate_metrics import ec2_candidates

    accounts = {one.account_id for one in ec2_candidates(at=AT)}
    for account in accounts:
        unit = WorkUnit(
            tenant_id=UNIT.tenant_id,
            collector="waste_compute",
            window_start=AT,
            window_end=AT,
            account=AccountKey(provider=Provider.AWS, account_id=account),
            region="eu-west-1",
        )
        found = _compute_candidates(lambda: AT)(CollectorContext(unit=unit, connection=None))
        assert found and {one.account_id for one in found} == {account}
