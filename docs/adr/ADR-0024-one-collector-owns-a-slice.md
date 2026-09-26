# ADR-0024: One collector owns a slice's graph

Date: 2026-09-26
Status: Accepted

## Context

P4 reads the topology from two sources. `finops_providers/aws/config_inventory.py`
reads an organization Config aggregator, which supplies most relationships and stops
at the account boundary. `finops_providers/aws/topology.py` reads four EC2 and IAM
APIs, which supply the edges that cross it.

The P4 plan, TASK-P4-006, asks for two collectors, one per source, with a schedule
row each. That is the obvious shape: two sources with different costs and different
freshness requirements, and ADR-0012 already says cadence is data rather than code.

It does not work, for two reasons that are both about who may remove a row.

**Both write the same table.** A node's identity is `(tenant_id, provider_id)`, and
every node the edge supplement emits is a resource Config also records: the
supplement emits them only so it can stand alone in a slice where Config was
refused. So the two collectors cannot each own a node row. There is one row and two
writers.

**The retraction keys on the run id.** A resource that has gone is removed by
deleting the rows in a slice whose `ingest_run_id` is not this run's, which is the
pattern `cost_focus` established and the only signal that works: a timestamp cannot
distinguish two runs inside one second. With two collectors, whichever ran second
would delete every row the first one wrote, and nothing else. The graph would hold
exactly one source's view at all times, alternating.

A third option exists and was written out before being rejected. Give
`topology_node` a `source` column, have the upsert keep the first writer's value,
and scope each collector's retraction to the sources it owns. It works. It also
means the answer to "may this collector delete this row" is a join across two
columns and a rule about which writer arrived first, on the one code path where a
bug deletes data rather than showing a wrong number.

## Decision

One collector owns a slice's graph. `finops_ingest/collectors/inventory.py` is that
collector, and `finops_ingest/collectors/topology.py` holds a composite source that
reads every source for a slice in one run and merges the results.

There is one schedule row, `inventory`, at a daily cadence. Its reason states the
argument for six hourly and the call volume argument against, so the number can be
settled from a real estate rather than from a paragraph.

The merge keeps the first source's version of a duplicate node, and the caller
orders the sources richest first: Config's node carries a name, tags and a real
capture time, and the supplement's carries an identifier and a kind.

A shortfall from any source makes the whole slice PARTIAL. That is the point of
merging as a set rather than picking a winner: if Config answered and the peering
call refused, the graph is missing its peering edges and the coverage row has to say
so even though most of the slice is there.

## Consequences

The two sources cannot have different cadences. If the supplement later needs its
own, the right move is to design slice ownership on purpose, which means the `source`
column and its retraction rule arrived at deliberately, rather than inheriting them
by accident from two schedule rows.

A slow source slows the whole collection of a slice. The four supplement calls are
per account and region, so a run is about five calls per slice rather than one, and
the schedule row's reason says where that stops being affordable.

The plan's TASK-P4-006 is delivered with one collector rather than two, and its
first acceptance criterion, that a departed resource is removed with its edges
scoped to one tenant and one run, is delivered exactly. The deviation is in the file
count, not in the behaviour.

## What this does not decide

Whether a PARTIAL slice may ever be retracted from. It may not, and that is a
separate and stronger rule stated in the collector: a partial read cannot tell a
resource that is gone from a resource it could not see, so removing on one would
delete the estate a refused credential hid, silently, and the graph would then be
smaller and still render. That rule would be necessary even with two collectors.
