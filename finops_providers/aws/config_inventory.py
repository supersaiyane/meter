"""Resources and relationships from an organization Config aggregator.

**Nothing in this file has ever made a call.** ISS-200. Every shape below is read
from the AWS Config advanced query documentation and from nothing else, and the
tests exercise a client that answers from a literal.

**The mappings least likely to be right.** Two tables here turn provider strings
into closed sets, and both are the part a first real call will correct.

`KIND_OF` has fourteen members to spend and the estate has more kinds of thing
than that. A type it cannot name is `OTHER` and is listed in `SliceRead.unmapped`,
which is **not** a shortfall: the node is present with its `resource_type` intact,
so the slice is complete and only its labelling is imprecise. Making it a shortfall
was the first draft, and the contract suite caught what that costs, because an
estate with a fleet of EKS clusters would then be PARTIAL on every run forever.

`AWS::EKS::Cluster`, `AWS::ECS::Cluster`,
`AWS::ElastiCache::CacheCluster`, `AWS::MSK::Cluster`, `AWS::EC2::TransitGateway`,
`AWS::EC2::VPCPeeringConnection`, `AWS::EC2::VPCEndpointService` and
`AWS::IAM::Role` all land on `OTHER`, which means four of the most expensive
things in a real estate draw as an unlabelled box. `resource_type` is stored
beside `node_kind` so a screen can still name them, and ISS-201 records the gap
rather than widening an enumeration the specification fixed and a check
constraint holds.

`GLOBAL_TYPES` decides which resources belong to the account's global slice
rather than to a region, and it decides it by type because Config records a global
resource under whichever region had global recording enabled. Filtering on
`awsRegion` instead would put an IAM role in eu-west-1, and a type added to AWS and
not added here reads as a regional resource of whatever region it was recorded in.

`RELATIONSHIPS` maps Config's prose relationship names, and the prose is the
problem: `Is contained in Vpc` and `Contains Subnet` are the same fact reported
from the two ends, `Is associated with RouteTable` and `Is attached to
NetworkInterface` are different words for one edge kind, and a name outside the
table is a `SchemaDrift` shortfall rather than a guess.

**An inward relationship whose origin is outside this slice is not emitted, and
that is not a dropped edge.** Config reports a relationship from both ends, so
the edge belongs to the origin's own slice and that slice's aggregator query
supplies it. If that slice is unreadable, the edge is genuinely unknown and its
own `graph_coverage` row says so, which is section 6 working rather than being
worked around. The alternative, emitting the edge from a node this slice never
read, would violate the `from_node_id` key for a fact this slice cannot vouch
for.

**Nothing here raises for a partial read.** `read_slice` returns a `SliceRead`
whose `shortfalls` name the APIs that refused. An exception carries one cause and
discards every node already read, and a slice where the aggregator answered for
most of an account and refused one call is worth what it answered plus a row
saying what is missing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey
from finops_core.domain.topology import (
    CoverageCause,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Shortfall,
    SliceRead,
    node_id_for,
)
from finops_core.errors import CollectionError, Throttled
from finops_providers.aws.client import translate

COLLECTOR = "inventory"

#: The value every edge from a Config relationship carries, so a reader can tell
#: which edges in the table depend on this file. Named by the P4 specification.
CONFIG_RELATIONSHIP = "CONFIG_RELATIONSHIP"

#: The aggregator query, and the reason it is a constant. Config's advanced query
#: language rejects a `SELECT` of a column it does not know by failing the whole
#: call rather than omitting the column, so this is exercised as a literal by the
#: tests rather than assembled per call.
SELECT = (
    "SELECT accountId, awsRegion, resourceType, resourceId, resourceName, arn, "
    "availabilityZone, tags, configurationItemCaptureTime, relationships"
)

#: Rows per page. The API caps a page at 100 and refuses more, so this is the cap
#: rather than a preference: a larger number is a validation failure on the first
#: call in a real account, which is the failure a literal here prevents.
PAGE_SIZE = 100

#: Seconds before the first retry of a throttled page, doubled per attempt. The
#: same shape `accounts.py` uses, because the aggregator is throttled per payer and
#: a tight retry across three hundred accounts throttles harder.
THROTTLE_BACKOFF_BASE_SECONDS = 1.0

#: The resource types that belong to an account and to no region, which is what
#: the account's global slice holds. Named as a set rather than inferred from
#: `awsRegion`, and this is the third thing a first real call is most likely to
#: correct: Config records a global resource under whichever region had global
#: recording enabled, so `awsRegion` is a recording detail rather than a fact about
#: the resource, and filtering on it would put an IAM role in eu-west-1.
#:
#: The two slice queries partition the account between them. The global slice asks
#: for these types and the regional slice asks for everything else in one region, so
#: no resource is read twice and none is missed. A type added to AWS and not added
#: here would be read as a regional resource of whichever region Config recorded it
#: in, which is wrong and visible rather than wrong and absent.
GLOBAL_TYPES: frozenset[str] = frozenset(
    {
        "AWS::IAM::Role",
        "AWS::IAM::Policy",
        "AWS::IAM::User",
        "AWS::IAM::Group",
        "AWS::IAM::InstanceProfile",
        "AWS::CloudFront::Distribution",
        "AWS::Route53::HostedZone",
        "AWS::WAF::WebACL",
    }
)

#: Provider resource type to the fourteen kinds the schema admits. See the module
#: docstring for what this cannot express. Anything absent is `OTHER` plus a
#: `SchemaDrift` shortfall, so an unfamiliar type is in the graph and loud rather
#: than missing and quiet.
KIND_OF: Mapping[str, NodeKind] = {
    "AWS::EC2::VPC": NodeKind.VPC,
    "AWS::EC2::Subnet": NodeKind.SUBNET,
    "AWS::EC2::Instance": NodeKind.INSTANCE,
    "AWS::EC2::NetworkInterface": NodeKind.ENI,
    "AWS::EC2::SecurityGroup": NodeKind.SECURITY_GROUP,
    "AWS::ElasticLoadBalancingV2::TargetGroup": NodeKind.TARGET_GROUP,
    "AWS::ElasticLoadBalancingV2::LoadBalancer": NodeKind.LOAD_BALANCER,
    "AWS::ElasticLoadBalancing::LoadBalancer": NodeKind.LOAD_BALANCER,
    "AWS::EC2::NatGateway": NodeKind.NAT_GATEWAY,
    "AWS::EC2::TransitGatewayAttachment": NodeKind.TGW_ATTACHMENT,
    "AWS::EC2::VPCEndpoint": NodeKind.VPC_ENDPOINT,
    "AWS::EC2::Volume": NodeKind.VOLUME,
    "AWS::RDS::DBInstance": NodeKind.DB_INSTANCE,
    "AWS::Lambda::Function": NodeKind.FUNCTION,
}


@dataclass(frozen=True)
class _Relation:
    """An edge kind, and which end of the prose the origin is."""

    kind: EdgeKind
    #: True where the relationship reads inward, so the origin is the far end.
    #: `Is contained in Vpc` on a subnet is the VPC containing the subnet.
    inward: bool


#: Config's relationship prose, by the prefix a name starts with. Prefixes rather
#: than whole names because a name ends in the other resource's type, which is open
#: ended: `Contains Subnet`, `Contains NetworkInterface`. Matched longest first, so
#: `Is contained in` is never matched by a shorter key.
RELATIONSHIPS: Mapping[str, _Relation] = {
    "Contains": _Relation(EdgeKind.CONTAINS, inward=False),
    "Is contained in": _Relation(EdgeKind.CONTAINS, inward=True),
    "Is attached to": _Relation(EdgeKind.ATTACHED_TO, inward=False),
    "Is associated with": _Relation(EdgeKind.ATTACHED_TO, inward=False),
    "Is part of": _Relation(EdgeKind.CONTAINS, inward=True),
    "Routes to": _Relation(EdgeKind.ROUTES_TO, inward=False),
}

Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def _tags(raw: Any) -> dict[str, str]:
    """Config returns tags as a list of key and value pairs, not a mapping."""
    if not isinstance(raw, list):
        return {}
    found: dict[str, str] = {}
    for entry in raw:
        if isinstance(entry, dict) and "key" in entry:
            found[str(entry["key"])] = str(entry.get("value", ""))
    return found


def _captured_at(raw: Any) -> datetime | None:
    """When Config saw the resource, or None if it did not say.

    None rather than the current time. `as_of` is when the value was true at the
    source, so substituting our own clock would make a configuration item from
    months ago read as one from this morning, which is the exact confusion
    constraint 10 splits the two timestamps to prevent.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _match(name: str) -> _Relation | None:
    """The relation a Config relationship name means, or None for an unknown one."""
    for prefix in sorted(RELATIONSHIPS, key=len, reverse=True):
        if name.startswith(prefix):
            return RELATIONSHIPS[prefix]
    return None


