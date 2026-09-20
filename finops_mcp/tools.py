"""The tools, described once.

A tool here is data: a name, the route it calls, and the envelope model that
route declares. The schema a model sees is generated from that model rather than
written out again, so changing a field on the API changes the tool in the same
edit. A test holds each entry against the route's own `response_model`, which is
what turns a divergence into a build failure instead of a support ticket.

There is deliberately no tool that runs free form SQL, and no tool that writes.
See ADR-0007 and constraint 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finops_api.schemas import (
    AccountOut,
    Envelope,
    FreshnessOut,
    MeOut,
    OrgNodeOut,
    PlatformCostOut,
    QueryFindingOut,
    RunOut,
)

API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class ToolSpec:
    """One tool. The envelope model is the single source of both schemas."""

    name: str
    path: str
    envelope: Any
    description: str

    def output_schema(self) -> dict[str, Any]:
        """What the model is told to expect, taken from the API's own model."""
        return dict(self.envelope.model_json_schema())


#: The four the P0 spec names, `whoami`, and the P2 findings list. Two more
#: that the P2 spec names are absent: `get_dashboard_cost` needs a parameter,
#: and a tool here is a parameterless GET, and `get_query_accuracy` needs a
#: calibration FEAT-018 has not published. ISS-148. `whoami` is here because the first
#: question a model asks about a partial answer is "what am I allowed to see",
#: and without it the only way to find out is to infer it from a coverage
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
    ),
    ToolSpec(
        name="get_freshness",
        path=f"{API_PREFIX}/health/freshness",
        envelope=Envelope[list[FreshnessOut]],
        description=(
            "How old each collector's data is, against the cadence it is "
            "supposed to run at. Use this before quoting any figure as current."
        ),
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
    ),
    ToolSpec(
        name="whoami",
        path=f"{API_PREFIX}/me",
        envelope=Envelope[MeOut],
        description=(
            "The caller's identity, tier and how many accounts are in their "
            "scope. Ask this first when an answer looks smaller than expected."
        ),
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOLS}
