# P4 Inventory and Topology: design specification

Date: 2026-09-20
Status: Provisional, pending approval
Sub project: P4
Features: FEAT-030, FEAT-031, FEAT-032
Depends on: P0 delivered
Supersedes: nothing

## 1. Purpose

Every other sub project reasons about resources it has never seen. P1 reads charges
that name a `resource_id` and knows nothing else about it. P3 recommends changing a
resource without knowing what depends on it.

P4 is the answer to "what is actually out there, and what is connected to what".

It has one consumer whose correctness depends on it, and that consumer shapes the
design: FEAT-044 scores the blast radius of a proposed change by walking these edges.
A graph that is quietly incomplete would produce a confidently low score for a
resource with forty dependents nobody could see. Section 6 is about that, and it is
why this specification is not simply "ingest Config".

## 2. Definition of done

- Every resource in every enrolled account and enabled region has a row, with its
  region and availability zone.
- The connection map exists as nodes and edges, traversable to arbitrary depth.
- **Completeness is a recorded fact, per account and per region.** A consumer can ask
  whether the graph it is about to walk is whole, and gets a truthful answer.
- The map renders and stays usable at the scale the estate actually reaches.
- The monthly cost of recording is estimated, written down, and visible on the
  platform's own cost screen once it is running.

## 3. Out of scope

**Anything that writes.** Constraint 6. This sub project reads and draws.

**Resource configuration history.** Config records it and it is a different product
feature: "what did this security group look like in March" is drift detection, not
topology. Recording it would also multiply the cost in section 10.

**Non AWS resources.** The node and edge model is deliberately provider neutral so
GCP and Azure stay a connector rather than a rewrite, but nothing here reads them.

## 4. Module structure

```
finops_core/
  domain/topology.py       Node, Edge, NodeKind, EdgeKind, GraphCoverage
  ports/inventory.py       ResourceInventory exists from P0 and is widened here
  ports/topology.py        TopologySource. Relationships, not resources
finops_providers/
  aws/config_inventory.py  The Config aggregator. Unproved, ISS-122
  aws/topology.py          What Config does not relate: Transit Gateway
                           attachments, VPC peering, PrivateLink, cross account
                           trust
  fake/topology.py         An estate with a region it cannot read, on purpose
finops_ingest/collectors/
  inventory.py             Nodes, one aggregator read
  topology.py              Edges, and the coverage record
finops_query/
  graph.py                 Recursive traversal, depth bounded. No provider
```

## 5. Data model

### 5.1 `topology_node`

| Column | Why |
| --- | --- |
| `node_id` | Ours |
| `tenant_id`, `sub_account_id` | Scoped by account like everything else |
| `provider_id` | The ARN or equivalent. Unique with the tenant |
| `node_kind` | `VPC`, `SUBNET`, `INSTANCE`, `ENI`, `SECURITY_GROUP`, `TARGET_GROUP`, `LOAD_BALANCER`, `NAT_GATEWAY`, `TGW_ATTACHMENT`, `VPC_ENDPOINT`, `VOLUME`, `DB_INSTANCE`, `FUNCTION`, `OTHER` |
| `region_id`, `availability_zone` | FEAT-030's stated purpose. Zone is nullable, and a null means a regional resource rather than an unknown |
| `name`, `tags` | Whatever the provider gave |
| `as_of`, `collected_at` | Constraint 10 |

### 5.2 `topology_edge`

| Column | Why |
| --- | --- |
| `edge_id` | Ours |
| `tenant_id` | Scope |
| `from_node_id`, `to_node_id` | Directed |
| `edge_kind` | `CONTAINS`, `ATTACHED_TO`, `ROUTES_TO`, `TARGETS`, `PERMITS`, `PEERS_WITH`, `TRUSTS` |
| `is_cross_account` | Materialised, because it is the expensive question to ask repeatedly and the interesting one to answer |
| `source` | `CONFIG_RELATIONSHIP` or the API that supplied it. An edge Config did not give us is an edge somebody has to maintain |
| `as_of`, `collected_at` | Constraint 10 |

