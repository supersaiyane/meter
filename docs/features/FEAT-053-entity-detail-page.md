# FEAT-053: One resource, and everything we know about it

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Delivered |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), 2026-09-26 section |
| Tasks | None. Small enough to land as one change, on the owner's decision of 2026-09-26 |
| Refresh cadence | Follows the collectors behind it. The page owns no collector |
| Source | Adopted from the IBM Turbonomic review on 2026-09-26 |

## What it does

`GET /api/v1/inventory/nodes/{node_id}` and a screen at `/inventory/resources/:nodeId`
answering five questions about one resource: what it is, where it is, what it cost, what is
wrong with it, and what it is attached to.

Reached from the topology map, where every resource on the picture is now a link.

## Why it exists

Every list in the product pointed nowhere. A reader who found an oversized instance on the
waste screen, a VPC on the map or a spike on the anomalies screen had no page to open, so the
next question after "what is wrong" had no answer anywhere in the interface.

The Turbonomic review recorded the entity detail view as the thing their Supply Chain drills
into, and it was the second of the two gaps cheap enough to close with what already existed:
the cost repository, the topology repository and the recommendation serialiser each already
answered one fifth of this page.

## What is already known

**Two of the five sections are admissions rather than facts, and both are load bearing.**

The coverage banner. This resource came out of a slice, and a slice that was not read whole
yields a neighbour list that is short for a reason that has nothing to do with the resource.
The banner sits above the list for the same reason the map's sits above the drawing: a reader
who reads the list first has already concluded it was complete. `graph_coverage` is what makes
this answerable at all, which is the argument P4's specification section 6 makes.

The unmatched finding count. A recommendation joins to a resource on the provider's own
identifier, and the first party sources report identifiers that do not always match what
Config recorded. An empty finding list would then read as a clean resource when the truth may
be that nothing could be joined to it. Measured rather than assumed: the route counts the
findings in the same account that matched no `provider_id` at all and the page says the
number. This is how ISS-205 was found rather than argued about.

**Null cost is not zero cost.** A resource with no line item in the latest period is one the
bill does not mention, which happens for a resource created after the period closed and for
one whose charges land under a parent. Rendering that as zero would tell a reader it is free,
which is constraint 5 applied to a join rather than to a failure.

## How it works

`CostRepository.for_resource` sums `effective_cost` for one `resource_id` in one billing
period and returns `Decimal | None`, through `scoped_select`, so a resource in an account
outside scope contributes nothing even if its identifier were guessed.

`TopologyRepository` gained three reads. `one` fetches a node through the scope guard.
`slice_coverage` fetches that node's own slice row. `findings_for` returns the matched
recommendations and the count of unmatched ones, as one method, because two calls could
disagree about which account was being counted.

Neighbours come from `subgraph(bounds=Bounds(max_depth=1))`, the same bounded traversal the
map uses, so the neighbour list and the map cannot disagree about what a resource is attached
to. Edges with `leaves_the_graph` set are reported separately, with the API that supplied
them, because the far end of a cross account relationship is the most interesting thing on the
page and a row pointing at an absent resource is not how to show it.

Findings are serialised by `recommendation_out`, promoted from the waste route's private
helper rather than copied, so FEAT-052's risk verdict arrives here without a second
serialiser to forget to update. `saidOf` moved to `screens/sliceCoverage.ts` for the same
reason: the map and this page make the same claim about the same row.

A 404 answers both a node that does not exist and a node outside scope, deliberately.
Distinguishing them would tell a narrowed reader that a resource exists in an account they
were not granted.

## Failure behaviour

`scope_coverage` on this page is one of one slices when the resource's slice is COMPLETE and
nought of one when it is not, so the trust strip reads degraded on a page drawn from an unread
region. The unit is slices, not accounts, because one resource sits in exactly one slice.

A missing coverage row renders its own notice. It should be impossible, because the collector
writes a row per enrolled slice on every run, but treating a missing row as a healthy one is
the exact failure the coverage table exists to prevent.

Every empty section says so in words. An empty finding list, an empty neighbour list and an
absent cost are three different claims about the estate and none of them renders blank.

## Security considerations

Scope is enforced twice, per constraint 3. Every read goes through `scoped_select`, and the
route's own dependency resolves the scope before any of them run. The neighbour walk repeats
the scope predicate in the recursive term, which is what stops a traversal walking out of
scope one hop at a time.

The 404 is the security behaviour, not a convenience. A 403 on an out of scope node would
confirm the node exists.

Read only, constraint 6. The page offers no control that changes anything in a member account.

## Interface

`/inventory/resources/:nodeId`, linked from every resource in the topology map's accessible
table, and linking back to the map. Not in the navigation, because it is a destination rather
than a screen you choose, which is how `/governance/queries/:id` works.

The cost renders as measured and the savings on the same page render as modelled, both through
`Figure`. That pairing is asserted in the screen test: two money figures on one page, one from
the bill and one from a model, and rendering them identically would invite a reader to treat
an estimate as a fact.

## Not doing

Linking from the waste list. A recommendation carries a provider identifier and the page takes
a node identifier, and the two only join where a collector recorded both. The unmatched count
measures how often that fails, which is ISS-205, and a link that broke for most first party
findings would be worse than no link.

The resource inventory list at `/inventory/resources`. That is the screen ISS-204 tracks and a
different feature: this page is its detail view and does not resolve it.

Any history. The page shows the latest period's cost and the current graph. A resource's cost
over time and its relationships over time both exist in the tables and neither is drawn here,
because a time series on this page needs a decision about which of the two timestamps it is
indexed by and that decision deserves its own argument.
