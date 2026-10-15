# ADR-0038: Meter may merge a pull request it opened for a reversible fix, under the tenant's policy

Date: 2026-10-15
Status: Accepted. The owner chose it on 2026-10-15, OPEN-41, for P15
Supersedes: FEAT-040's rule that a fix is never merged automatically. Constraint 6 is unchanged

## Context

FEAT-040, P7, authors a fix as a Terraform pull request and states that it is never merged
automatically, and `tests/contract/test_no_llm_writes.py` holds that no production module names a
merge, an approval or an apply. Every fix it authors is a deletion, for which that rule is right: a
deleted volume or snapshot cannot be brought back, and only a person can know nothing still needs
it. Proposal 4 of `next-in-scope.txt` asks for graded autonomy: fixes that are low risk merged
under policy, with the saving measured before and after. P15 adds the first fix that loses nothing
if it is wrong, a volume moved from gp2 to gp3, which a second change moves back.

## Decision

1. A class of fix is reversible when undoing it loses nothing. The set is in the domain, not in
   configuration, and holds `EBS_GP2_TO_GP3` alone. Adding a class to it is a change to this record.
2. Each tenant has a merge policy naming which reversible classes Meter may merge. It starts empty,
   is changed by a person whose scope is the organization with a reason, and every change is
   audited. A database check refuses any class outside the reversible set.
3. Meter merges only a pull request it opened, of a class the policy names, and only when GitHub
   reports it mergeable with every required status check passed and every required review given.
   It merges through GitHub's own merge endpoint, so the repository's branch protection applies.
4. Meter never approves a pull request, never merges a deletion, never merges a pull request a
   person opened, and never applies anything. The organization's pipeline applies what is merged.
5. One function performs the merge. The contract test is changed to allow the merge call in that
   function alone and to keep refusing approval, applying and every tool that changes a cloud.
6. A feature flag, `pull_request_merge`, turns every merge off at once.

## Why constraint 6 still holds

Constraint 6 forbids a write API call into a member account. A merge is a write into a repository
the organization owns, through credentials it issued to an app it installed, and the change reaches
an account only through the organization's own pipeline, its own review rules and its own apply.

## Alternatives

- **Never merge.** Keeps FEAT-040's rule; every fix waits for a person. Rejected by the owner: the
  low risk fixes are the ones worth not waiting for.
- **Merge reversible fixes and deletions.** Saves more, but a wrong deletion loses data. Rejected
  by the owner.
- **Merge without waiting for the repository's checks and reviews.** Would make Meter the only
  gate on a change. Not offered.

## Consequences

- Meter holds its first write credential: a GitHub App installation token, minted for one request
  from a key only the worker reads, valid for an hour, never stored.
- Every merge is a recorded step with the policy that allowed it, and FEAT-029 measures each fix's
  saving from the bill afterwards, as for every recommendation marked done.
- Nothing here has been merged against a real repository. The first waits on an app installation.
