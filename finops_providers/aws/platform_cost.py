"""One Cost Explorer request per day, grouped by module and service.

Cost Explorer charges per request, so the shape of this matters more than it
looks. One grouped request answers the whole question. Calling it per module
would multiply a metered API by the number of modules, which is a tool that
makes its own bill worse the more carefully it measures itself.

The tag value arrives as `finops:module$value`, and untagged cost arrives with
an empty value after the separator. That empty case is returned as an empty
module rather than silently discarded; the collector decides what an untagged
charge is called, because that is a domain question and not an API detail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.constants import PLATFORM_TAG_KEY
from finops_providers.aws.client import botocore_config, translate

COLLECTOR = "platform_cost"
SCOPE = "platform"
TAG_SEPARATOR = "$"
AMORTIZED = "AmortizedCost"

ClientFactory = Callable[[], Any]


@dataclass(frozen=True)
class ModuleCharge:
    """One day, one module tag value, one service, as the provider reported it."""

    day: date
    #: Empty when the charge carried no module tag. Naming it is the caller's job.
    module: str
    service: str
    amortized_cost: Decimal


class AwsPlatformCostSource:
    """Reads the platform's own spend, grouped, in a single request."""

    def __init__(
        self,
        settings: Settings,
        client_factory: ClientFactory | None = None,
        tag_key: str = PLATFORM_TAG_KEY,
    ) -> None:
        self._settings = settings
        self._tag_key = tag_key
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client

    def _default_client(self) -> Any:
        return boto3.client("ce", config=self._config)

    def daily_by_module(self, start: date, end: date) -> tuple[ModuleCharge, ...]:
        """Every module and service charge between start and end.

        Raises:
            AccessDenied: The hub role may not read Cost Explorer.
            NotOptedIn: Cost Explorer has never been enabled for this payer.
            Throttled: Cost Explorer rejected the request rate.
            Unreachable: The endpoint did not answer.
            SchemaDrift: The response held a group shape this adapter does not
                recognise, which is loud rather than silently skipped.
        """
        try:
            response = self._factory().get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="DAILY",
                Metrics=[AMORTIZED],
                GroupBy=[
                    {"Type": "TAG", "Key": self._tag_key},
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                ],
            )
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=SCOPE, collector=COLLECTOR) from failure
        return self._parse(response)

    def _parse(self, response: Any) -> tuple[ModuleCharge, ...]:
        charges: list[ModuleCharge] = []
        for period in response.get("ResultsByTime", []):
            day = date.fromisoformat(period["TimePeriod"]["Start"])
            for group in period.get("Groups", []):
                keys = list(group.get("Keys", []))
                if len(keys) != 2:
                    raise translate(
                        ValueError(f"expected a tag and a service, got {keys!r}"),
                        scope_key=SCOPE,
                        collector=COLLECTOR,
                    )
                returned_key, _, module = keys[0].partition(TAG_SEPARATOR)
                if returned_key != self._tag_key:
                    # Grouping by one tag and being answered about another means
                    # every module attribution below is wrong, so it is loud.
                    raise translate(
                        ValueError(f"asked for tag {self._tag_key!r}, got {returned_key!r}"),
                        scope_key=SCOPE,
                        collector=COLLECTOR,
                    )
                amount = group["Metrics"][AMORTIZED]["Amount"]
                charges.append(
                    ModuleCharge(
                        day=day,
                        module=module,
                        service=keys[1],
                        amortized_cost=Decimal(str(amount)),
                    )
                )
        return tuple(charges)
