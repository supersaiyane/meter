# Runbook: platform cost anomaly

Covers `meter-<env>-platform-cost-anomaly`.

**Why this pages.** Meter is doing to itself the thing it exists to prevent. A
FinOps tool that quietly becomes expensive has no standing left to comment on
anyone else's bill, so this is a page rather than a ticket, and it is not
downgraded when it is inconvenient.

The alarm is an anomaly band rather than a fixed number, because Meter's cost is
expected to grow with the number of accounts it reads. A fixed threshold would
be wrong within a quarter and would then be raised instead of investigated.

## Step 1: which module

The platform cost screen answers this, and so does the API:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$METER_URL/api/v1/platform/cost" | jq '.data | group_by(.module)'
```

Cost that carries no `finops:module` tag appears under `unallocated`. A large
and growing `unallocated` is itself the finding: something was created without
the tag, and self metering reports nothing for it rather than failing, which is
the worst kind of broken.

## Step 2: the three usual causes, in order of likelihood

**Query volume.** Athena scanned bytes and `GetMetricData` calls are the two
lines that move fastest, because both are billed per unit of work rather than
per hour.

```bash
aws cloudwatch get-metric-statistics --namespace AWS/Usage \
  --metric-name CallCount --dimensions Name=Service,Value=CloudWatch \
    Name=Type,Value=API Name=Resource,Value=GetMetricData \
  --start-time "$(date -u -v-7d +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --period 86400 --statistics Sum
```

`METER_GETMETRICDATA_BATCH_SIZE` is 500, the API maximum, because
`GetMetricData` is billed per metric requested. If it has been lowered for
debugging and left there, the bill is roughly the inverse of the change.

**A cadence change.** Someone slowing a collector reduces cost; someone speeding
one up multiplies it by the same factor.

```sql
SELECT collector, cadence_seconds, est_cost_per_run, reason, updated_by, updated_at
FROM collector_schedule ORDER BY updated_at DESC;
```

`est_cost_per_run` is what makes this a one line diagnosis. It is modelled, not
measured, and the measured figure arrives in the next day's report, which is the
point of metering ourselves.

**Aurora scaling.** A runaway query scales the cluster to
`database_max_capacity` and holds it there. Performance Insights, at the free
seven day tier, names the query.

## Step 3: if it is none of those

A retry storm produces cost without producing throughput, so compare the run
count against the items written. Equal cost with fewer items means work is being
repeated.

```sql
SELECT collector, count(*) AS runs, sum(items_written) AS items,
       count(*) FILTER (WHERE status = 'FAILED') AS failed
FROM ingest_run WHERE started_at > now() - interval '2 days'
GROUP BY collector ORDER BY runs DESC;
```

## Closing it

Do not raise the threshold. The band adapts on its own as the account count
grows, and raising it converts the one alert that keeps this product honest into
a formality. If the new level of spend is correct and permanent, say so in
`docs/04-DEPLOYMENT.md` alongside the estimate it now contradicts, so the next
person to read that table is not misled by it.
