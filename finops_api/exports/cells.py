"""What goes in a cell, and what its column is called. FEAT-067, TASK-P8-009.

An export is the view's own rows, so a row is the route's own row model, flattened: the fields
of a nested model become columns of their own, named for what they hold. A list or a mapping
inside a row, a sparkline's history or a finding's evidence, is not a cell and is left out,
because a cell holding a list is a string nobody can sort or sum.
"""

from __future__ import annotations

import re
import types
from collections import abc
from collections.abc import Mapping
from enum import Enum
from typing import Any, Final, Union, get_args, get_origin

from pydantic import BaseModel

#: The FOCUS display name of every column that has one. A column without one is named in its
#: own words, which is what the screen calls it too.
FOCUS_NAMES: Final[Mapping[str, str]] = {
    "effective_cost": "Effective Cost",
    "billed_cost": "Billed Cost",
    "list_cost": "List Cost",
    "contracted_cost": "Contracted Cost",
    "sub_account_id": "Sub Account ID",
    "account_id": "Sub Account ID",
    "region_id": "Region ID",
    "service_name": "Service Name",
    "service_category": "Service Category",
    "charge_category": "Charge Category",
    "availability_zone": "Availability Zone",
    "commitment_discount_type": "Commitment Discount Type",
    "commitment_discount_status": "Commitment Discount Status",
    "billing_period_start": "Billing Period Start",
    "charge_period_start": "Charge Period Start",
    "resource_id": "Resource ID",
    "resource_name": "Resource Name",
    "as_of": "As of",
    "collected_at": "Collected at",
}

#: Every collector by the name a reader knows it by: the web's `COLLECTOR_NAMES`, which
#: `tests/api/test_export_names.py` holds equal to this. A failure on the About sheet is
#: named the way the screens name it, because ISS-246 was these codes on every screen.
COLLECTOR_NAMES: Final[Mapping[str, str]] = {
    "account_health": "Account health",
    "budgets": "Budgets",
    "commitment": "Commitments",
    "commitment_actions": "Commitment actions",
    "container_usage": "Kubernetes usage",
    "cost_anomaly": "Cost anomalies",
    "cost_focus": "Cost and usage (FOCUS)",
    "finops_score": "FinOps Score",
    "iac_state": "Infrastructure as code state",
    "inventory": "Resource inventory",
    "org_tree": "Organization",
    "partition_maintenance": "Partition maintenance",
    "platform_cost": "Meter Cost",
    "query_audit": "Query audit",
    "query_evidence": "Query evidence",
    "quotas": "Service quotas",
    "realized_savings": "Realized Savings",
    "recommendations": "Recommendations",
    "retention_audit": "Retention, audit records",
    "retention_cost": "Retention, cost records",
    "retention_operational": "Retention, operational records",
    "retention_principal": "Retention, personal records",
    "retention_scope_cache": "Retention, scope cache",
    "team_digests": "Team digests",
    "waste_cloudwatch": "CloudWatch waste",
    "waste_compute": "Compute waste",
    "waste_parking": "Off hours scheduling",
}

#: Annotations that hold many values, and are therefore not one cell.
_COLLECTIONS: Final[tuple[Any, ...]] = (
    list,
    tuple,
    set,
    frozenset,
    dict,
    abc.Sequence,
    abc.Mapping,
    abc.Set,
    abc.Iterable,
)


def columns_of(model: type[BaseModel], prefix: str = "") -> list[str]:
    """Every cell a row of `model` has, by dotted path, in the order the model declares them."""
    fields: dict[str, Any] = {
        name: info.annotation for name, info in model.model_fields.items() if not info.exclude
    }
    for name, computed in model.model_computed_fields.items():
        fields[name] = computed.return_type
    columns: list[str] = []
    for name, annotation in fields.items():
        path = f"{prefix}{name}"
        nested = _model_in(annotation)
        if nested is not None:
            columns.extend(columns_of(nested, f"{path}."))
        elif not _is_collection(annotation):
            columns.append(path)
    return columns


def flatten(row: BaseModel) -> dict[str, object]:
    """A row's values by the same dotted paths `columns_of` names."""
    found: dict[str, object] = {}
    _walk(row.model_dump(mode="python"), "", found)
    return found


def header(path: str, names: Mapping[str, str] | None = None) -> str:
    """A column's heading: the route's own name for it, its FOCUS name, or its own words."""
    if names is not None and path in names:
        return names[path]
    words = " ".join(FOCUS_NAMES.get(part, part.replace("_", " ")) for part in path.split("."))
    return words[:1].upper() + words[1:]


def text_of(value: object) -> str:
    """A text cell's words: an enum by its value, anything else as Python spells it."""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def in_words(code: str) -> str:
    """A code nobody named, in words rather than as a code: the web's `inWords`."""
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", code)
    words = re.sub(r"[_-]+", " ", words).strip().lower()
    return words[:1].upper() + words[1:]


def collector_name(code: str) -> str:
    """A collector by its name, or its code in words where it has none yet."""
    return COLLECTOR_NAMES.get(code) or in_words(code)


def _walk(value: object, path: str, found: dict[str, object]) -> None:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            _walk(inner, f"{path}.{key}" if path else str(key), found)
    elif not isinstance(value, list | tuple | set | frozenset):
        found[path] = value


def _model_in(annotation: Any) -> type[BaseModel] | None:
    """The model an annotation holds, directly or as an optional."""
    if (
        isinstance(annotation, type)
        and not isinstance(annotation, types.GenericAlias)
        and issubclass(annotation, BaseModel)
    ):
        return annotation
    if get_origin(annotation) in (Union, types.UnionType):
        for argument in get_args(annotation):
            found = _model_in(argument)
            if found is not None:
                return found
    return None


def _is_collection(annotation: Any) -> bool:
    if annotation in _COLLECTIONS or get_origin(annotation) in _COLLECTIONS:
        return True
    if get_origin(annotation) in (Union, types.UnionType):
        return any(
            _is_collection(argument)
            for argument in get_args(annotation)
            if argument is not type(None)
        )
    return False
