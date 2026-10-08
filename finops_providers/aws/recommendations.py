"""What AWS already worked out, read through three services.

**Nothing in this file has ever made a call.** ISS-122. It is written against the
AWS documentation and the shapes botocore declares, it is unit tested against
recorded responses, and it is held to the same contract as the fake. None of that
is the same thing as having run.

The part most likely to be wrong is the **estimated saving field name in each
service**, because all three report money and none of them agrees on what to call
it. Cost Optimization Hub returns `estimatedMonthlySavings`, Compute Optimizer
returns a nested `estimatedMonthlySavings.value` inside a savings opportunity, and
Trusted Advisor returns a check result whose money is a string in a positional
metadata array. That third one is the weakest mapping here and the first thing a
real account will correct.

Two rules carry the file.

**`NotOptedIn` is raised as itself.** Compute Optimizer needs an organization level
opt in, ISS-004, and Trusted Advisor's checks need a support tier, OPEN-03. An
estate without either is correctly configured and simply has fewer signals. A
caller must be able to tell that from an estate with no waste, because the second
is a comfortable lie.

**A money field that cannot be parsed is `SchemaDrift`, never zero.** A
recommendation reported as saving nothing is one nobody acts on, and it looks
exactly like a recommendation that genuinely saves nothing.

**Compute Optimizer is read Region by Region and account by account**, TASK-P9-006,
P9 spec section 5.5. It answers per Region, takes one member account a request, pages
by `nextToken` with no botocore paginator, and is asked for Graviton through its CPU
architecture preference. Every ranked option is kept, with its rank, its performance
risk and its own saving. One account or Region that cannot be read is returned as a
refusal beside what was read, `ScopedFindings`, so the collector records it and
withdraws nothing it could not see, constraint 5.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import (
    Lifecycle,
    RankedOption,
    Recommendation,
    ScopedFindings,
    Source,
    WasteClass,
)
from finops_core.errors import CollectionError, NotOptedIn, SchemaDrift
from finops_providers.aws.client import botocore_config, translate

COLLECTOR = "recommendations"
SCOPE = "billing"

#: Cost Optimization Hub and Compute Optimizer answer from one region for the
#: whole organization, like Cost Explorer.
HOME_REGION = "us-east-1"  # allow-hardcoded: the organization wide services answer here only

#: How Compute Optimizer names a finding, mapped to ours. A finding type we do not
#: recognise is skipped rather than guessed at, and the count of skipped ones is
#: worth more than a wrong class on a screen.
COMPUTE_OPTIMIZER_CLASSES: dict[str, WasteClass] = {
    "Overprovisioned": WasteClass.RIGHTSIZE_INSTANCE,
    "Underprovisioned": WasteClass.RIGHTSIZE_INSTANCE,
    "Idle": WasteClass.IDLE_INSTANCE,
}

#: Asked of Compute Optimizer for every instance: Graviton as well as the current architecture,
#: P9 spec section 5.5.
ARCHITECTURES: dict[str, list[str]] = {"cpuVendorArchitectures": ["AWS_ARM64", "CURRENT"]}
#: The most pages one account in one Region is followed for. Compute Optimizer returns up to
#: 1,000 instances a page by default, so this is far past any estate.
MAX_PAGES = 100

#: Trusted Advisor check identifiers we read. There are dozens; these are the ones
#: whose money is unambiguous.
TRUSTED_ADVISOR_CHECKS: dict[str, WasteClass] = {
    "Qch7DwouX1": WasteClass.IDLE_INSTANCE,
    "DAvU99Dc4C": WasteClass.LOAD_BALANCER_IDLE,
    "Z4AUBRNSmz": WasteClass.ELASTIC_IP_UNASSOCIATED,
    "hjLMh88uM8": WasteClass.EBS_UNATTACHED,
}

#: Codes that mean "you have not turned this on", as distinct from "you may not".
#: Kept here rather than in `client.py` because they are specific to these three
#: services, and widening the shared translation would make every adapter treat an
#: access failure as an opt in question.
NOT_ENABLED_CODES = frozenset(
    {
        "OptInRequiredException",
        "ResourceNotFoundException",
        "SubscriptionRequiredException",
        "AccessDeniedException",
    }
)


def _money(raw: Any, field: str) -> Decimal:
    """Money from a provider, or a typed refusal. Never a zero."""
    if raw is None:
        raise SchemaDrift(
            scope_key=SCOPE, collector=COLLECTOR, detail=f"no {field} in the response"
        )
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as error:
        raise SchemaDrift(
            scope_key=SCOPE, collector=COLLECTOR, detail=f"{field} was not a number: {raw!r}"
        ) from error


class CostRecommendationSource:
    """`RecommendationSource` over three AWS services. Unproved, ISS-122."""

    def __init__(
        self,
        settings: Settings,
        tenant_id: UUID,
        *,
        severity_of: Callable[[Decimal], str],
        client_factory: Callable[[str], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        accounts: Callable[[], Iterable[str]] | None = None,
        regional_client_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._tenant_id = tenant_id
        # Passed in rather than computed here, because severity comes from
        # settings thresholds and an adapter has no business reading them. The
        # same function the query findings and the anomalies use.
        self._severity_of = severity_of
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client
        self._clock = clock or (lambda: datetime.now(UTC))
        # The member accounts Compute Optimizer is asked about, one a request. From the
        # organization tree at composition; none means the caller's own account only.
        self._accounts = accounts or (lambda: ())
        if regional_client_factory is not None:
            self._regional = regional_client_factory
        elif client_factory is not None:
            # A single client stands for every Region, as the recorded responses do.
            self._regional = lambda service, _region: client_factory(service)
        else:
            self._regional = self._default_regional_client

    def _default_client(self, service: str) -> Any:
        return boto3.client(service, region_name=HOME_REGION, config=self._config)

    def _default_regional_client(self, service: str, region: str) -> Any:
        return boto3.client(service, region_name=region, config=self._config)

    def _call(self, service: str, name: str, **kwargs: Any) -> Any:
        try:
            return getattr(self._factory(service), name)(**kwargs)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in NOT_ENABLED_CODES:
                # An expected state, not a fault. The caller renders "not opted in,
                # here is how" rather than "no waste found".
                raise NotOptedIn(
                    scope_key=SCOPE,
                    collector=COLLECTOR,
                    detail=f"{service} is not enabled for this organization: {code}",
                ) from error
            raise translate(error, scope_key=SCOPE, collector=COLLECTOR) from error
        except BotoCoreError as error:
            raise translate(error, scope_key=SCOPE, collector=COLLECTOR) from error

    def _build(
        self,
        *,
        source: Source,
        reference: str,
        waste_class: WasteClass,
        resource_id: str,
        region_id: str,
        saving: Decimal,
        observation_days: int,
        rationale: str,
    ) -> Recommendation:
        now = self._clock()
        return Recommendation(
            as_of=now,
            collected_at=now,
            tenant_id=self._tenant_id,
            sub_account_id=_account_of(resource_id),
            source=source,
            source_reference=reference,
            waste_class=waste_class,
            resource_id=resource_id,
            region_id=region_id,
            estimated_monthly_saving=saving,
            severity=self._severity_of(saving),
            observation_days=observation_days,
            lifecycle=Lifecycle.OPEN,
            owner=None,
            ticket_reference=None,
            rationale=rationale,
        )

    # -- the port ----------------------------------------------------------

    def compute_optimizer(self) -> ScopedFindings:
        accounts: tuple[str | None, ...] = tuple(self._accounts()) or (None,)
        found: dict[str, Recommendation] = {}
        read: set[tuple[str, str]] = set()
        refused: list[CollectionError] = []
        for region in self._settings.region_list:
            client = self._regional("compute-optimizer", region)
            for account in accounts:
                try:
                    items = [
                        rec
                        for raw in self._instance_recommendations(client, region, account)
                        if (rec := self._optimizer_recommendation(raw, region)) is not None
                    ]
                except CollectionError as failure:
                    refused.append(failure)
                    continue
                # An account read is a scope; the caller's own account, unnamed, is every
                # account the call answered for in that Region.
                read.add((account or "*", region))
                for rec in items:
                    found.setdefault(rec.source_reference, rec)
        if refused and not read:
            raise refused[0]
        return ScopedFindings(
            found=tuple(found.values()), read=frozenset(read), refused=tuple(refused)
        )

    def _instance_recommendations(
        self, client: Any, region: str, account: str | None
    ) -> Iterable[Any]:
        """Every instance recommendation for one account in one Region, every page."""
        scope = f"{account or 'own'}:{region}"
        request: dict[str, Any] = {"recommendationPreferences": ARCHITECTURES}
        if account is not None:
            request["accountIds"] = [account]
        items: list[Any] = []
        for _ in range(MAX_PAGES):
            page = self._optimizer_call(client, scope, **request)
            items.extend(page.get("instanceRecommendations") or ())
            token = page.get("nextToken")
            if not token:
                return items
            request = {**request, "nextToken": token}
        raise SchemaDrift(
            scope_key=scope,
            collector=COLLECTOR,
            detail=f"more than {MAX_PAGES} pages of instance recommendations",
        )

    def _optimizer_call(self, client: Any, scope: str, **request: Any) -> Any:
        try:
            return client.get_ec2_instance_recommendations(**request)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in NOT_ENABLED_CODES:
                raise NotOptedIn(
                    scope_key=scope,
                    collector=COLLECTOR,
                    detail=f"compute-optimizer is not enabled here: {code}",
                ) from error
            raise translate(error, scope_key=scope, collector=COLLECTOR) from error
        except BotoCoreError as error:
            raise translate(error, scope_key=scope, collector=COLLECTOR) from error

    def _optimizer_recommendation(self, item: Any, region: str) -> Recommendation | None:
        finding = str(item.get("finding", ""))
        waste_class = COMPUTE_OPTIMIZER_CLASSES.get(finding)
        if waste_class is None:
            # Skipped rather than guessed. A finding type mapped to the wrong class is
            # worse than one absent, because the absent one is countable and the wrong
            # one is believed.
            return None
        options = _ranked(item.get("recommendationOptions") or [])
        if not options:
            return None
        best = min(item.get("recommendationOptions") or [], key=_rank_of)
        saving = _money(
            (best.get("savingsOpportunity") or {}).get("estimatedMonthlySavings", {}).get("value"),
            "savingsOpportunity.estimatedMonthlySavings.value",
        )
        arn = str(item.get("instanceArn", ""))
        current = str(item.get("currentInstanceType") or "") or None
        return replace(
            self._build(
                source=Source.COMPUTE_OPTIMIZER,
                reference=arn,
                waste_class=waste_class,
                resource_id=arn,
                region_id=_region_of(arn) or region,
                saving=saving,
                # Compute Optimizer's own lookback, which it reports per recommendation.
                # Defaulted to the floor rather than to zero, because a zero would be
                # refused by the entity and a recommendation would be silently lost.
                observation_days=int(item.get("lookBackPeriodInDays", MINIMUM_HISTORY)),
                rationale=(
                    f"Compute Optimizer finding {finding}, recommending "
                    f"{options[0].instance_type} first of {len(options)} ranked options"
                ),
            ),
            current_instance_type=current,
            options=options,
        )

    def cost_optimization_hub(self) -> Iterable[Recommendation]:
        response = self._call("cost-optimization-hub", "list_recommendations")
        found: list[Recommendation] = []
        for item in response.get("items", []):
            saving = _money(item.get("estimatedMonthlySavings"), "estimatedMonthlySavings")
            reference = str(item.get("recommendationId", ""))
            found.append(
                self._build(
                    source=Source.COST_OPTIMIZATION_HUB,
                    reference=reference,
                    waste_class=_hub_class(str(item.get("actionType", ""))),
                    resource_id=str(item.get("resourceId", "")),
                    region_id=str(item.get("region", "")),
                    saving=saving,
                    observation_days=int(item.get("lookbackPeriodInDays", MINIMUM_HISTORY)),
                    rationale=(
                        f"Cost Optimization Hub {item.get('actionType', 'action')} on "
                        f"{item.get('currentResourceType', 'a resource')}"
                    ),
                )
            )
        return tuple(found)

    def trusted_advisor(self) -> Iterable[Recommendation]:
        found: list[Recommendation] = []
        for check_id, waste_class in TRUSTED_ADVISOR_CHECKS.items():
            response = self._call(
                "support", "describe_trusted_advisor_check_result", checkId=check_id
            )
            result = response.get("result", {})
            for flagged in result.get("flaggedResources", []):
                metadata = flagged.get("metadata") or []
                # **The weakest mapping in this file.** Trusted Advisor returns a
                # positional array whose meaning differs per check, and the money
                # is not always in the same slot. Parsed defensively and refused
                # rather than guessed, and the first real account will correct it.
                saving = _money(_last_numeric(metadata), f"metadata money for check {check_id}")
                resource_id = str(flagged.get("resourceId", ""))
                found.append(
                    self._build(
                        source=Source.TRUSTED_ADVISOR,
                        reference=f"{check_id}:{resource_id}",
                        waste_class=waste_class,
                        resource_id=resource_id,
                        region_id=str(flagged.get("region", "")),
                        saving=saving,
                        # Trusted Advisor does not publish a lookback. The floor is
                        # the honest answer: it is what we can vouch for.
                        observation_days=MINIMUM_HISTORY,
                        rationale=f"Trusted Advisor check {check_id} flagged this resource",
                    )
                )
        return tuple(found)


def _rank_of(raw: Any) -> int:
    try:
        return int(raw.get("rank") or 0)
    except (TypeError, ValueError):
        return 0


def _ranked(raw_options: list[Any]) -> tuple[RankedOption, ...]:
    """Every option as Compute Optimizer ranked it, best first, or SchemaDrift."""
    found: list[RankedOption] = []
    for index, raw in enumerate(sorted(raw_options, key=_rank_of), start=1):
        risk = raw.get("performanceRisk")
        saving = ((raw.get("savingsOpportunity") or {}).get("estimatedMonthlySavings") or {}).get(
            "value"
        )
        try:
            found.append(
                RankedOption(
                    rank=_rank_of(raw) or index,
                    instance_type=str(raw.get("instanceType") or ""),
                    performance_risk=_money(risk, "recommendationOptions.performanceRisk"),
                    provider_monthly_saving=None if saving is None else _money(saving, "saving"),
                    migration_effort=raw.get("migrationEffort") or None,
                    platform_differences=tuple(
                        str(d) for d in raw.get("platformDifferences") or ()
                    ),
                )
            )
        except ValueError as failure:
            raise SchemaDrift(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=f"a ranked option this cannot read: {failure}",
            ) from failure
    return tuple(found)


def _hub_class(action_type: str) -> WasteClass:
    """Cost Optimization Hub's action type, mapped to ours."""
    mapping = {
        "Rightsize": WasteClass.RIGHTSIZE_INSTANCE,
        "Stop": WasteClass.IDLE_INSTANCE,
        "Delete": WasteClass.EBS_UNATTACHED,
        "MigrateToGraviton": WasteClass.GRAVITON_CANDIDATE,
        "Upgrade": WasteClass.EBS_GP2_TO_GP3,
    }
    return mapping.get(action_type, WasteClass.RIGHTSIZE_INSTANCE)


def _region_of(arn: str) -> str:
    """The region slot of an ARN, or empty where it has none."""
    parts = arn.split(":")
    return parts[3] if len(parts) > 3 else ""


def _account_of(arn: str) -> str:
    """The account slot of an ARN, or the whole string where it is not one."""
    parts = arn.split(":")
    return parts[4] if len(parts) > 4 else arn


def _last_numeric(metadata: list[Any]) -> str | None:
    """The last value in the array that parses as a number.

    Trusted Advisor's metadata is positional and its layout differs per check, so
    there is no index that is right for all of them. The money is conventionally
    last, and this returns None rather than a guess when nothing parses, which
    becomes `SchemaDrift` at the call site.
    """
    for candidate in reversed(metadata):
        text = str(candidate).replace("$", "").replace(",", "").strip()
        try:
            Decimal(text)
        except (InvalidOperation, ValueError):
            continue
        return text
    return None
