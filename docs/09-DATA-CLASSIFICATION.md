# Data classification and retention

Last updated: 2026-08-23
Update trigger: any new table, any new column holding data about a person
Closes: AUDIT-001 finding A001-F12, ISS-056

The audit found that the schema already stores personal data with no
classification, no retention period and no erasure path. This document fixes
that before there is data in it, which is the only cheap moment to do it.

## Classes

| Class | Definition | Handling |
| --- | --- | --- |
| **P** Personal | Identifies or relates to an identifiable person | Minimise, retain by policy, erasable on request, never in a log |
| **C** Confidential | Commercially sensitive to the organization | Scope filtered, encrypted at rest, audited on read |
| **O** Operational | Meter's own running state | Retained for operations, no personal data |
| **U** Public | Nothing sensitive | No constraint |

## Every table, classified

| Table | Class | Contains | Retention | Erasable |
| --- | --- | --- | --- | --- |
| `tenant` | O | Organization name | Life of the tenant | With the tenant |
| `principal` | **P** | `subject`, `display_name`, `email`, `last_seen_at` | 90 days after last sign in, then anonymised | **Yes** |
| `principal_scope` | **P** | Which accounts a named person could see | Expiry driven, hours. It is a cache | Yes, immediate |
| `cloud_account` | **P** and C | Account identifiers, names, and `email`, the AWS **account root email address** | Life of the account plus 13 months | The `email` column only |
| `org_node` | C | Organization structure | Current state only, rebuilt hourly | Not applicable |
| `cost_focus_daily` | **C** | Resource level spend for the whole organization | **37 months**, then aggregate and drop line items | Not applicable |
| `cost_provider_extra` | C | Provider specific billing fields | Same as its parent fact | Not applicable |
| `platform_cost` | O | Meter's own cost by module | 37 months | Not applicable |
| `ingest_run`, `ingest_watermark` | O | Collection state | 90 days | Not applicable |
| `sync_error` | O | Typed failures and remediation text | 90 days | Not applicable |
| `collector_schedule` | O | Cadence, reason, `updated_by` | Life of the tenant | `updated_by` on request |
| `audit_event` | **P** | Who read what, when, and the scope evaluated | **13 months**, immutable within that window | **No.** See below |
| `grafana_instance` | O | Workspace name, endpoint, account and region, and `credential_ref`, which is a Secrets Manager **name and never a value** | Life of the instance | Not applicable |
| `query_definition` | O and **P** | Query text, dashboard and panel names, and `last_editor`, which is a named person | 13 months after the query was last seen | `last_editor` on request |
| `query_finding` | O and **P** | Modelled and measured cost per query per day, and `owner_email` | **13 months**, then dropped. A cost trend older than a year has told us what it is going to | `owner_email` on request |
| `folder_team_map` | **P** | `owner_email`, `team` and `updated_by`, all entered by a person | Life of the mapping | **Yes** |
| `enforcement_action` | **P** | `principal_arn`, which identifies a role and often a person, and what was done to them | **13 months**, immutable within that window. It is the record of a control applied to somebody | **No.** Same argument as `audit_event` |
| `remediation_change` | O and **P** | The before and after of a change, and `applied_by` | 13 months. `before` is the undo and outlives the change it reverses | `applied_by` on request |
| `quota_usage` | C | Service limits and how much of each an account uses, which is the shape and the scale of somebody's estate. No personal data: a quota belongs to an account, never to a person | Current state only. Each run replaces the row, because a limit nobody raised is the same fact today as it was yesterday | Not applicable |
| `quota_request` | C | An increase somebody asked AWS for, what they asked for, and whether it was granted. `submitted_by_meter` is always false | Life of the request. A denial is the part worth keeping | Not applicable |
| `quota_request_history` | C | Every status a request passed through, and when | Life of the request | Not applicable |
| `assistant_exchange` | **P** and C | The question a named person typed, with any secret already replaced by the name of the rule that found it, and the answer, refusal or failure, the tool calls, the tokens and the modelled cost | **Not decided**, OPEN-14. No retention job reads it | **Not yet.** `erase_principal` does not reach it, ISS-226 |
| `redaction_event` | **P** | Which rule fired on whose question and what was done. Never the secret, its hash, its position or its length | **Not decided**, OPEN-14 | **Not yet**, ISS-226 |
| `report_run` | **P** and C | Who made which export of which view, under which scope, with how many rows and bytes. Never the file, its rows or its figures | **Not decided**. No retention job reads it, ISS-249 | **Not yet.** `erase_principal` does not reach it, ISS-249 |
| `report_schedule` | **P** and C | Who scheduled which view and route, how often, and the people it renders for, by their identifiers. Never a figure | **Not decided**. No retention job reads it, ISS-256 | **Not yet.** `erase_principal` does not reach it, and a person erased would still be named in other people's recipient lists, ISS-256 |
| `saved_view` | **P** and C | Who saved which screen and query under what name, and whether they shared it with the tenant. Never a figure the screen showed | **Not decided**. No retention job reads it, ISS-255 | **Not yet.** `erase_principal` does not reach it, and erasing a shared view takes it from everyone it was shared with, ISS-255 |
| `team_digest` | C | A week of spend for one team or the whole payer, as prose and citations. No personal data: the team is a cost allocation label | **Not decided**, OPEN-14 | Not applicable |
| `billing_period` | C | Which months the payer has been invoiced for. No personal data | Life of the tenant. A month is closed once and stays closed | Not applicable |
| `invoice_detail` | **C** | Every invoice and credit memo issued to the payer, its amounts before and after tax, and the entity that issued it. Payer wide, ADR-0025. No personal data | **37 months**, as `cost_focus_daily`, because an invoice is compared with those rows | Not applicable |
| `price_list_version`, `price` | U | AWS's published prices, every term, per service, Region and version. Nothing of the tenant's, and no personal data | Until superseded; how many versions are kept back is decided with TASK-P9-004 once the row count is measured | Not applicable |
| `instance_type_spec`, `volume_type_spec` | U | AWS's own descriptions of its instance and volume types | Current state, replaced each run | Not applicable |
| `recommendation_option` | C | Every target a provider ranked for a finding about the tenant's own resources, with the catalog price each quotes or the reason it has none, TASK-P9-006 | Replaced with each read of its recommendation; kept while the recommendation is | Not applicable |
| `resource_owner` | C and **P** | Each resource's suggested owners, from the service catalogue, its tags and the event that created it, FEAT-077; a creator is a named person or a pipeline's role | Tag and catalogue rows replaced by each daily run, a row a source no longer reports removed; a creator's row kept, since it cannot change | A PERSON row on request |
| `creator_lookup` | C | Which resources CloudTrail's event history was asked who created them, and whether it found the creator or the resource is older than the history, FEAT-077; it holds no name, the name is in `resource_owner` | Kept, a resource is asked once, so a PERSON row deleted on request is not read back | Nothing personal |
| `savings_credit` | C and **P** | Each verified saving credited to the recommendation's owner, the team named for its resource and the person who closed it, FEAT-078; the saving is measured | Kept while the saving verifies; withdrawn when it no longer does | The owner and closer on request |
| `savings_credit_month` | C | Each closed month after a credited saving verified, held, regressed or unobserved, with its measured cost and saving, FEAT-078; it holds no name | Judged again each daily run; removed with its credit or after a regression | Nothing personal |
| `spot_price`, `spot_price_daily` | U | AWS's published spot prices, the latest per pool and each day's low and high | The latest replaced each run; the daily rows **90 days**, OPEN-18 | Not applicable |

