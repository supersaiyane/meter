# Runbook: collection stalled

Covers two alarms, `meter-<env>-collection-stalled` and
`meter-<env>-collection-stalled-widespread`. They are the same failure at two
scales and the first question splits them.

**Why this pages.** Silent staleness is the failure mode of this product. The
API keeps answering, the screens keep rendering, and the numbers are last
week's. Nothing else in the system notices, which is exactly why this is a page
and not a ticket.

## First, which one is it

| Alarm | Meaning | Where to look |
| --- | --- | --- |
| `collection-stalled` | At least one collector and scope pair is behind | Individual accounts |
| `collection-stalled-widespread` | Over 5 percent of scopes at once | The hub, not the accounts |

If the widespread alarm is in ALARM, do not chase individual accounts. It is
almost always one of three things and all three are central.

## Step 1: read the typed cause

Never start from the logs. Every failure is already classified.

```sql
SELECT collector, scope_key, error_type, detail, remediation, occurrences, last_seen_at
FROM sync_error ORDER BY last_seen_at DESC LIMIT 50;
```

`error_type` is one of six values and each one means a different action.

| `error_type` | What happened | Do this |
| --- | --- | --- |
| `AccessDenied` | The collector role in the member account is gone, renamed, or its trust policy no longer names the hub role | Go to step 2 |
| `Throttled` | AWS is rate limiting us | Go to step 3 |
| `NotOptedIn` | The account never had the service enabled. Not a fault | Go to step 4 |
| `NoData` | The source has nothing for that window. Not a fault | Go to step 4 |
| `Timeout` | The call did not return in time | Go to step 3 |
| `Unknown` | Nothing else matched, which usually means AWS changed a payload | Go to step 5 |

`NoData` is the one that most often looks like a fault and is not. It renders as
a genuine zero rather than as a failure, and that is deliberate.

## Step 2: AccessDenied

Widespread means the hub end. A single account means that account.

```bash
aws sts get-caller-identity
aws secretsmanager get-secret-value --secret-id meter/external-id --query SecretString
```

Then confirm the member role still exists and still trusts us:

```bash
aws cloudformation describe-stack-set --stack-set-name meter-collector-role \
  --call-as DELEGATED_ADMIN
```

If the StackSet shows drift or a failed instance, the role was changed or
removed in that account. Re deploying the StackSet instance restores it. If
`aws:PrincipalOrgID` is the failing condition, the account has left the
organization, and the correct outcome is that we can no longer read it.

## Step 3: Throttled or Timeout

The collector already backs off. A sustained alarm means the backoff is not
enough, not that it is missing.

1. Check the queue depth on the service health dashboard. A deep queue with
   workers at the ceiling means too much concurrent work, not a broken account.
2. Lower `METER_WORKER_CONCURRENCY`, or lower the worker autoscaling ceiling.
3. If one collector dominates, slow its cadence. Cadence is data, not code:

```sql
UPDATE collector_schedule SET cadence_seconds = 7200,
       reason = 'Slowed <date>: sustained Throttled at hourly. See incident <id>.'
WHERE collector = '<collector>' AND tenant_id = '<tenant>';
```

`reason` is NOT NULL for this exact moment. A cadence nobody can explain is a
number nobody can safely change back.

## Step 4: NotOptedIn or NoData

Neither is a fault and neither needs a fix. If a scope is permanently in this
state, stop collecting it rather than leaving a permanent alarm:

```sql
UPDATE collector_schedule SET is_enabled = false,
       reason = 'Disabled <date>: account is not opted in to <service>.'
WHERE collector = '<collector>' AND tenant_id = '<tenant>';
```

A disabled collector is excluded from the freshness calculation, so the alarm
clears honestly rather than by being muted.

## Step 5: Unknown

`Unknown` means the payload did not match anything the parser expects, which
usually means AWS changed it. This is the only cause that needs a code change.

1. Find the run: `SELECT * FROM ingest_run WHERE error_type = 'Unknown' ORDER BY started_at DESC LIMIT 5;`
2. The log line for that `run_id` carries the metadata, never the payload, and
   never a credential. That is deliberate and it does make this step slower.
3. Reproduce against the fake provider first. If the fake still passes, the
   fixture is now wrong, and updating the fixture is part of the fix.

## Closing it

The alarm clears when the watermark advances. It does not clear because
somebody looked at it. If the underlying scope is genuinely gone, disable it in
`collector_schedule` per step 4; the alarm then has nothing to report, which is
different from being silenced.

Write a lesson in `tasks/lessons.md` if this was caused by something we did.
