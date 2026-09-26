# FEAT-031: Topology graph

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | In build |
| Specification | [P4 spec](../specs/2026-09-20-p4-inventory-and-topology-design.md), section 5.2 |
| Tasks | TASK-P4-004 to TASK-P4-007, TASK-P4-011 |
| Refresh cadence | Follows FEAT-030 |

## What it does

The connection map between resources: VPC to subnet to network interface to instance to security group to target group to load balancer, plus cross account edges.

## Why it exists

The requirement asked how resources connect to each other.

## What is already known

Node and edge tables in PostgreSQL traversed with recursive common table expressions, see ADR-0005. Config relationships supply most edges. Transit Gateway attachments, VPC peering, PrivateLink and cross account trust need supplementing.

## How it works

Node and edge tables in PostgreSQL, traversed with recursive common table
expressions, per ADR-0005. VPC to subnet to network interface to instance to
security group to target group to load balancer, plus cross account edges.

Config relationships supply most edges. Transit Gateway attachments, VPC peering,
PrivateLink and cross account trust need supplementing from their own APIs, and
each edge records which API supplied it.

Edges are directed: a security group permitting an instance is not the instance
permitting the group.

## Failure behaviour

**An edge Meter cannot see is not an absent edge**, and a graph makes that worse
than usual. A failed cost collection leaves a missing number and a screen that says
so. A failed topology collection leaves a graph that still renders, still
traverses, and answers every question wrongly in the same direction: everything
looks less connected than it is.

So traversal returns its result **and** the coverage of every slice it touched, as
part of the return type rather than as an optional second call. A caller cannot
forget to look, and the caller who would forget is FEAT-044, scoring somebody's
production change.

A cycle terminates, because a security group referencing itself is the common case
and a recursive CTE without a depth bound does not stop on one.

## Security considerations

Scoped by account. The edge rule is argued explicitly in the guard, because an edge
joins two nodes that may be in different accounts, and whether a reader entitled to
one end may see it is a decision rather than an oversight.

## Interface

`GET /inventory/topology`, bounded server side by depth and node count.

## Not doing

**Application level dependencies.** A service calling another over the internet
leaves no infrastructure edge. This is an infrastructure graph and says so, which is
why any blast radius derived from it is a lower bound.
