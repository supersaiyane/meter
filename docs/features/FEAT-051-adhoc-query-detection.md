# FEAT-051: Ad hoc query detection

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | TASK-P2-026 |
| Refresh cadence | 6 hours |

## What it does

Reports the Logs Insights queries that ran in an account and belong to no dashboard panel and no alert rule, with what each one scanned, what it cost, and who ran it.

## Why it exists

Every other finding in P2 starts from something Meter can enumerate: a panel, an alert. A query somebody typed into the console or fired from a script is enumerable only after the fact, from evidence, and it is the one nobody owns. A single thirty day scan run by hand costs real money, sits on no dashboard, survives no review, and recurs whenever that person repeats it. Meter as built cannot see it at all.

It was in the prototype and reached neither the specification nor the code, which is recorded as ISS-171 and is why this document arrives after FEAT-050 rather than beside FEAT-013.

## How it works

The set difference the collector is already holding. `QueryEvidence.observations` returns every observed execution keyed by normalised query text, with runs, scanned bytes and the principal that ran it. The audit already walks the known definitions against that same dict to promote a finding from modelled to measured. Whatever is left over, observed but matching no definition, is ad hoc.

That makes this an arithmetic addition rather than a new collector. It adds no AWS call and no new permission, because CloudTrail and the query history are already read for FEAT-013.

Cost is the observed bytes at the scan price. It is measured, never modelled, because there is no definition to model from: an ad hoc query exists only in the evidence.

## What is already known

The prototype's `extract_adhoc_queries` in [the reference copy](../reference/sample_lambda.py.txt), including its decision to rank by cost then runs and to carry the log groups touched. Its report showed them in a tab of their own beside the inventory.

## Failure behaviour

Evidence that cannot be read leaves the estate modelled and reports no ad hoc queries at all. That is not the same as zero ad hoc queries, and the surface must say which of the two it means, in the way the freshness screen distinguishes never collected from current.

A query with no principal is reported as unattributed rather than dropped, because an unowned expensive query is precisely the case this feature exists for.

## Security considerations

Reports principal identifiers, which the measured overlay already reads under the same scope rules. It also reports query text written by a person, which can carry identifiers a dashboard panel would not. The text is shown to callers already entitled to the account it ran in, and to nobody else.

## Interface

The screen states what these queries cost in total, added 2026-09-27. It is the finding the screen
exists for and it was being said one row at a time, so a reader had to add the cost column up to
learn the thing the page is about.

The sentence under it keeps the judgement the total cannot make: an ad hoc query is not waste by
itself, and one running on a schedule nobody remembers setting usually is. A bare total with no
sentence would read as an accusation against every row in the table.

A new table, one row per distinct normalised query per account, region and window, and a read route beside the other query routes. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) sections 5 and 8.2.

## Not doing

Does not attribute a query to a team or a cost centre. Ownership here is the principal CloudTrail saw and nothing else, because the folder map FEAT-016 uses has nothing to say about a query belonging to no folder.

Does not remediate. There is nothing to change: the query has already run and its cost is spent. The action this feature supports is a conversation with a named person, which is why the principal matters more than the figure.
