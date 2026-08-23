# ADR-0013: Seven rung ladder, with a disqualification record and a security sign off

Date: 2026-08-23
Status: Accepted
Supersedes: the ladder in ADR-0011

## Context

ADR-0011 adopted a six rung reuse ladder. ADR-0010 adopted a zero vulnerability
dependency gate. Put together they deadlock.

> The ladder says: use the existing dependency.
> The security gate says: you cannot use that dependency, it has a CVE.

With no defined escalation, the predictable outcome is the worst one: an
engineer or an agent jumps straight to writing custom code, records no reason,
and the project quietly acquires a hand rolled version of a solved problem with
no record of why.

A prior project solved this precisely. Its guide, with a seven rung ladder and
a disqualification protocol, is imported here with credit rather than
reinvented, which is rung two of the ladder applied to the ladder itself.

## Decision

**The ladder becomes seven rungs.** Start at rung one. Use the lowest rung that
solves the problem. Justify skipping each rung before moving past it.

| Rung | Meaning |
| --- | --- |
| 1 | **stdlib**, the language's built in library |
| 2 | **installed dependency**, already in `pyproject.toml` or `package.json` |
| 3 | **config**, solve it with configuration rather than code |
| 4 | **installed tool**, a CLI or service already in the stack, including an AWS service |
| 5 | **compose**, combine existing pieces |
| 6 | **fork**, fork an existing open source project and modify it |
| 7 | **custom**, write it from scratch. Last resort |

Rung four is where ADR-0006 lives: prefer Cost Optimization Hub and Compute
Optimizer over a bespoke recommendation engine. That decision is now an
instance of a general rule rather than a one off.

**When a rung is disqualified, four steps, in order.**

**Step 1. Write a Rung Disqualification Record.** No escalation without one.

```
RUNG DISQUALIFICATION RECORD
Rung:      2 (installed dependency)
Package:   example-lib 2.3.0
Reason:    CVE-2026-11111, deserialization flaw reachable from our parse path
Evidence:  https://nvd.nist.gov/vuln/detail/CVE-2026-11111
           security/reports/2026-08-23-141200/index.html
Checked by: name
Date:      2026-08-23
```

**Step 2. Exhaust the current rung first.** Before escalating, check for a
patched version of the same package, an alternative package at the same rung,
or a maintained fork. **If a same rung alternative exists, use it and do not
escalate.**

**Step 3. Escalate one rung at a time.** Skipping from rung two to rung seven is
not allowed unless rungs three to six are each disqualified with evidence.

**Step 4. An ADR for any escalation past rung two**, carrying the full
disqualification trail.

**Security sign off gate.** When the disqualification reason is a CVE or any
other security issue, the replacement rung needs a security sign off before
work starts. For a licence or performance disqualification, an architect sign
off is sufficient.

## Consequences

Positive.

- The deadlock between ADR-0010 and the reuse ladder is resolved with a defined
  path rather than left to whoever hits it first.
- "Why did you not just use the existing package" has a documented answer that
  survives the person who made the decision leaving.
- The most common wrong turn, jumping straight to custom code because a
  dependency has a CVE, is named as an anti pattern rather than discovered in
  review.

Negative.

- More paperwork on a genuinely blocked dependency. Accepted: this happens
  rarely, and the record is short.
- Rung six, forking, introduces a maintenance burden that is easy to
  underestimate. Any fork needs a named owner and a plan to upstream or retire.

## What must never happen

| Anti pattern | Correct behaviour |
| --- | --- |
| Jump from rung two to rung seven because a dependency has a CVE | Check same rung alternatives first |
| Write custom code without recording why every lower rung was disqualified | Full trail in an ADR |
| Mark a dependency disqualified with no evidence | A record with a CVE link, a licence reference, or a measurement |
| Start work before a security sign off, when a CVE was the trigger | Wait for the sign off |
| Write "rung two not applicable" without checking alternatives | Enumerate and rule out each one |

## Attribution

Adapted from the Ponytail Rung Disqualification Guide, version 1.0, in a prior
project. The seven rung structure, the disqualification record, the same rung
check and the security sign off gate are taken from it directly. Adopting a
protocol that already worked is rung two.
