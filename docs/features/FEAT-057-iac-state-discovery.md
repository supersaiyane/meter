# FEAT-057: Which file manages this resource

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Delivered |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), 2026-09-26 candidate list |
| Tasks | `TASK-P4-013` |
| Refresh cadence | Follows FEAT-030 |
| Source | Adopted from the IBM Turbonomic review on 2026-09-26 |

## What it does

Records, per resource, whether infrastructure as code manages it and which state file and
address own it. Read from Terraform state, attached to `topology_node`.

## Why it exists

FEAT-040 generates a remediation as a pull request and cannot produce a useful one without
knowing which file to change. It is also worth having on its own: a resource nobody manages in
code is a fact somebody wants to know, independently of any remediation.

Recorded in P4 rather than with FEAT-040 in P7 because who manages a resource is an inventory
fact about that resource, belonging beside its region and its zone. FEAT-040 is a consumer.
P7 has no plan and no approved specification, and writing tasks into one would be the guess
`docs/plans/README.md` warns about.

## How it works

`finops_core/domain/iac.py` holds the three valued rule and is pure. `management_of` decides
`MANAGED`, `UNMANAGED` or `NOT_DETERMINED` from what was read, what an operator declared, and
whether the read was whole.

The adapter reads the configured S3 objects, skips `data` sources because a state file also
records reads of things Terraform does not own, and builds the Terraform address including the
index key: `aws_vpc.main[0]` and `aws_vpc.main["a"]` are different addresses and only one exists
in any given file.

The collector resolves each resource to an account through `topology_node` before writing, and
counts the ones it cannot place. A state file routinely owns resources Meter has never
inventoried and has no account column of its own, so parsing the account out of the identifier
would have written rows keyed by a string that looked like an account.

`UNMANAGED` is never stored. It is derived per request from two things that are both about our
own configuration: the account being declared exhaustive, and no state location having refused
us on the latest run. Storing it would freeze a judgement made under yesterday's configuration
into a row that outlives it.

**Its own table rather than columns on `topology_node`, per ADR-0024.** One collector owns a
slice's graph: a second writer would race the inventory collector's run scoped retraction, and
the retraction would delete what the second writer had just put there.

## Failure behaviour

The default is **not determined**, never unmanaged. Unmanaged is an actionable fact and "we did
not look in the right bucket" is not, and rendering the second as the first would tell somebody
to import a resource already inside a module, which produces a duplicate, a state conflict or a
second copy of a live resource.

**A location that refuses us suppresses `UNMANAGED` everywhere**, not just for what it held. One
unreadable backend casts doubt on every account it might have contained, and the declaration
that the configured backends are exhaustive is worth nothing on a run where one of them was not
read. A refusal that could not be read also keeps its existing rows: removing them would turn a
managed resource into a not determined one on the strength of a failure.

**A read where every location refuses raises.** That is a configuration failure rather than a
partial answer, and an estate whose every backend refused us is not an estate with no code.

**No location configured writes nothing and says nothing is wrong.** That is a real deployment,
and every resource then reads as not determined, which is true.

## Security considerations

Read only, constraint 6. The backend location is configured rather than discovered, because
guessing at buckets is reconnaissance. No credential for a customer state backend lives in
this repository, and the scan gate covers the new configuration.

## Interface

The entity page, FEAT-053, shows the address where there is one and says not determined where
there is not.

## Not doing

Writing a pull request, which is FEAT-040. Reading CloudFormation or CDK: one format first, and
the port is shaped so a second is an adapter rather than a rewrite.

Taking a state lock. A Terraform lock blocks whoever is mid apply, so a tool that took one could
stall somebody's deployment, which is not read only in the sense the person on call cares about.

Joining a resource whose type publishes no ARN. An association, an attachment or a policy
document carries no identifier this can match, so those are counted as unplaceable rather than
guessed at. ISS-209 records how much of a state file that covers, which is not yet measured
against anything real.
