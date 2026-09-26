"""Terraform state for an estate, with one backend that refuses.

FEAT-057. ADR-0022 keeps this out of the production packages.

**Partial by default, like the topology fake.** One of the three configured backends refuses,
so every test above the provider runs against a read that is not whole unless it deliberately
asks otherwise. That matters more here than anywhere else in the project: the whole feature
turns on refusing to say `UNMANAGED` on an incomplete read, and a fake that always read wholly
would leave that path exercised by nothing a developer runs.

**And one resource in the state has no ARN.** `aws_route_table_association` has no ARN at all,
which is not an edge case: a real state file is full of associations, attachments and policy
documents that carry no ARN and therefore cannot be joined to anything Meter inventoried. The
collector counts them, and a fake without one would make that count look like dead code.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from finops_core.domain.iac import ManagedResource, StateRead

AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)

NETWORK = "s3://fake-state/network.tfstate"
PLATFORM = "s3://fake-state/platform.tfstate"
#: The one that refuses. Named after what it holds rather than after its failure, because a
#: fake whose broken thing is called broken tests nothing about how a reader finds it.
PRODUCT = "s3://fake-state-product/main.tfstate"

LOCATIONS = (NETWORK, PLATFORM, PRODUCT)

#: What the readable backends own, keyed by the identifiers the fake estate actually uses.
#:
#: Not ARNs, and that is not a shortcut. `topology_node.provider_id` is documented as an ARN and
#: the fake estate's identifiers are `amazonvpc/account/region/name`, which is ISS-202's second
#: paragraph in the flesh: three of the four supplementary APIs return bare identifiers and the
#: ARN is the identity everywhere else. A fake that used ARNs here would have joined to nothing
#: and the whole feature would have looked broken for a reason that has nothing to do with it.
#:
#: So the fake follows the estate rather than the schema comment. When ISS-202 or ISS-205 is
#: closed by normalising identifiers at ingest, these three move with it.
_OWNED: tuple[tuple[str, str, str], ...] = (
    (
        "amazonvpc/fake-platform-a/fake-region-a/vpc",
        "module.network.aws_vpc.main",
        NETWORK,
    ),
    (
        "amazonvpc/fake-platform-a/fake-region-a/subnet-a",
        'module.network.aws_subnet.private["a"]',
        NETWORK,
    ),
    (
        "amazonec2/fake-platform-a/0001",
        "module.platform.aws_instance.api",
        PLATFORM,
    ),
)


class FakeTerraformState:
    """The configured backends, one of which refuses."""

    def __init__(self, *, locations: tuple[str, ...] = LOCATIONS, whole: bool = False) -> None:
        self._locations = locations
        # `whole` exists for the one test that needs a complete read in order to exercise the
        # UNMANAGED path. Defaulting it to True would have made the partial path the exception.
        self._whole = whole

    @property
    def locations(self) -> tuple[str, ...]:
        return self._locations

    def read(self, locations: Iterable[str]) -> StateRead:
        wanted = frozenset(locations)
        managed = tuple(
            ManagedResource(
                provider_id=provider_id,
                address=address,
                state_reference=reference,
                as_of=AT,
                collected_at=AT,
            )
            for provider_id, address, reference in _OWNED
            if reference in wanted
        )
        if self._whole or PRODUCT not in wanted:
            return StateRead(managed=managed)
        return StateRead(managed=managed, refused=((PRODUCT, "AccessDenied"),))
