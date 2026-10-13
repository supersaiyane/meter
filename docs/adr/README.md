# Architecture decision records

<!-- Basic boiler Plate Doc | Grade A
     Why this file exists: Explains what a decision record is for and when one is required.
     Grade A here: nothing in this file is specific to this project. Copy it unchanged.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

One file per decision that is expensive to reverse. Format is deliberately
short. If a decision can be reversed in an afternoon, it does not need a
record.

Status values: `Proposed`, `Accepted`, `Superseded by ADR-NNNN`, `Rejected`.

| ID | Decision | Status |
| --- | --- | --- |
| 0001 | Decompose into eight sub projects, build P0 then P2 then P1 | Accepted |
| 0002 | FOCUS 1.1 is the canonical cost schema | Accepted |
| 0003 | PostgreSQL only for the serving layer, no ClickHouse in P0 | Accepted |
| 0004 | Cross account access by StackSet deployed role, curated policy | Accepted |
| 0005 | PostgreSQL adjacency tables for topology, not a graph database | Accepted |
| 0006 | Ingest AWS native recommendation services before building a collector | Accepted |
| 0007 | The language model never computes a number | Accepted |
| 0008 | Identity adapter deferred, isolated behind two ports | Accepted |
| 0009 | An MCP server alongside the HTTP API, not instead of it | Accepted |
| 0010 | Minimus base images and a continuously maintained zero CVE posture | Accepted |
| 0011 | A decision ladder before any new code, and token economy | Superseded by ADR-0013 |
| 0012 | Collection cadence is data, not code | Accepted |
| 0013 | Seven rung ladder, disqualification record, security sign off | Accepted |
| 0014 | Derived documentation is generated from a registry | Accepted |
