# ADR-0035: The hub reaches AWS through endpoints, and through a relay for what has none

Date: 2026-10-08
Status: Accepted. The owner chose the path on 2026-10-05, P9 spec section 5.1 and OPEN-16, and
spot prices and Savings Plans rates on 2026-10-07, OPEN-17. This records it as built in
TASK-P9-001, and one service the owner's rule reaches that the choice did not name
Supersedes: nothing. It closes ISS-242 and ISS-259

## Context

The hub has no route out, and ADR-0028 relies on that: every call leaves through a VPC endpoint
or not at all. A deployed hub could reach six services, while its collectors called about
fifteen more, ISS-242, and the comment above the six said they were every service the tasks
call. Three facts shape the fix.

1. Cost Explorer, Organizations, IAM and Cost Optimization Hub answer only in us-east-1, and
   the Price List Query API only there among the Regions Meter uses. Cross Region PrivateLink
   does not reach them, so an endpoint in the hub's Region cannot either.
2. The collectors call each member account in every collection Region, eu-west-1 and
   eu-west-2 by OPEN-06, so the second Region needs its own endpoints.
3. Budgets, Support and Invoicing have no interface endpoint at all. Budgets and Support were
   measured against the AWS PrivateLink service list on 2026-10-05; Invoicing, which P10 added,
   on 2026-10-08, and the list names no Invoicing endpoint.

## Decision

**Endpoints for every service that has one.** In the hub's Region, an interface endpoint for
each service the tasks call there. In us-east-1 and in the second collection Region, a small VPC
holding only endpoints, peered to the hub, with one private hosted zone in the hub per service
resolving the hostname an SDK calls to the endpoint across the peering. No client names an
endpoint URL, so none can bypass this by forgetting one. The hub's private route table gains a
route to each endpoint VPC and nothing else; each endpoint VPC has one route, back to the hub.

**A relay for what has none.** Budgets, Support and Invoicing, and spot prices and Savings Plans
rates in every Region, go through one Lambda function with no VPC, `finops_relay`. The hub
invokes it through the Lambda endpoint, so the decision when to ask stays in
`collector_schedule`, constraint 9, and the relay answers through the data bucket, which the hub
reads through its S3 gateway endpoint. Invoicing joins Budgets and Support under the owner's own
rule, an endpoint for every service that has one and this path for those that have none, rather
than by a new choice.

The relay is narrow by construction.

- It makes only the calls `ALLOWED` names, six of them, each read only, and refuses anything
  else before a client exists.
- The role each call is made as is the list's, not the caller's: the payer's organization reader
  for Budgets and Invoicing, a member's collector role for Support, its own for public prices.
- Every role it assumes is narrowed by a session policy to the one action, so even an edited
  relay could not use an assumed role for anything else.
- AWS's own error codes come back unchanged, so the adapter's `translate` names the same typed
  cause it would for a direct call.
- It imports nothing of Meter's and nothing beyond botocore, a contract in `pyproject.toml`, and
  a test imports its handler from the zip alone.

The existing adapters need no second implementation: `RelayClient` has a boto3 client's shape,
and `AwsBudgets` and `AwsInvoices` read through it unchanged in the tests.

## Cost

Endpoint prices are measured from the AWS price list, offer file version 20260917190528
published 2026-09-17: 0.011 USD per endpoint per zone hour in eu-west-1 and eu-west-2, 0.010 in
us-east-1, and 0.01 USD per GB processed. Endpoints are counted from the Terraform. Every total
below is modelled, at two zones and 730 hours a month.

| Where | Endpoints | Each a month | A month |
| --- | --- | --- | --- |
| eu-west-1, the hub, already built | 6 | 16.06 USD | 96.36 USD |
| eu-west-1, the hub, added | 10 | 16.06 USD | 160.60 USD |
| eu-west-2, added | 6 | 16.06 USD | 96.36 USD |
| us-east-1, added | 5 | 14.60 USD | 73.00 USD |
| **Added by this decision** | **21** | | **329.96 USD** |

Beside the endpoints, also modelled and not measured: 11 private hosted zones at the published
0.50 USD a month each, 5.50 USD; two flow log keys at about 1 USD each; the relay's invocations,
a few hundred a day at well under a dollar a month; and data processed and carried between
Regions, cents at the traffic a collector makes. About 338 USD a month in all, against the
roughly 290 USD the owner chose on, which assumed about 20 endpoints at 14.7 USD each. The
difference is one more endpoint than estimated and the measured price of 0.011 rather than
0.010 in the two European Regions.

One lever is left unpulled: the endpoint VPCs in one zone rather than two would save about 85
USD a month (modelled), at the price of a zone failure cutting the hub off from those Regions.

## Alternatives

- **A NAT gateway with an allow list**, option B in the spec. Cheaper and with fewer moving
  parts, and it opens the egress path ADR-0028 is built on its absence of. Refused by the owner
  on 2026-10-05.
- **Everything through the relay.** One path instead of three, and it would make a Lambda
  function the hub's only way to the cloud it reads, with every call's size and latency to match.
- **An endpoint URL in each client instead of private hosted zones.** It works until one client
  forgets, and nothing would say so until that call failed in a deployment.

## Consequences

- `tests/contract/test_network_paths.py` holds every service the adapters call, read from the
  code, to one of these paths. A collector that calls something new fails a test, not a deploy.
- A Region added to OPEN-06 needs a provider, a module call and a peering in `endpoints.tf`,
  because Terraform cannot make a provider per item of a list.
- The relay is a second principal the member and payer roles trust, by name, with the same
  ExternalId and organization conditions as the task role. `docs/05-SECURITY.md` lists it.
- What hands the adapters a `RelayClient` in production waits on the collector registry nothing
  assembles yet, ISS-182, as every other adapter's wiring does.
- Nothing here has been applied. `terraform validate` passes for the hub, member and management
  stacks; the first apply waits on an AWS account, ISS-002.
