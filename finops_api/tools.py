"""The tools, described once, for both of the things that call the API as somebody else.

A tool here is data: a name, the route it calls, and the envelope model that route
declares. The schema a caller sees is generated from that model rather than written out
again, so changing a field on the API changes the tool in the same edit, and a test holds
each entry against the route's own `response_model`.

**Why this table lives in the API package.** It used to live in `finops_mcp`, and P7 gave
it a second reader. The assistant's tools are the MCP tools, spec section 5.1, so the two
must read one table, and the assistant is composed inside the API process, which the
layer contract forbids from importing `finops_mcp`. The table describes the API's own
routes, so the API owning it is the natural direction, and `finops_mcp` still imports
nothing but this and the schemas: it stays a facade over the network, ADR-0009.

**Three fields only the assistant reads.** `provenance` is how a tool's figures were
arrived at where a row does not say itself, so a cited figure carries its flag. `units` is
what each of its numeric fields counts, dollars or a count, so a cited figure carries that
too and no screen reads a unit out of a field's name, ISS-231. `screen` is where a person
sees the same rows, so a refusal can point there.

There is deliberately no tool that runs free form SQL, and no tool that writes. See
ADR-0007 and constraint 6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from finops_api.schemas import (
    AccountOut,
    ContainerCostOut,
    CostSliceOut,
    CostSummaryOut,
    Envelope,
    FreshnessOut,
    MeOut,
    OrgNodeOut,
    PlatformCostOut,
    QueryFindingOut,
    RunOut,
)
from finops_core.domain.insight import Provenance, Unit
from finops_core.ports.llm import ToolSchema

API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class ToolSpec:
    """One tool. The envelope model is the single source of both schemas."""

    name: str
    path: str
    envelope: Any
    description: str
    #: What every numeric field under `data` counts, keyed by its path with any row selector
    #: taken out, such as `data.clusters.workloads.cost`. Required, and held by a test to
    #: exactly the numeric fields of the envelope, so a figure added without its unit fails
    #: in CI rather than reaching a screen as a guess. Nothing under `meta` is listed: every
    #: number there is a count, and the loop says so in one place.
    units: Mapping[str, Unit]
    #: How this tool's figures were arrived at, where a row carries no `provenance` of
    #: its own. A row that does say is believed over this.
    provenance: Provenance = Provenance.MEASURED
    #: The screen that shows the same rows, for a refusal to point at. None where no
    #: screen shows them.
    screen: str | None = None

    def output_schema(self) -> dict[str, Any]:
        """What a caller is told to expect, taken from the API's own model."""
        return dict(self.envelope.model_json_schema())

    def schema(self) -> ToolSchema:
        """The tool as a model is offered it. Every tool here takes no arguments."""
        return ToolSchema(name=self.name, description=self.description)


#: One row of a cost grouping, `CostSliceOut`, which the by service and by account tools share.
COST_SLICE_UNITS: Mapping[str, Unit] = {
    "data.billed_cost": Unit.USD,
    "data.effective_cost": Unit.USD,
    "data.line_items": Unit.COUNT,
}