Unique on `(tenant_id, from_node_id, to_node_id, edge_kind)`. Direction matters: a
security group permitting an instance is not the instance permitting the group.

### 5.3 `graph_coverage`

The table this specification exists for.

| Column | Why |
| --- | --- |
| `tenant_id`, `sub_account_id`, `region_id` | The slice being described |
| `state` | `COMPLETE`, `PARTIAL`, `UNREAD` |
| `cause` | The typed cause where not complete. `AccessDenied`, `Throttled`, `NotOptedIn`, `Unreachable` |
| `node_count`, `edge_count` | What was actually read |
| `as_of`, `collected_at` | Constraint 10 |

One row per account and region, written on **every** run including failed ones,
exactly as `account_health` already is. A slice never read has an `UNREAD` row rather
than no row, because absence of a row and absence of resources are indistinguishable
to a consumer, and one of them is dangerous.

## 6. The rule that shapes this sub project

**An edge Meter cannot see is not an absent edge.**

This is constraint 5 applied to a graph, and a graph makes it worse than usual. When
a cost collector fails, a number is missing and the screen says so. When a topology
collector fails, the graph is still a graph. It renders. It can be traversed. Every
query against it returns an answer, and the answers are wrong in the one direction
that matters: everything looks less connected than it is.

So:

1. `graph_coverage` is written on every run, successful or not.
2. `finops_query.graph` traversal returns its result **and** the coverage of every
   slice it touched. Not as an optional extra, as part of the return type, so a
   caller cannot forget to look.
3. A consumer needing completeness must check it. FEAT-044 refuses to score against a
   `PARTIAL` or `UNREAD` slice, per the P3 specification section 12.
4. The map marks incompletely read regions visibly, rather than drawing them as
   sparse.

A test in the contract suite removes one region's edges, sets its coverage to
`PARTIAL`, and requires every consumer to refuse rather than answer.

## 7. Flow

```
AWS Config aggregator ---> inventory collector ---> topology_node
  (selective recording,                                  |
   see section 10)                                       |
                                                         v
Config relationships ----+                        topology_edge
TGW / peering /          +--> topology collector -->     ^
PrivateLink / trust      |              |                |
(supplementary APIs) ----+              |                |
                                        v                |
                                 graph_coverage ---------+
                                 written every run,
                                 including failed ones
                                        |
                                        v
                    finops_query.graph traversal returns
                    (nodes, edges, coverage) as one value
                                        |
                  +---------------------+------------------+
                  v                                        v
           /inventory/topology                    FEAT-044 blast radius
           (2,000 node cap)                       (refuses when PARTIAL)
```

## 8. Interface

| Route | Answers |
| --- | --- |
| `GET /inventory/resources` | Every node, filterable by kind, region and zone |
| `GET /inventory/topology` | A subgraph, from a root node outward to a bounded depth |
| `GET /inventory/topology/coverage` | Which slices are complete, and why the others are not |

`GET /inventory/topology` takes a root and a depth and is **bounded server side**. An
unbounded traversal of a real estate is a query that returns the whole estate, and
the browser is not the place to discover that.

The subgraph response carries its coverage in the envelope, not only in `/coverage`.
A caller that asked for a subgraph and got an answer must be able to see, in that
answer, that part of it was unreadable.

## 9. User interface

`/inventory/topology`, Cytoscape.js, filtered server side to at most 2,000 nodes
because a browser will not survive more. That cap is FEAT-032's own stated number and
is enforced by the route rather than by the client.

Two things the screen must do that a topology map usually does not.

**Say what it could not see.** A region with `PARTIAL` coverage is named in the
interface, above the graph, not as a footnote. The existing `CoverageBanner` component
already does this for accounts and is reused.

