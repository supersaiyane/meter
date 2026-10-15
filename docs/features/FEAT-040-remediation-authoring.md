# FEAT-040: Remediation authoring

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | In build |
| Specification | [P7 spec](../specs/2026-09-28-p7-insight-and-llm-layer-design.md), section 3 |
| Tasks | TASK-P7-009, TASK-P7-014, and in P15 TASK-P15-002 and TASK-P15-004 |
| Refresh cadence | On demand |

## What it does

Generates the Terraform or CloudFormation diff, or the Grafana panel patch, and opens a merge request for human approval.

## Why it exists

Meter is read only in v1. Remediation as a reviewable code change is how it acts without holding write credentials.

## What is already known

Never merged automatically. The same constraint as the security autofix, and for the same reason. Superseded on 2026-10-15 for fixes that lose nothing if wrong, by ADR-0038: under the tenant's merge policy, Meter may merge a reversible fix it opened through the repository's own protections, FEAT-094. A deletion, which every fix written here is, is still never merged by Meter.

## How it works

**As built, 2026-10-04, TASK-P7-009 and TASK-P7-014.** `finops_query/remediation.py`
authors a removal for the eight waste classes whose fix is deleting the resource: an idle
instance, an unattached volume, an aged snapshot, an idle NAT gateway, an idle load
balancer, an unassociated Elastic IP, an alarm stuck in insufficient data, and a log group
nobody queries. The resource's Terraform address comes from FEAT-057's
`resource_management`. The change is one new file under `meter/remediation/`, named for the
recommendation, holding a `removed` block with `destroy = true`, on a branch named the same
way. The file and the body both tell the reviewer to delete the resource's own block in the
same change, because Meter does not know which file holds it.

The body carries the recommendation, its saving marked **modelled**, and the blast radius
band from FEAT-044, and ends with the sentence that Meter opened the pull request and will
never merge, approve or apply it. `propose` hands the draft to a `PullRequestSink`, and the
port has one method, which opens.

This differs from what was known before the spec, which expected CloudFormation and Grafana
panel patches as well. Only Terraform removals are authored.

**Why In build.** The sink has a fake and no adapter, because the code host is OPEN-13, and
nothing in the product calls `propose`, ISS-228.

## Failure behaviour

A recommendation that cannot be authored is refused with its reason, never guessed at: a
class whose fix is not a removal, a resource with no `resource_management` row, and an
address with an instance key, which a `removed` block cannot target.

## Security considerations

Constraint 6. Nothing applies, merges or approves, and `tests/contract/test_no_llm_writes.py`
holds three absences: no production module names a merge, an approval or an apply, none
starts terraform, aws or kubectl as a process, and the member role grants reads only. The
credential an adapter will need is a repository write, the first write Meter would hold
anywhere, and it needs to open a pull request and nothing more, OPEN-13.

## Interface

None yet, ISS-228. `author` and `propose` in `finops_query/remediation.py`, and a refusal
is a `NotAuthored` carrying its reason.

## Not doing

**A resize.** It needs the target value and the file that sets it, and nothing reads
either. **Applying anything**, in any account, in v1.
