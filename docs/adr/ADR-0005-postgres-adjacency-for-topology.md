# ADR-0005: PostgreSQL adjacency tables for topology, not a graph database

Date: 2026-08-23
Status: Accepted

## Context

The resource topology is genuinely graph shaped. A VPC contains subnets, which
contain network interfaces, which attach to instances, which carry security
groups, which are referenced by target groups behind load balancers. The
organization tree is also a graph, though a simple one.

The instinct is to reach for Neptune.

## Decision

Model topology as `node` and `edge` tables in PostgreSQL, traversed with
recursive common table expressions. Render with Cytoscape.js, server side
filtered to at most 2,000 nodes.

Introduce a dedicated graph database only when a query requiring more than
four hops is demonstrated to be needed and demonstrably slow.

## Consequences

Positive.

- No additional database, no additional cost, no additional operational
  surface. Around 95 percent of real queries are one to three hops, which
  recursive CTEs handle comfortably.
- Topology data sits next to cost data, so joining a graph edge to a cost fact
  is an ordinary join rather than a cross system federation.

Negative.

- Deep or unbounded traversal will be slow. This is accepted deliberately,
  with a documented trigger to revisit.
- Some graph query patterns are more awkward to express in SQL than in a graph
  query language.

## Alternatives rejected

**Amazon Neptune.** Rejected as premature. It is a second database, a second
security boundary, a second backup story, and a material monthly cost, in
exchange for capability that has not been shown to be needed.

**Apache AGE on PostgreSQL.** Held as the upgrade path if graph query
ergonomics become the real problem, since it keeps a single database.
