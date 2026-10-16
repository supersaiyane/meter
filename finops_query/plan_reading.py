"""A Terraform plan reduced to what sets its price. TASK-P16-002, FEAT-095, spec section 5.2.

`terraform show -json` writes every value Terraform knows about a change, the ones marked sensitive
included, in plain text, beside the prior state and the configuration. Meter keeps, per managed
resource change from the `hashicorp/aws` provider, the address, the type, the actions, the Region,
and the attributes pricing reads, before and after, with the names of those Terraform knows only
after apply. Everything else is dropped here, in memory, and never reaches a table. A priced
attribute its author marked sensitive is not kept either: it is named, and the line goes unpriced.

The Region is read, in order, from the resource's own `region` argument, which version 6 of the AWS
provider added, from its availability zone, and from the provider configuration the resource
names: a constant, or a root module variable the plan carries. None of these is a Region of None,
which the estimate reports, rather than a guess.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

_MIB: Final = 1024 * 1024
#: The largest plan read, modelled as ten times the largest plan Meter's own Terraform writes.
MAX_PLAN_BYTES: Final = 50 * _MIB
#: The `format_version` major version this reads.
FORMAT_MAJOR: Final = "1"
#: How the AWS provider's source address ends, on Terraform's registry or OpenTofu's.
AWS_SOURCE: Final = "/hashicorp/aws"
#: The actions that change what is billed. `no-op`, `read` and `forget` change nothing.
BILLED_ACTIONS: Final = frozenset({"create", "update", "delete"})

_VOLUME: Final = ("volume_type", "volume_size", "iops", "throughput")
_SEARCH: Final[Mapping[str, tuple[str, ...]]] = {
    "cluster_config": (
        "instance_type",
        "instance_count",
        "dedicated_master_enabled",
        "dedicated_master_type",
        "dedicated_master_count",
        "warm_enabled",
        "warm_type",
        "warm_count",
    ),
    "ebs_options": ("ebs_enabled", "volume_type", "volume_size", "iops", "throughput"),
}
#: Per type, the attributes pricing reads: a name with no inner names is a value, a name with them
#: is a block, of which only those are kept. A type not named here keeps its address, type, actions
#: and Region, so the estimate can say it is not priced, and nothing more.
PRICED: Final[Mapping[str, Mapping[str, tuple[str, ...]]]] = {
    "aws_instance": {
        "instance_type": (),
        "tenancy": (),
        "instance_market_options": ("market_type",),
        "root_block_device": _VOLUME,
        "ebs_block_device": _VOLUME,
    },
    "aws_ebs_volume": {"type": (), "size": (), "iops": (), "throughput": ()},
    "aws_db_instance": {
        "instance_class": (),
        "engine": (),
        "license_model": (),
        "multi_az": (),
        "allocated_storage": (),
        "storage_type": (),
        "iops": (),
        "storage_throughput": (),
    },
    "aws_rds_cluster_instance": {"instance_class": (), "engine": ()},
    "aws_elasticache_cluster": {
        "node_type": (),
        "num_cache_nodes": (),
        "engine": (),
        "replication_group_id": (),
    },
    "aws_elasticache_replication_group": {
        "node_type": (),
        "num_cache_clusters": (),
        "num_node_groups": (),
        "replicas_per_node_group": (),
        "engine": (),
    },
    "aws_redshift_cluster": {"node_type": (), "number_of_nodes": (), "cluster_type": ()},
    "aws_opensearch_domain": _SEARCH,
    "aws_elasticsearch_domain": _SEARCH,
}

_REGION: Final = re.compile(r"[a-z]{2}(?:-[a-z]+)+-\d+")
_ZONE: Final = re.compile(r"([a-z]{2}(?:-[a-z]+)+-\d+)[a-z]")
#: One module step of a resource's module address, with or without an instance key.
_MODULE_STEP: Final = re.compile(r'module\.([A-Za-z0-9_-]+)(?:\[(?:"(?:[^"\\]|\\.)*"|\d+)\])?')
_VARIABLE: Final = re.compile(r"var\.([A-Za-z0-9_-]+)")

Keys = Mapping[tuple[tuple[str, ...], str, str], str]


@dataclass(frozen=True)
class PlannedChange:
    """One resource change, as much of it as sets a price."""

    address: str
    resource_type: str
    actions: tuple[str, ...]
    region: str | None
    before: Mapping[str, Any]
    after: Mapping[str, Any]
    #: Priced attributes Terraform knows only after apply, such as `root_block_device[0].iops`.
    unknown: tuple[str, ...] = ()
    #: Priced attributes marked sensitive, which are named and never kept.
    withheld: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReducedPlan:
    """What is kept of a plan."""

    format_version: str
    terraform_version: str | None
    #: The plan's own timestamp, written by Terraform 1.5 and later.
    timestamp: datetime | None
    changes: tuple[PlannedChange, ...]


@dataclass(frozen=True)
class Unreadable:
    """A document that is not a plan Meter reads, and why."""

    reason: str


def reduce_plan(document: bytes) -> ReducedPlan | Unreadable:
    """The priced part of a plan as `terraform show -json` writes it, or why it cannot be read."""
    if len(document) > MAX_PLAN_BYTES:
        size = len(document) / _MIB
        return Unreadable(
            f"the plan is {size:.1f} MiB; Meter reads a plan up to {MAX_PLAN_BYTES // _MIB} MiB"
        )
    try:
        plan = json.loads(document)
    except json.JSONDecodeError as error:
        return Unreadable(f"the plan is not JSON: {error.msg} at line {error.lineno}")
    except (UnicodeDecodeError, RecursionError) as error:
        return Unreadable(f"the plan is not JSON Meter can read: {type(error).__name__}")
    refused = _refusal(plan)
    if refused is not None:
        return Unreadable(refused)
    configuration = plan.get("configuration")
    configuration = configuration if isinstance(configuration, Mapping) else {}
    keys = _provider_keys(configuration.get("root_module"), ())
    regions = _provider_regions(configuration.get("provider_config"), plan.get("variables"))
    changes: list[PlannedChange] = []
    for index, entry in enumerate(plan.get("resource_changes") or ()):
        malformed = _malformed(entry)
        if malformed is not None:
            return Unreadable(
                f"resource change {index} is not as Terraform writes one: {malformed}"
            )
        kept = _change(entry, keys, regions)
        if kept is not None:
            changes.append(kept)
    version = plan.get("terraform_version")
    return ReducedPlan(
        format_version=plan["format_version"],
        terraform_version=version if isinstance(version, str) else None,
        timestamp=_timestamp(plan.get("timestamp")),
        changes=tuple(changes),
    )


def _refusal(plan: Any) -> str | None:
    if not isinstance(plan, Mapping):
        return "the document is not a JSON object"
    version = plan.get("format_version")
    if not isinstance(version, str):
        return "it has no format_version, so it is not terraform show -json output"
    if version.split(".")[0] != FORMAT_MAJOR:
        return f"its format_version is {version}; Meter reads {FORMAT_MAJOR}.x"
    if "planned_values" not in plan and "resource_changes" not in plan:
        return "it is not a plan: it has neither planned_values nor resource_changes, as a state"
    if not isinstance(plan.get("resource_changes") or [], list):
        return "its resource_changes is not a list"
    return None


def _malformed(entry: Any) -> str | None:
    if not isinstance(entry, Mapping):
        return "not an object"
    for field in ("address", "mode", "type", "name"):
        if not isinstance(entry.get(field), str):
            return f"no {field}"
    change = entry.get("change")
    if not isinstance(change, Mapping):
        return "no change"
    actions = change.get("actions")
    if not isinstance(actions, list) or not all(isinstance(one, str) for one in actions):
        return "no actions"
    return None


def _change(
    entry: Mapping[str, Any], keys: Keys, regions: Mapping[str, str | None]
) -> PlannedChange | None:
    """The kept part of one resource change, or None for one that changes nothing billed."""
    if entry["mode"] != "managed" or not _aws(entry.get("provider_name")):
        return None
    change = entry["change"]
    actions = tuple(change["actions"])
    if not BILLED_ACTIONS.intersection(actions):
        return None
    wanted = PRICED.get(entry["type"], {})
    before, withheld_before = _kept(change.get("before"), change.get("before_sensitive"), wanted)
    after, withheld_after = _kept(change.get("after"), change.get("after_sensitive"), wanted)
    destroyed = actions == ("delete",)
    side = change.get("before") if destroyed else change.get("after")
    module = tuple(_MODULE_STEP.findall(str(entry.get("module_address") or "")))
    key = keys.get((module, entry["type"], entry["name"]))
    provider_region = regions[key] if key is not None and key in regions else _only(regions)
    return PlannedChange(
        address=entry["address"],
        resource_type=entry["type"],
        actions=actions,
        region=_region(side if isinstance(side, Mapping) else {}, provider_region),
        before=before,
        after=after,
        unknown=() if destroyed else _unknown(change.get("after_unknown"), wanted),
        withheld=tuple(dict.fromkeys(withheld_before + withheld_after)),
    )


def _aws(provider: Any) -> bool:
    return isinstance(provider, str) and provider.endswith(AWS_SOURCE)


def _kept(
    values: Any, sensitive: Any, wanted: Mapping[str, tuple[str, ...]]
) -> tuple[dict[str, Any], list[str]]:
    """One side's priced attributes, and the names withheld because they are marked sensitive."""
    if not isinstance(values, Mapping):
        return {}, []
    kept: dict[str, Any] = {}
    withheld: list[str] = []
    for name, inner in wanted.items():
        if name not in values:
            continue
        if _flag(sensitive, name):
            withheld.append(name)
            continue
        value = values[name]
        if not inner:
            if _scalar(value):
                kept[name] = value
            continue
        blocks: list[dict[str, Any]] = []
        for index, block in enumerate(_blocks(value)):
            one: dict[str, Any] = {}
            for part in inner:
                if _flag(sensitive, name, index, part):
                    withheld.append(f"{name}[{index}].{part}")
                elif part in block and _scalar(block[part]):
                    one[part] = block[part]
            blocks.append(one)
        kept[name] = blocks
    return kept, withheld