### The account root email address

`cloud_account.email` is the AWS account root email. It is personal data, it
frequently identifies a named individual, and it arrives whether we want it or
not because `organizations:ListAccounts` returns it.

**Decision: do not store it.** No feature reads it. The tree is keyed on
account identifier, and `role_health` carries the operational signal. Storing
personal data that nothing consumes is the easiest kind of exposure to avoid,
and the cheapest moment to avoid it is before the column has data.

The column is **removed from the schema**. If a future feature genuinely needs
to contact an account owner, that is a new decision with its own ADR, and the
right shape is almost certainly a contact reference resolved at send time
rather than a stored copy.

### Why `audit_event` is not erasable

An erasure request cannot remove an audit record without destroying the control
it exists to provide. Deleting who read the organization's financial data, on
the request of the person who read it, is not a defensible position in a
financial services environment.

It is instead **minimised and time boxed**: it stores `principal_id`, not a
name or an email, so identifying the person requires joining to `principal`,
and anonymising `principal` after 90 days breaks that join for everything older.
The audit trail survives, the identification does not.

This is a deliberate position and should be reviewed by whoever owns data
protection before the first production deployment.

## Retention, implemented

Retention is a scheduled job, not a policy nobody runs. Nothing here is left as
"we intend to".

| Job | Cadence | Action |
| --- | --- | --- |
| `retention_principal` | Daily | Anonymise `principal` rows unseen for 90 days: `display_name` and `email` set to a tombstone, `subject` hashed. The row survives so audit joins do not dangle |
| `retention_operational` | Daily | Remove `ingest_run` and `sync_error` history older than 90 days, and `ingest_watermark` rows untouched for 90 days. A watermark is a resume point, so removing one means a scope that returns is collected from the start, which is correct for an account closed three months ago |
| `retention_audit` | Daily | Delete `audit_event` older than 13 months |
| `retention_cost` | Monthly | Aggregate `cost_focus_daily` older than 37 months to month, account, service and region into `cost_focus_monthly`, then remove the line items by dropping their partitions. Both halves are one transaction, so there is no instant at which the line items are gone and the monthly shape is not there |
| `partition_maintenance` | Daily | Create the current month plus three for `cost_focus_daily` and `cost_provider_extra`. Not an optimisation: a range partitioned table with no partition for a row rejects the row outright, so this is what makes those tables writable |
| `retention_scope_cache` | Hourly | Delete expired `principal_scope` rows |
| `retention_query` | Daily | Remove `query_finding` older than 13 months, then `query_definition` rows unseen for 13 months once no finding references them. Definitions go second, because a finding whose definition has gone is a cost with nothing to attribute it to |
| `retention_enforcement` | Daily | Delete `enforcement_action` and `remediation_change` older than 13 months. Neither is anonymised in place: an enforcement record with its principal removed cannot answer the question it exists to answer, so it is removed whole |

