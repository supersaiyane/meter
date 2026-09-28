# ADR-0018: The threshold is zero fixable findings, not zero findings

Date: 2026-08-23
Status: Accepted
Amends: the threshold in ADR-0010. The rest of ADR-0010 stands.

## Context

ADR-0010 and `docs/05-SECURITY.md` state the policy as **zero vulnerabilities
at any severity**. TASK-P0-029 measured the candidate base images for the first
time, and the policy is undeliverable as written.

| Image | Total | Critical | High | Medium | **Fixable** |
| --- | --- | --- | --- | --- | --- |
| `python:3.12` | 13 | 0 | 3 | 8 | **0** |
| `python:3.13` | **3** | 0 | **0** | 3 | **0** |
| `node:22-dev` | **0** | 0 | 0 | 0 | 0 |
| `nginx:1.27` | 93 | **6** | 26 | 19 | 76 |
| `nginx:1.30` | **0** | 0 | 0 | 0 | 0 |
| official `python:3.12-slim` | **204** | **7** | **26** | 69 | 80 |

Three conclusions, and the third is the awkward one.

ADR-0010 was right. Minimus against the official image is 3 against 204 once
the versions are chosen by measurement, which is a factor of sixty.

**Version choice matters more than base image choice.** Moving Python 3.12 to
3.13 removes every High finding. Moving nginx 1.27 to 1.30 removes all
ninety-three. Neither move was suggested by any document, and both were found
only by scanning.

**Nothing reaches zero.** Python 3.13 carries three Medium findings in CPython
itself, none with a published fix. No rebuild cadence fixes them, because the
fix does not exist upstream yet.

So the policy as written cannot be met by any Python image that exists. A
policy that cannot be met is not a high standard, it is a rule everyone learns
to route around, and the routing around is what actually costs you.

## Decision

**The threshold is zero findings that have a published fix.**

A finding with no published fix is not a build failure. It requires an
**acceptance record**, which is a different and stronger thing than an
allowlist entry, because it must argue that the vulnerable code is not
reachable from ours.

```yaml
- id: CVE-2026-15806
  package: python-3.13
  target: base-image
  unfixable: true
  reachability: >
    Affects urllib.request.HTTPPasswordMgr and its subclasses. Meter never
    constructs an HTTPPasswordMgr and never uses urllib basic auth handling.
    Enforced by scripts/ci/check_forbidden_imports.py.
  owner: PLACEHOLDER-security
  added: 2026-08-23
  review: 2026-11-21
```

Four differences from an ordinary allowlist entry, and each closes a way the
old rule could be gamed.

1. **`reachability` is mandatory.** "We accept this risk" is not a reason.
   "This code path does not exist in our application" is.
2. **`review`, not `expires`.** An unfixable finding does not become fixable on
   a date. The date forces re-examination, not re-acceptance, and the review
   asks one question: has a fix been published yet.
3. **A reachability claim that can be enforced must be enforced.** All three
   current findings are in stdlib modules we do not import, so
   `check_forbidden_imports.py` fails the build if anyone imports them. That
   turns "we do not use it" from a claim into a fact.
4. **A fixable finding can never be accepted this way.** If a fix exists, take
   the fix. The old allowlist, with its 90 day expiry, still governs those, and
   is for genuinely exceptional cases such as a fix that breaks compatibility.

## Consequences

Positive.

- The policy is achievable, so it will be followed rather than routed around.
- It moves the pressure to where it changes outcomes: **choose the version by
  measurement**. That single practice removed 3 High and 93 findings here, more
  than any policy wording would have.
- A reachability argument is auditable. "Zero vulnerabilities" invites the
  question of how, and this answers it.

Negative.

- "Zero fixable findings" is a weaker headline than "zero vulnerabilities". It
  is also true, which the other one was not.
- Reachability assessment is judgement, and judgement can be wrong. Mitigated
  by requiring enforcement where enforcement is possible, and by the review
  date.
- Three accepted findings today will grow. If the count climbs, that is a
  signal to change base image or language version, and the review date is when
  the question gets asked.

## Alternatives rejected

**Keep "zero findings" and allowlist the three.** Rejected. It preserves a
slogan the build cannot satisfy, and the 90 day expiry would churn forever on
findings that are never going to be fixable, training everyone to renew
allowlist entries without reading them.

**Drop to "zero critical and high".** Rejected, and it is the usual answer. It
would have accepted nginx 1.27's nineteen Mediums without anyone looking, when
the actual right answer was to move to 1.30 and have none. A severity floor
lets a fixable finding through, and every fixable finding is a decision not to
take a fix that exists.

**Build our own base image.** Rejected at rung six of ADR-0013. It moves the
CVE burden onto us permanently, and we would do it worse than a team that does
only that.