def _unknown(after_unknown: Any, wanted: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """The priced attributes Terraform knows only after apply."""
    found: list[str] = []
    for name, inner in wanted.items():
        if _flag(after_unknown, name):
            found.append(name)
            continue
        marks = after_unknown.get(name) if isinstance(after_unknown, Mapping) else None
        for index in range(len(marks)) if inner and isinstance(marks, list) else ():
            found.extend(f"{name}[{index}].{part}" for part in inner if _flag(marks, index, part))
    return tuple(found)


def _flag(marks: Any, *path: str | int) -> bool:
    """Whether a mark structure, `after_unknown` or a sensitivity, marks the value at `path`."""
    current = marks
    for step in path:
        if current is True:
            return True
        if not _holds(current, step):
            return False
        current = current[step]
    return current is True


def _holds(container: Any, step: str | int) -> bool:
    """Whether a step leads somewhere: a key of an object, or an index of a list."""
    if isinstance(step, str):
        return isinstance(container, Mapping) and step in container
    return isinstance(container, list) and step < len(container)


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _blocks(value: Any) -> list[Mapping[str, Any]]:
    """A nested block as a list, whether the provider writes it as a list or as one object."""
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [one for one in value if isinstance(one, Mapping)]
    return []


def _region(values: Mapping[str, Any], provider_region: str | None) -> str | None:
    own = values.get("region")
    if isinstance(own, str) and _REGION.fullmatch(own):
        return own
    zone = values.get("availability_zone")
    if isinstance(zone, str) and (match := _ZONE.fullmatch(zone)):
        return match.group(1)
    return provider_region


def _provider_keys(
    module: Any, path: tuple[str, ...]
) -> dict[tuple[tuple[str, ...], str, str], str]:
    """Each managed resource's provider configuration key, by its module path, type and name."""
    found: dict[tuple[tuple[str, ...], str, str], str] = {}
    if not isinstance(module, Mapping):
        return found
    for resource in module.get("resources") or ():
        if isinstance(resource, Mapping) and resource.get("mode") == "managed":
            key = resource.get("provider_config_key")
            if isinstance(key, str):
                found[(path, str(resource.get("type")), str(resource.get("name")))] = key
    calls = module.get("module_calls")
    for name, call in calls.items() if isinstance(calls, Mapping) else ():
        if isinstance(call, Mapping):
            found.update(_provider_keys(call.get("module"), (*path, name)))
    return found


def _provider_regions(providers: Any, variables: Any) -> dict[str, str | None]:
    """Each AWS provider configuration's Region, where its configuration gives one."""
    found: dict[str, str | None] = {}
    for key, provider in providers.items() if isinstance(providers, Mapping) else ():
        if isinstance(provider, Mapping) and provider.get("name") == "aws":
            # A variable is read only for a root module provider: the plan carries root variables.
            root = ":" not in key
            found[key] = _expression_region(
                provider.get("expressions"), variables if root else None
            )
    return found


def _expression_region(expressions: Any, variables: Any) -> str | None:
    region = expressions.get("region") if isinstance(expressions, Mapping) else None
    if not isinstance(region, Mapping):
        return None
    constant = region.get("constant_value")
    if isinstance(constant, str):
        return constant if _REGION.fullmatch(constant) else None
    references = region.get("references")
    if not isinstance(references, list) or len(references) != 1:
        return None
    named = _VARIABLE.fullmatch(str(references[0]))
    if named is None or not isinstance(variables, Mapping):
        return None
    variable = variables.get(named.group(1))
    value = variable.get("value") if isinstance(variable, Mapping) else None
    return value if isinstance(value, str) and _REGION.fullmatch(value) else None


def _only(regions: Mapping[str, str | None]) -> str | None:
    """With one AWS provider configuration in the plan, every AWS resource uses it."""
    return next(iter(regions.values())) if len(regions) == 1 else None


def _timestamp(value: Any) -> datetime | None:
    """The plan's timestamp. One that does not parse is treated as absent: the plan's arrival is
    then its `as_of`, which is later than the truth and never earlier."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
