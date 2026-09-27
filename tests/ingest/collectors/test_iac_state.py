"""What manages a resource, over a real database.

FEAT-057, TASK-P4-013. The three valued rule has its own suite in `tests/core/test_iac.py`.
What this asks is what actually lands in `resource_management`, and the cases that carry the
file are the two about removal.

A row here means we found a resource in state; no row means we did not find it. So removing a
row is how a managed resource comes to read as not determined, and a collector that removed
rows for a location it failed to read would report managed resources as unknown on the strength
of a failure. That is the inverse of the mistake the whole feature exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.iac import ManagedResource, StateRead
from finops_fakes.terraform_state import NETWORK, PLATFORM, PRODUCT, FakeTerraformState
from finops_ingest.collectors.iac_state import IacStateCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
MINE = "fake-platform-a"
#: The identifiers the fake estate uses, which are not ARNs although the column is documented
#: as one. That is ISS-202's second paragraph and is why the fake state follows the estate: a
#: fake using ARNs here would join to nothing and the feature would look broken for a reason
#: that has nothing to do with it.
VPC = "amazonvpc/fake-platform-a/us-fake-1/vpc"
SUBNET = "amazonvpc/fake-platform-a/us-fake-1/subnet-a"
INSTANCE = "amazonec2/fake-platform-a/0001"
#: Owned only by the state location that refuses, so its row is the one the removal rule
#: has to protect. A resource the readable locations also own would be rewritten by them on
#: every run and would survive for the wrong reason, which is what the first draft asserted.
QUEUE = "arn:aws:sqs:us-fake-1:fake-platform-a:orders"

INSERT_ACCOUNT = text(
    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, name, status, "
    "as_of, collected_at) VALUES (:pk, :t, 'aws', :a, :a, 'ACTIVE', :at, :at) "
    "ON CONFLICT DO NOTHING"
)
INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)
INSERT_NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
    "provider_id, node_kind, resource_type, region_id, availability_zone, name, as_of, "
    "collected_at) VALUES (:node, :t, :run, :a, :p, 'OTHER', 'AWS::EC2::VPC', "
    "'us-fake-1', NULL, :n, :at, :at)"
)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def inventory(engine: Engine, tenant: UUID, *provider_ids: str) -> None:
    """The nodes the state resources join to.

    Seeded rather than assumed, because the account on a `resource_management` row comes from
    the node and not from the ARN: a resource with no node cannot be placed and is counted
    instead, which is a case below.
    """
    with engine.begin() as connection:
        run = uuid4()
        connection.execute(INSERT_ACCOUNT, {"pk": uuid4(), "t": tenant, "a": MINE, "at": NOW})
        connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": NOW})
        for index, provider_id in enumerate(provider_ids):
            connection.execute(
                INSERT_NODE,
                {
                    "node": uuid4(),
                    "t": tenant,
                    "run": run,
                    "a": MINE,
                    "p": provider_id,
                    "n": f"node-{index}",
                    "at": NOW,
                },
            )


def collect(
    engine: Engine,
    tenant: UUID,
    settings: Settings,
    *,
    source: object | None = None,
    run_id: UUID | None = None,
) -> int:
    with engine.begin() as connection:
        outcome = IacStateCollector(source or FakeTerraformState(), clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=run_id or uuid4(),
                settings=settings,
            )
        )
    return int(outcome.items_written)


def managed_rows(engine: Engine, tenant: UUID) -> dict[str, tuple[str, str, str]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT provider_id, address, state_reference, sub_account_id "
                    "FROM resource_management WHERE tenant_id = :t"
                ),
                {"t": tenant},
            )
        }


def errors(engine: Engine, tenant: UUID) -> dict[str, tuple[str, str]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                text(
                    "SELECT scope_key, error_type, detail FROM sync_error "
                    "WHERE tenant_id = :t AND collector = 'iac_state'"
                ),
                {"t": tenant},
            )
        }


def configured(
    settings: Settings, *, locations: tuple[str, ...] = (NETWORK, PLATFORM, PRODUCT)
) -> Settings:
    return settings.model_copy(update={"iac_state_locations": ",".join(locations)})


def test_a_resource_in_the_state_gets_its_address_recorded(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    inventory(engine, tenant_id, VPC, SUBNET, INSTANCE)
    assert collect(engine, tenant_id, configured(settings)) == 3
    rows = managed_rows(engine, tenant_id)
    assert rows[VPC][0] == "module.network.aws_vpc.main"
    # The index key, rendered the way Terraform renders a for_each key. `aws_subnet.private[0]`
    # and `aws_subnet.private["a"]` are different addresses and only one of them exists.
    assert rows[SUBNET][0] == 'module.network.aws_subnet.private["a"]'
    # The location, so a reader can find the file rather than being told something unnamed
    # manages their resource.
    assert rows[VPC][1] == NETWORK
    # The account from the node, not from the ARN.
    assert rows[VPC][2] == MINE


def test_nothing_is_written_when_no_location_is_configured(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A real deployment rather than a failure. Nothing configured means nothing read, and every
    resource reads as not determined, which is true. Returning zero rather than raising is what
    lets the collector be scheduled before anybody configures it."""
    inventory(engine, tenant_id, VPC)
    assert collect(engine, tenant_id, settings) == 0
    assert managed_rows(engine, tenant_id) == {}
    assert errors(engine, tenant_id) == {}


