# ADR-0036: The worker reaches the AI providers through a NAT gateway, and nothing else does

Date: 2026-10-12
Status: Accepted. The owner chose the path on 2026-10-12, OPEN-31, for P13
Supersedes: nothing. It amends ADR-0035, whose hub had no route out

## Context

ADR-0035 gave the hub every AWS service it calls through an interface endpoint, the S3 gateway
endpoint, or a relay in us-east-1, and kept the private route table without a default route, so a
task could reach nothing outside AWS. P13 reads OpenAI's and Anthropic's usage and cost reports,
`api.openai.com` and `api.anthropic.com`. Neither has a VPC endpoint, and the relay is a Lambda
function for AWS APIs, which a third party call through it would turn into a general proxy with
the member and payer roles' trust. `network.tf` said what this would cost: a non AWS dependency
means an endpoint or a proxy, not just a call.

## Decision

1. One NAT gateway, with an Elastic IP, in the hub's first public subnet, and a default route to
   it from the private route table.
2. The worker's tasks get a security group of their own, `worker_internet`, whose one egress rule
   is TCP 443 to `0.0.0.0/0`. The shared task group's egress is unchanged: the endpoints, S3, the
   database and the VPC. The API, the web and the dispatcher have no rule that reaches the
   internet, so the route exists for them and the security group refuses it.
3. The VPC flow logs, which already record accepts and rejects, are the record of every connection
   the worker makes and every one another task attempts.
4. A test reads the Terraform and fails if any security group other than `worker_internet` has an
   egress rule to `0.0.0.0/0` or `::/0`, so a second route out is a failed build.

## Cost

Modelled from AWS's list prices for eu-west-1, the hub's Region, not measured: USD 0.048 an hour
for the gateway, USD 35.04 for a 730 hour month; USD 0.005 an hour for its public IPv4 address,
USD 3.65 a month; USD 0.048 per GB it processes. A day of usage and cost reports from both
providers is kilobytes, so the data charge rounds to nothing and the total is about USD 38.69 a
month. `docs/04-DEPLOYMENT.md` records that a NAT gateway is cheaper than endpoints below roughly
1,560 GB a month; this one adds to the endpoints rather than replacing them, so that comparison
does not apply.

## Alternatives

- **Through the relay.** No new network cost, and it would make the relay, trusted by every member
  and payer role, a proxy to the internet. Rejected for that trust.
- **AWS Network Firewall with a domain allow list.** Restricts the route to the two hosts, at a
  modelled USD 288 a month for one endpoint at eu-west-1's list price of USD 0.395 an hour before
  data. Rejected on cost for two hosts; it is the upgrade if the worker's egress needs to be
  narrower than a security group can say.
- **One gateway per zone.** Removes the zone as a single point of failure for the provider reads, at
  double the cost. Rejected: a lost zone stops two daily reads, typed Unreachable, and the next run
  catches up, because each run rereads the billing period to date.

## Consequences

- The hub is no longer a VPC with no route out. The property that holds now is narrower: only the
  worker can reach the internet, only on 443, and every connection is in the flow logs.
- A worker task compromised through a dependency can reach any host on 443. ADR-0031's hashed
  dependency locks and the admission gate are what stands between a dependency and the worker.
- `tests/contract/test_network_paths.py` holds the two provider hosts to this path, as it holds
  every AWS service to its endpoint or the relay.
- The admin keys live in Secrets Manager under `meter/<env>/ai/`, reached through the existing
  endpoint. The hub has one task role, shared by the API and the worker, so both may read that
  path; only the worker can reach a provider with what it reads. A role the worker alone holds is
  ISS-286, and needs every member account's trust policy to name it, so it is not done here.
- Nothing here has been applied. The first apply waits on an AWS account, ISS-002.
