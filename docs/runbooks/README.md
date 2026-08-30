# Runbooks

One per paging alert, written **with** the alert and never after. An alert
shipped without a runbook is a page that wakes someone who then has to work out
what to do.

Four alerts page, per the alert table in `docs/10-OBSERVABILITY.md`. This file
and the plan both used to say two, which was a misreading of the sentence below
that table: two of the four are *unusual*, which is not the same as two being
the total. ISS-121.

| Alert | Pages because | Runbook |
| --- | --- | --- |
| Collection stalled | Silent staleness is the failure mode of this product | `collection-stalled.md` |
| Collection stalled, widespread | The same failure at a scale that means the hub, not an account | `collection-stalled.md` |
| API 5xx | Ordinary. The product is unavailable or wrong for some users | `api-5xx.md` |
| Platform cost anomaly | A FinOps tool that quietly becomes expensive has no standing left | `platform-cost-anomaly.md` |

Two runbooks cover three alarms, because the widespread stalled alarm is the
same failure as the single scope one and its first diagnostic step is telling
them apart. Splitting them would mean two files whose first paragraph is the
same question.