**Say when it truncated.** A subgraph that hit the 2,000 node cap says so, and says
how many nodes were omitted. A map that silently shows the first two thousand is a map
that is wrong about the shape of the estate.

The existing `GraphCanvas` and `OrgTree` components already hold three hundred
accounts, and their virtualisation is the starting point.

## 10. Infrastructure and its cost

ISS-012: recording all resource types organization wide in AWS Config is a five figure
monthly line item.

**Decided 2026-09-20: selective recording.** Continuous recording for the resource
types the graph is built from and the ones that carry cost, periodic recording for
stable types, and nothing at all for types no feature reads.

Three things make this honest rather than a hope.

1. The resource type list lives in Terraform, not in prose, so what is recorded is
   reviewable in a diff.
2. **The estimated monthly cost is written into the task that applies it**, before it
   is applied, with the resource type count and the assumed configuration item volume
   that produced the estimate.
3. The aggregator and its recorders are tagged `finops:module`, per constraint 7, so
   the actual cost appears on the platform cost screen beside everything else. The
   estimate meets the bill inside the product that made it, which is the FEAT-029
   discipline applied to ourselves.

A second Terraform stack, `infra/terraform/config/`, because the aggregator lives in
the payer account and the recorders are a StackSet across members. It validates and is
not applied, like the P1 export stack, until ISS-122 is resolved.

## 11. Testing

The contract suite gains `TopologySource`, parameterised over the fake and the
unproved AWS adapter.

**The fake estate contains a region it cannot read.** Not as an afterthought: the
fake's default estate has three regions and one raises `AccessDenied`, so every test
above the provider runs against a partial graph unless it deliberately asks for a
whole one. A fake that is complete by default makes the incompleteness path the one
nobody exercises, and section 6 is the whole point of this sub project.

**A cycle.** Real estates have them, a security group referencing itself is the common
case, and a recursive CTE without a depth bound does not terminate on one.

**Three hundred accounts.** The organization map already proves the interface holds at
that scale, and the topology graph is larger by roughly the number of resources per
account.

## 12. Risks

**The graph is confidently wrong.** Section 6, and the mitigation is the whole of
section 6.

**Config cost overruns the estimate.** Mitigated by section 10's three points, and by
the estimate being checkable against the bill in this product.

**The map is unreadable at real scale.** Mitigated by the 2,000 node cap being a
server side rule with a stated truncation, rather than a client side hope.

**Edges no API reports.** Application level dependencies, a service calling another
over the internet, are invisible here. The graph is an infrastructure graph and says
so. A blast radius score derived from it is a lower bound on blast radius, never an
upper one, and FEAT-044's screen must say that in words.

## 13. Open questions

| ID | Question | Effect if unanswered |
| --- | --- | --- |
| OPEN-02 | Single payer or multiple | A second payer means a second aggregator and cross payer edges, which the edge model supports and the collector does not yet |
| OPEN-06 | Regions | Answered 2026-08-23: eu-west-1 and eu-west-2 only. The recorder list follows it |

## 14. Features delivered

FEAT-030, FEAT-031, FEAT-032.

FEAT-044 is P3's and is unblocked by this sub project, which is why P3's plan places
it after P4 rather than inside its own natural wave.

## 15. Exit criteria

1. Every resource in the seeded estate has a node with a region, and a zone where it
   has one.
2. The graph traverses from a VPC to an instance and back to a load balancer, and a
   test asserts the path.
3. A cycle does not hang the traversal.
4. `graph_coverage` holds a row for every account and region, including the one that
   could not be read and one that has never been attempted.
5. Every traversal returns its coverage, asserted by a test that checks the return
   type rather than the value.
6. A consumer asked to act on a `PARTIAL` slice refuses, asserted by the test in
   section 6.
7. The map truncates at 2,000 nodes and says so.
8. The Terraform validates, is not applied, and carries its own cost estimate.

As with P3, none of this is met against a real estate until ISS-122 is resolved.