#: The four the P0 spec names, `whoami`, the P2 findings list, and the four cost reads P7
#: added for the assistant. Two more that the P2 spec names are absent:
#: `get_dashboard_cost` needs a parameter, and a tool here is a parameterless GET, and
#: `get_query_accuracy` needs a calibration FEAT-018 has not published. ISS-148. `whoami` is
#: here because the first question a model asks about a partial answer is "what am I
#: allowed to see", and without it the only way to find out is to infer it from a coverage
#: fraction, which is guessing.
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="list_accounts",
        path=f"{API_PREFIX}/accounts",
        envelope=Envelope[list[AccountOut]],
        description=(
            "Cloud accounts the caller is entitled to see, with the health of the "
            "role Meter reads them through. Check meta.scope_coverage before "
            "describing this as the whole organization: it is the number in scope "
            "over the number that exist, and it is frequently not one."
        ),
        units={},
    ),
    ToolSpec(
        name="get_org_tree",
        path=f"{API_PREFIX}/org/tree",
        envelope=Envelope[list[OrgNodeOut]],
        description=(
            "The organization tree. Nodes outside the caller's scope are present "
            "with reachable=false rather than hidden, so the shape of the "
            "organization is honest. Do not report a figure against an "
            "unreachable node."
        ),
        units={"data.depth": Unit.COUNT},
    ),
    ToolSpec(
        name="get_ingest_status",
        path=f"{API_PREFIX}/ingest/runs",
        envelope=Envelope[list[RunOut]],
        description=(
            "Recent collection runs with typed failure causes. error_type is one "
            "of a closed set: AccessDenied, Throttled, NotOptedIn, NoData, "
            "Timeout, Unknown. A failed run means a number is missing, which is "
            "not the same as a number being zero."
        ),
        units={"data.items_written": Unit.COUNT},
        screen="/platform/ingest",
    ),
    ToolSpec(
        name="get_platform_cost",
        path=f"{API_PREFIX}/platform/cost",
        envelope=Envelope[list[PlatformCostOut]],
        description=(
            "What Meter itself costs to run, by module and service. Cost that "
            "carries no module tag is reported under 'unallocated' rather than "
            "dropped, so the total reconciles with the bill."
        ),
        units={"data.amortized_cost": Unit.USD},
        screen="/platform/cost",
    ),
    ToolSpec(
        name="get_freshness",
        path=f"{API_PREFIX}/health/freshness",
        envelope=Envelope[list[FreshnessOut]],
        description=(
            "How old each collector's data is, against the cadence it is "
            "supposed to run at. Use this before quoting any figure as current."
        ),
        units={"data.age_seconds": Unit.COUNT, "data.cadence_seconds": Unit.COUNT},
        screen="/platform/freshness",
    ),
    ToolSpec(
        name="list_expensive_queries",
        path=f"{API_PREFIX}/query/findings",
        envelope=Envelope[list[QueryFindingOut]],
        description=(
            "Saved queries ranked by what they cost each month, most expensive "
            "first. Read `provenance` before quoting any figure: `modelled` "
            "rests on an assumed log ingestion rate that can be an order of "
            "magnitude out, and `measured` is what the account actually did. "
            "`owner` is null when nothing could attribute the query, which "
            "means unowned rather than owned by nobody in particular, and "
            "`why` is the sentence that says what drives the cost."
        ),
        units={
            "data.history.cost_month_usd": Unit.USD,
            "data.monthly_cost": Unit.USD,
            "data.measured_runs": Unit.COUNT,
            "data.refresh_seconds": Unit.COUNT,
            "data.runs_per_day": Unit.COUNT,
            "data.scan_bytes_per_run": Unit.COUNT,
            "data.window_seconds": Unit.COUNT,
        },
    ),
    ToolSpec(
        name="whoami",
        path=f"{API_PREFIX}/me",
        envelope=Envelope[MeOut],
        description=(
            "The caller's identity, tier and how many accounts are in their "
            "scope. Ask this first when an answer looks smaller than expected."
        ),
        units={"data.accounts_in_scope": Unit.COUNT},
    ),
    ToolSpec(
        name="get_cost_summary",
        path=f"{API_PREFIX}/cost/summary",
        envelope=Envelope[CostSummaryOut],
        description=(
            "The latest billing period's spend and the one before it, with the change "
            "between them. `change` is null when there is no previous period, which is "
            "not a change of zero."
        ),
        units={
            # This period's effective cost less the last one's, `finops_api/routes/cost.py`, so
            # a difference in dollars and never a percentage.
            "data.change": Unit.USD,
            "data.current.billed_cost": Unit.USD,
            "data.current.effective_cost": Unit.USD,
            "data.current.line_items": Unit.COUNT,
            "data.previous.billed_cost": Unit.USD,
            "data.previous.effective_cost": Unit.USD,
            "data.previous.line_items": Unit.COUNT,
        },
        screen="/cost",
    ),
    ToolSpec(
        name="get_cost_by_service",
        path=f"{API_PREFIX}/cost/by-service",
        envelope=Envelope[list[CostSliceOut]],
        description=(
            "The latest billing period's cost by service, worst first, one row per "
            "service named in `name`. `effective_cost` is after discounts and is the "
            "figure to quote. A row named `unallocated` is cost the bill gives no "
            "service for, never dropped and never folded into another."
        ),
        units=COST_SLICE_UNITS,
        screen="/cost",
    ),
    ToolSpec(
        name="get_cost_by_account",
        path=f"{API_PREFIX}/cost/by-account",
        envelope=Envelope[list[CostSliceOut]],
        description=(
            "The latest billing period's cost by account, worst first, one row per "
            "account id in `name`, and only the accounts the caller may see. "
            "meta.scope_coverage says how many of the organization's accounts that is."
        ),
        units=COST_SLICE_UNITS,
        screen="/cost",
    ),
    ToolSpec(
        name="get_container_cost",
        path=f"{API_PREFIX}/cost/containers",
        envelope=Envelope[ContainerCostOut],
        description=(
            "Cost by cluster, namespace and workload, measured from split cost "
            "allocation data on the bill. `unallocated` is capacity no workload "
            "requested. A cluster without a breakdown says why in "
            "`unmeasurable_reason`, and an export without the data at all reports "
            "that in meta.failures."
        ),
        units={
            "data.clusters.allocated": Unit.USD,
            "data.clusters.total": Unit.USD,
            "data.clusters.unallocated": Unit.USD,
            "data.clusters.workloads.cost": Unit.USD,
            "data.clusters.workloads.line_items": Unit.COUNT,
            "data.found_count": Unit.COUNT,
            "data.measured_count": Unit.COUNT,
        },
        screen="/cost/containers",
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOLS}