def test_a_refused_location_is_recorded_with_its_cause_and_the_name_of_the_file(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Both, because a screen saying something went wrong sends nobody anywhere. The remediation
    says what the consequence is, so a reader knows the gap is not a claim about their code."""
    inventory(engine, tenant_id, VPC, SUBNET, INSTANCE)
    collect(engine, tenant_id, configured(settings))
    found = errors(engine, tenant_id)
    assert PRODUCT in found
    assert found[PRODUCT][0] == "AccessDenied"
    assert "what it manages is not known" in found[PRODUCT][1]


def test_a_state_resource_with_no_inventoried_node_is_counted_rather_than_written(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Terraform owns things Config has never recorded, and a state file has no account column,
    so a resource with no node cannot be placed. Counted, because a state file full of resources
    we cannot join is a fact about our inventory rather than about their code."""
    # Only the VPC is inventoried. The subnet and the role are not.
    inventory(engine, tenant_id, VPC)
    assert collect(engine, tenant_id, configured(settings)) == 1
    assert set(managed_rows(engine, tenant_id)) == {VPC}
    found = errors(engine, tenant_id)
    assert "2 resources in state matched no inventoried resource" in found["iac"][1]
    assert found["iac"][0] == "NoData"


def test_a_resource_removed_from_a_location_that_was_read_loses_its_row(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The first of the two removal cases. A resource taken out of Terraform is genuinely no
    longer managed by it, and leaving the row would point FEAT-040 at a block that is gone."""
    inventory(engine, tenant_id, VPC, SUBNET, INSTANCE)
    collect(engine, tenant_id, configured(settings))
    assert VPC in managed_rows(engine, tenant_id)

    # The same locations, and the network state no longer owns the VPC.
    class WithoutTheVpc(FakeTerraformState):
        def read(self, locations: object) -> StateRead:
            whole = super().read(locations)  # type: ignore[arg-type]
            return StateRead(
                managed=tuple(one for one in whole.managed if one.provider_id != VPC),
                refused=whole.refused,
            )

    collect(engine, tenant_id, configured(settings), source=WithoutTheVpc())
    assert VPC not in managed_rows(engine, tenant_id)
    assert SUBNET in managed_rows(engine, tenant_id)


def test_a_row_from_a_location_that_refused_us_is_kept(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The second removal case, and the one this file exists for.

    A row is removed when the location that held it was read and no longer names the resource.
    If the location refused us instead, removing the row would turn a managed resource into a
    not determined one because of a failure, and a reader would be told nothing is known about
    a resource whose address we recorded yesterday.
    """
    inventory(engine, tenant_id, VPC, SUBNET, INSTANCE, QUEUE)

    class Whole(FakeTerraformState):
        """Every location reads, and the refusing one owns a resource of its own."""

        def read(self, locations: object) -> StateRead:
            base = FakeTerraformState(whole=True).read(locations)  # type: ignore[arg-type]
            return StateRead(
                managed=(
                    *base.managed,
                    ManagedResource(
                        provider_id=QUEUE,
                        address="module.orders.aws_sqs_queue.main",
                        state_reference=PRODUCT,
                        as_of=NOW,
                        collected_at=NOW,
                    ),
                ),
            )

    collect(engine, tenant_id, configured(settings), source=Whole())
    assert managed_rows(engine, tenant_id)[QUEUE][1] == PRODUCT

    # A second run where the product state refuses. Its row survives, because the location that
    # held it was never read, and absence from a location nobody read is not absence.
    collect(engine, tenant_id, configured(settings))
    after = managed_rows(engine, tenant_id)
    assert QUEUE in after, "a row was removed because its own state location could not be read"
    assert after[QUEUE][1] == PRODUCT
    # And the readable locations still wrote, so this was not a run that left everything alone.
    assert VPC in after


def test_a_resource_that_moves_between_state_files_keeps_one_row(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Two addresses for one resource would let FEAT-040 open a pull request against whichever
    the query happened to return first."""
    inventory(engine, tenant_id, VPC, SUBNET, INSTANCE)
    collect(engine, tenant_id, configured(settings))
    collect(engine, tenant_id, configured(settings))
    with engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM resource_management WHERE tenant_id = :t AND provider_id = :p"
            ),
            {"t": tenant_id, "p": VPC},
        ).scalar_one()
    assert count == 1


def test_it_refuses_to_run_without_settings(engine: Engine, tenant_id: UUID) -> None:
    """The locations are configuration, and searching for them instead would mean listing
    somebody's buckets to see what is in them."""
    with engine.begin() as connection, pytest.raises(ValueError, match="configuration"):
        IacStateCollector(FakeTerraformState(), clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant_id),
                connection=connection,
                run_id=uuid4(),
                settings=None,
            )
        )