Each job writes an `ingest_run`, so a retention job that silently stops shows
up on the freshness screen exactly like a collector that stopped.

The cost roll up drops whole partitions rather than deleting rows. A partition
drop is one catalog operation; the equivalent delete is a scan, a mass delete
and a vacuum on the largest table in the system, inside a scheduled job's
transaction. The consequence is that the boundary is the first of the month
containing the cutoff rather than the cutoff itself, because a partition holding
even one day still inside the window cannot be removed. Those days wait for the
next run, which is why the cadence is monthly.

`retention_cost` aggregates on the same boundary it drops on. Aggregating on a
different boundary is how a month ends up counted twice or not at all.
`cost_provider_extra` has no aggregate: it holds the provider's own fields that
FOCUS has no column for, which are only meaningful against the line item they
came from, so summing them would produce a number with no definition.

**37 months** for cost data is chosen so that a full three year trend plus the
current month is always available, which is what a year on year comparison
needs. It is not an arbitrary round number.

## Erasure

A request to erase a person:

1. Anonymise their `principal` row: tombstone the name and email, hash the
   subject.
2. Delete their `principal_scope` rows.
3. Anonymise `collector_schedule.updated_by` where it names them.
4. **Do not touch `audit_event`.** The join to a name is already broken by
   step 1.
5. Record the request and its completion in the audit log.

`scripts/ops/erase_principal.py` performs all five in one transaction and
prints what it changed, including the count of audit events removed, which is
always zero and is printed rather than left to be inferred from an absence. It
is deliberately a script a person runs, not an API, because an erasure endpoint
is a deletion primitive exposed to the network.

It defaults to a dry run. The transaction is rolled back and the report printed
unless `--commit` is passed, so the answer to "what would this remove" is
obtained by running it rather than by reading it.

```bash
python scripts/ops/erase_principal.py --tenant <uuid> --principal <uuid> \
    --requested-by <operator> --request-id <ticket> --commit
```

The cadence row in step 3 keeps its change and loses only its attribution. A
cadence change is operational history rather than personal data, and removing
the row would silently reset a deliberately slowed collector back to its
default.

## What Meter deliberately does not hold

Stated so that a reviewer can confirm it quickly.

- No credentials of any kind. The ExternalId lives in Secrets Manager and the
  database stores only a reference to it, in `cloud_account.external_id_ref`.
- No S3 object contents, no SSM parameter values, no Secrets Manager values.
  The curated member policy grants none of them. ADR-0004.
- No log contents. Meter reads log group **metadata**, ingestion rate and
  retention setting, never log events.
- No end customer data of any kind. Meter reads billing and resource metadata.
- No payment instrument or bank detail. Cost figures are AWS invoice amounts.

## Encryption and access

| | |
| --- | --- |
| At rest | Aurora encrypted with a customer managed KMS key. S3 raw exports SSE KMS |
| In transit | TLS everywhere. Private subnets with VPC interface endpoints, so cross account calls do not traverse the public internet |
| Access to class P | Only the API, under a caller scope, and every read audited |
| Access to class C | Scope filtered at two independent points |
| Backups | Inherit the encryption of the source. Retention matches the table policy, so a backup does not resurrect data past its retention |

That last row matters and is easy to miss: a 35 day automated backup holding
data that policy says was deleted 30 days ago undoes the retention policy.

## Open

| Question | Owner |
| --- | --- |
| Does the organization's data protection owner accept the `audit_event` position | Pending, before the first production deployment |
| Is there a regulatory retention floor that exceeds 37 months for cost data | Pending. Financial services frequently requires 7 years for records supporting an invoice |

The second could change the cost retention materially. It is raised now rather
than discovered after 37 months of data has been aggregated away.