def _decode(raw: Any) -> Mapping[str, Any] | None:
    """One result, which the API returns as a JSON string rather than an object.

    A result that does not parse is skipped rather than raised on. One malformed row
    in a page of a hundred should not discard the ninety nine, and the caller still
    learns something was unmappable from the SchemaDrift shortfall.
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class ConfigAggregatorInventory:
    """One aggregator query per slice, paginated, with a bounded retry.

    Unproved, ISS-200. The aggregator lives in the payer account, so this holds one
    client rather than one per member account: that is the whole reason FEAT-030
    reads Config through an aggregator instead of assuming a role three hundred
    times.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any,
        aggregator_name: str,
        tenant_id: Any,
        enrolled: tuple[tuple[AccountKey, str | None], ...],
        clock: Clock = _system_clock,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._aggregator = aggregator_name
        self._tenant_id = tenant_id
        self._enrolled = enrolled
        self._clock = clock
        # Injected so a test does not wait out a backoff. Imported here rather than
        # at module scope so nothing pulls `time` into the import graph of a module
        # the determinism check walks.
        if sleeper is None:
            import time

            sleeper = time.sleep
        self._sleeper = sleeper

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        """Every slice this source is expected to read, from configuration.

        Handed in rather than discovered, because the set of slices that should be
        readable cannot be derived from the set that was readable without already
        knowing the answer to the question TASK-P4-005 exists to ask.
        """
        return self._enrolled

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        """One account and region of the graph, with what was missed named.

        Does not raise for a refusal. See the module docstring.
        """
        at = self._clock()
        scope_key = f"acct:{account.account_id}"
        nodes: list[Node] = []
        relations: list[tuple[str, str, _Relation]] = []
        shortfalls: list[Shortfall] = []
        unfamiliar_types: set[str] = set()
        unfamiliar_relationships: set[str] = set()
        undated: set[str] = set()

        try:
            for item in self._pages(account, region, scope_key):
                node = self._node(item, account, at)
                if node is None:
                    # No capture time or no identifier, so `as_of` or the row's
                    # identity would have to be invented. Dropped and named, because
                    # a fact whose as_of we chose is a stale number wearing a fresh
                    # timestamp.
                    undated.add(str(item.get("resourceType") or "unknown"))
                    continue
                if node.node_kind is NodeKind.OTHER:
                    unfamiliar_types.add(node.resource_type)
                nodes.append(node)
                relations.extend(self._relations(item, unfamiliar_relationships))
        except CollectionError as failure:
            # The aggregator itself refused, so this slice has no nodes at all. Still
            # a SliceRead: the caller writes a PARTIAL row and moves to the next
            # account, which is constraint 5.
            return SliceRead(
                account_key=account,
                region_id=region,
                nodes=(),
                edges=(),
                shortfalls=(
                    Shortfall(
                        source="config:SelectAggregateResourceConfig",
                        cause=CoverageCause(failure.cause),
                        detail=failure.detail,
                    ),
                ),
            )

        if undated:
            shortfalls.append(
                Shortfall(
                    source="config:SelectAggregateResourceConfig",
                    cause=CoverageCause.SCHEMA_DRIFT,
                    detail=(
                        "resources with no capture time or no identifier, omitted: "
                        + ", ".join(sorted(undated))
                    ),
                )
            )
        if unfamiliar_relationships:
            shortfalls.append(
                Shortfall(
                    source=CONFIG_RELATIONSHIP,
                    cause=CoverageCause.SCHEMA_DRIFT,
                    detail=(
                        "relationship names this adapter does not map: "
                        + ", ".join(sorted(unfamiliar_relationships))
                    ),
                )
            )

        return SliceRead(
            account_key=account,
            region_id=region,
            nodes=tuple(nodes),
            edges=self._edges(nodes, relations, at),
            shortfalls=tuple(shortfalls),
            # Reported, and deliberately not a shortfall. The nodes are there as
            # OTHER with their `resource_type` intact, so the slice is complete and
            # only its labelling is imprecise. See `SliceRead.unmapped` and ISS-201.
            unmapped=tuple(sorted(unfamiliar_types)),
        )

    # -- turning one configuration item into a node ------------------------

    def _node(self, item: Mapping[str, Any], account: AccountKey, at: datetime) -> Node | None:
        as_of = _captured_at(item.get("configurationItemCaptureTime"))
        provider_id = str(item.get("arn") or item.get("resourceId") or "")
        resource_type = str(item.get("resourceType", ""))
        if as_of is None or not provider_id:
            return None
        # A global type has no region, whatever region Config recorded it under. The
        # recording region is a fact about our own configuration, and storing it here
        # would put an IAM role on the map in eu-west-1.
        region = None if resource_type in GLOBAL_TYPES else item.get("awsRegion")
        zone = item.get("availabilityZone")
        return Node(
            node_id=node_id_for(tenant_id=self._tenant_id, provider_id=provider_id),
            account_key=account,
            provider_id=provider_id,
            node_kind=KIND_OF.get(resource_type, NodeKind.OTHER),
            resource_type=resource_type,
            region_id=str(region) if region else None,
            # A zone Config did not give is a regional resource, which is what the
            # null means. A zone it gave for a resource with no region at all is
            # dropped, because the schema refuses that pair and it cannot be true.
            availability_zone=str(zone) if zone and region else None,
            name=str(item["resourceName"]) if item.get("resourceName") else None,
            tags=_tags(item.get("tags")),
            as_of=as_of,
            collected_at=at,
        )

    def _relations(
        self, item: Mapping[str, Any], unfamiliar: set[str]
    ) -> Iterator[tuple[str, str, _Relation]]:
        """Each relationship as origin, target and kind, in reading order."""
        mine = str(item.get("arn") or item.get("resourceId") or "")
        raw = item.get("relationships")
        if not mine or not isinstance(raw, list):
            return
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            theirs = str(entry.get("resourceId") or "")
            name = str(entry.get("relationshipName") or "")
            if not theirs or not name:
                continue
            relation = _match(name)
            if relation is None:
                unfamiliar.add(name)
                continue
            if relation.inward:
                yield theirs, mine, relation
            else:
                yield mine, theirs, relation

    def _edges(
        self,
        nodes: list[Node],
        relations: list[tuple[str, str, _Relation]],
        at: datetime,
    ) -> tuple[Edge, ...]:
        """Relationships as edges, keeping only those this slice can vouch for.

        An origin outside the slice is skipped, and the module docstring says why
        that is not a dropped edge: Config reports the relationship from both ends,
        so it belongs to the origin's own slice, whose coverage row answers for it.
        """
        by_provider_id = {node.provider_id: node for node in nodes}
        found: dict[tuple[str, str, EdgeKind], Edge] = {}
        for origin, target, relation in relations:
            source_node = by_provider_id.get(origin)
            if source_node is None:
                continue
            if origin == target:
                # A relationship from a resource to itself. Config reports one for a
                # security group under a name that maps to ATTACHED_TO, which the
                # check constraint refuses, so it is skipped here rather than left to
                # fail the whole unit at the database. The reflexive PERMITS edge that
                # a self referencing group really does have comes from
                # `finops_providers/aws/topology.py`, which reads the group's rules.
                continue
            key = (origin, target, relation.kind)
            if key in found:
                # Config reports the same pair twice where two relationship names map
                # to one kind. The unique index would refuse the second, so the
                # collector never sees it.
                continue
            far = by_provider_id.get(target)
            found[key] = Edge(
                from_node_id=source_node.node_id,
                to_node_id=node_id_for(tenant_id=self._tenant_id, provider_id=target),
                edge_kind=relation.kind,
                # True where the far end is outside this slice's nodes, because a
                # slice is one account: a target this account did not report is in
                # another one. Set here, at write time, not computed on read.
                is_cross_account=(
                    far.account_key != source_node.account_key if far is not None else True
                ),
                source=CONFIG_RELATIONSHIP,
                # The relationship was true when the configuration item was captured,
                # which is the origin's `as_of` and not the clock.
                as_of=source_node.as_of,
                collected_at=at,
            )
        return tuple(found.values())

    # -- calling the provider ----------------------------------------------

    def _pages(
        self, account: AccountKey, region: str | None, scope_key: str
    ) -> Iterator[Mapping[str, Any]]:
        """Every page, always. There is no unpaginated path through this class.

        An unpaginated call does not fail: it returns the first hundred resources in
        the account and a graph that is quietly a hundredth of the estate.
        """
        expression = f"{SELECT} WHERE accountId = '{account.account_id}'"
        listed = ", ".join(f"'{name}'" for name in sorted(GLOBAL_TYPES))
        if region is None:
            expression += f" AND resourceType IN ({listed})"
        else:
            # Both halves. Without the region the global slice's own resources would
            # be read again here, once per region, and the same IAM role would arrive
            # as eleven nodes with eleven different regions and one identifier.
            expression += f" AND awsRegion = '{region}' AND resourceType NOT IN ({listed})"
        token: str | None = None
        attempt = 0
        while True:
            request: dict[str, Any] = {
                "ConfigurationAggregatorName": self._aggregator,
                "Expression": expression,
                "Limit": PAGE_SIZE,
            }
            if token is not None:
                request["NextToken"] = token
            try:
                page = self._client.select_aggregate_resource_config(**request)
            except (ClientError, BotoCoreError) as failure:
                typed = translate(failure, scope_key=scope_key, collector=COLLECTOR)
                if not isinstance(typed, Throttled) or attempt >= self._settings.aws_max_retries:
                    raise typed from failure
                self._sleeper(THROTTLE_BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1
                continue
            # Reset per page rather than per call. A run of two hundred pages that is
            # throttled on every tenth one is healthy, and a counter that never reset
            # would fail it on the tenth throttle rather than the tenth consecutive
            # one.
            attempt = 0
            for raw in page.get("Results", []):
                decoded = _decode(raw)
                if decoded is not None:
                    yield decoded
            token = page.get("NextToken")
            if not token:
                return
