# ADR-0028: The language model runs in the hub account, on Bedrock

Date: 2026-09-28
Status: Accepted
Supersedes: nothing
Relates to: ADR-0007, which confines the model to four roles and is unchanged by this

## Context

P7 is the first sub project that sends anything anywhere. Every sub project before it
reads from AWS and writes to a database inside the same account, and the security
posture rests on that: constraint 6 says there is no write API call into a member
account in v1, and `tests/contract/test_no_quota_writes.py` is what keeps the most
recent version of that promise honest.

A language model changes the shape of that whichever way it is hosted, because
something has to be sent to it. What is sent is the thing to be careful about. The
four roles ADR-0007 allows are natural language cost questions, anomaly narration,
remediation authoring and summarization, and all four put an organization's account
identifiers, service names, resource names, tag values and spend figures into a
prompt. Resource names in particular are often the most sensitive thing in an estate,
because people name things after customers, projects and acquisitions.

Two ways to host it. The choice was made on 2026-09-28.

## Decision

**The model runs on Amazon Bedrock, in the hub account, in the regions the product
already deploys to.** No new outbound network path leaves the account boundary this
product already has.

Three consequences follow, and each is worth more than the model quality difference
that buys them.

**No new egress to review.** `docs/08-THREAT-MODEL.md` covers six trust boundaries. A
third party model API would be a seventh, with its own data processing agreement, its
own retention answer, its own subprocessor list and its own account of what happens to
a prompt once it has been answered. Bedrock is reached over the same IAM path as every
other AWS call here, through the hub task role, so the boundary already exists and is
already documented.

**Self metering sees the cost for free.** Constraint 7 says the platform meters
itself, every platform resource carries `finops:module`, and the platform's own cost is
on the front page. Bedrock invocations arrive on the same bill
`finops_ingest/collectors/platform_cost.py` already reads, tagged like everything
else. A third party API arrives on a separate invoice no collector can see, which
would leave a FinOps product unable to report the cost of its own newest feature. That
is not embarrassing so much as disqualifying.

**Amended 2026-10-05, ISS-230.** "Tagged like everything else" was wrong. An on demand
call names no resource and carries no tag, so it would have reached the bill with no
module. Each model is now reached through an application inference profile that the hub
stack tags `finops:module = assistant`, and the task role may invoke the model only
through it. The reasoning above stands: the call still arrives on the bill a collector
reads, which a third party invoice never would.

**FEAT-046 becomes defence in depth rather than a prerequisite.** Outbound AI request
scanning, to redact or block secrets, was specified as a control on data leaving the
organization. With the model inside the account it is no longer the thing standing
between a customer's resource names and a third party, so it ships as hardening in its
own task rather than as a blocking dependency of every other P7 feature. It is still
built, because a secret in a prompt is a secret in a log whoever receives it.

## What it costs

**Model choice is limited to what Bedrock carries in Ireland and London.** That is the
real price and it should be stated plainly rather than minimised: the strongest
available model at any moment may be one Bedrock does not host in those regions, so
P7's quality ceiling is set by somebody else's regional rollout. If that becomes
binding the answer is not to add an egress path quietly. It is to reopen this decision
with an ADR that supersedes it and a threat model section that earns it.

**A port and a fake, so a later swap is a connector rather than a rewrite.**
`finops_core/ports/llm.py` declares what the product needs of a model and nothing
about how it is reached, exactly as `CostExport` and `QuotaSource` do, with a Bedrock
adapter in `finops_providers/aws/` and a deterministic fake in `finops_fakes/`. This is
not hedging against the decision above. It is the structure every other provider here
has, for the same reasons: it is what lets one contract suite hold the real adapter and
the fake to the same sentences, and it is what lets the tests run with no model at all.

## Why this is an ADR

It fixes where customer data goes. Reversing it means a new trust boundary, a new
subprocessor, a threat model section, a data processing agreement and a conversation
with whoever owns data protection. That is the definition of expensive to reverse, and
it is the kind of decision that gets made by accident in a prototype and discovered in
a security review.

## Consequences

- `finops_core/ports/llm.py` is the only thing the query layer knows about a model.
- The hub task role gains `bedrock:InvokeModel` and
  `bedrock:InvokeModelWithResponseStream`, scoped to named model identifiers rather
  than to a wildcard, so adding a model is a Terraform change somebody reviews.
- `finops_providers/aws/bedrock.py` is the only file importing the Bedrock client, and
  it is unproven against a real account like every other adapter here, ISS-002.
- The platform cost screen gains Bedrock as a module with no work at all, because it
  reads the bill by tag. Amended 2026-10-05: not with no work. It took a tagged inference
  profile per model and a grant that reaches the model only through it, ISS-230.
- Nothing in `finops_core`, `finops_query` or `finops_api` names a model or a vendor.
- A deployment with no Bedrock access gets `NotOptedIn` from the adapter and a screen
  saying the assistant is unavailable, rather than an assistant that answers questions
  with silence.
