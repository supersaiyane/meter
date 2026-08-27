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
