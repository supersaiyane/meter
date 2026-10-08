"""Reading AWS's price list and its description of instance types. P9, TASK-P9-002.

P9 spec sections 5.2 to 5.4 and 14. Constraint 1: no SDK here. Read only, constraint 6.

Two ports rather than one, because the two are read from different places and fail apart: prices
through the Price List Query API in us-east-1, and EC2's instance types through
`DescribeInstanceTypes` in the hub's own Region, ADR-0035. A caller that can read one has learned
nothing about whether it can read the other.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.catalog import InstanceTypeSpec, Price, PriceListVersion, PriceSheet


@runtime_checkable
class PriceCatalog(Protocol):
    """AWS's published prices, one service and one Region at a time."""

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        """The current version of a service's price list in every Region it is sold in.

        The Regions are the price list's own, never a list in code, P9 spec section 14.2.

        Raises:
            AccessDenied: The session may not read the price list.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            SchemaDrift: A version or a publication date this cannot read.
        """
        ...

    def prices(self, version: PriceListVersion) -> Iterable[Price]:
        """Every on demand and reserved price in one version of one service in one Region.

        A term whose every price is nought is refused rather than returned as a price.

        Raises:
            AccessDenied: The session may not read the price list.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            NoData: The version names a service and Region the price list holds nothing for.
            SchemaDrift: A product or term this cannot read, or a price of nought.
        """
        ...


@runtime_checkable
class InstanceCatalog(Protocol):
    """EC2's own description of its instance types, per Region."""

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        """Every instance type EC2 describes in a Region.

        Raises:
            AccessDenied: The session may not describe instance types.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            NotOptedIn: The Region is not enabled for the account.
            SchemaDrift: A description with no vCPUs, no memory, or a shape this cannot read.
        """
        ...


@runtime_checkable
class SavingsPlansRates(Protocol):
    """Savings Plans rates for EC2 usage, one Region at a time. TASK-P9-012.

    Read through the relay outside the VPC, ADR-0035 and OPEN-17. The rates carry no published
    version, so a sheet's version is a digest of its rates, `sheet_version`.
    """

    def rates(self, region: str) -> PriceSheet:
        """Every Compute and EC2 Instance Savings Plans rate for shared tenancy EC2 in a Region.

        Raises:
            AccessDenied: The relay's role may not read the rates.
            Throttled: The provider rejected the call rate.
            Unreachable: The relay or the endpoint did not answer.
            NoData: No rate for EC2 in this Region.
            SchemaDrift: A rate this cannot read, a rate of nought, or more pages than the relay
                follows.
        """
        ...
