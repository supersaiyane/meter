# FEAT-034: Quota increase request drafting and tracking, never submission

| Field | Value |
| --- | --- |
| Sub project | P5 |
| Status | Specified |
| Specification | [P5 spec](../specs/2026-09-20-p5-quotas-and-limits-design.md), section 6 |
| Tasks | TASK-P5-007, TASK-P5-008 |
| Refresh cadence | On demand |

The title said "Quota increase workflow" until 2026-09-20, which promised something
constraint 6 forbids. A feature document promising what the product will not do is
one that will be quoted back.

## What it does

Drafts a limit increase request, hands it to a human to submit, and then tracks it
to completion. Meter never calls `RequestServiceQuotaIncrease`.

## Why it exists

Finding the headroom problem without a path to fix it is half a feature. The other
half turns out to be the tracking rather than the submitting: nobody loses a quota
increase because they could not find the button, they lose it because nobody checked
whether it was ever approved.

## How it works

Three parts, and only the first is the one people expect.

**The draft.** The service, the quota, the current limit, the observed usage and a
suggested new value with the working that produced it.

**The handover.** The exact console link and the exact CLI command, so the human step
is copy and paste rather than research.

**The tracking.** `ListRequestedServiceQuotaChangeHistory` is a read, so Meter can
watch a request it did not make travel from `PENDING` through `CASE_OPENED` to
`APPROVED` or `DENIED`, and show it on a screen beside the quota it concerns.

## What is already known

`RequestServiceQuotaIncrease` plus the Quota Request Template would give
organization wide defaults in one call. Both are writes into a member account, and
constraint 6 says there are none in v1.

Decided 2026-09-20: **track only.** The reasoning is in P5 spec section 6 and is not
about this particular API, which is close to harmless. It is that a product that has
never written into a customer account can say so in one sentence, every security
review after that is shorter, and the first exception ends it.

The enforcement is not a convention. The org reader role does not grant the
permission, and a test searches the source for the API name.

## Failure behaviour

A quota Meter cannot measure can still have a request tracked against it. The two
halves of this feature are independent, and a reader whose quota is unmeasurable
still needs to know whether their increase was approved.

A `DENIED` request is shown, not hidden. It is the status a product is most tempted
to bury and the one most worth acting on.

## Security considerations

`quota_request` is read only in the strongest sense available: there is no
application write path to it, and the IAM policy that would permit the underlying
call does not grant it.

## Interface

`GET /governance/quotas/requests`, and a drafted increase on each quota's own screen
with a sentence saying Meter will not submit it and why.

## Not doing

**Submitting anything.** See above, and see P5 spec section 6 for the argument
rather than the conclusion.

**The Quota Request Template.** Also a write. Meter renders the template it would
set and does not set it.

If enough people ask for submission, that is a decision to reopen with an ADR
superseding constraint 6, not a thing to slip in.
