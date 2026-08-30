# Runbook: API server errors

Covers `meter-<env>-api-5xx`. Server errors above 1 percent of requests over 5
minutes.

**Why this pages.** For an ordinary reason, unlike the other two paging alerts.
The product is unavailable or wrong for a fraction of its users and no other
alarm will catch it.

## Step 1: is it the database

By far the most common cause, because the API refuses to answer rather than
answer wrongly when it cannot read.

```bash
curl -s "$METER_URL/healthz" | jq '{status, database_reachable}'
```

`database_reachable: false` means Aurora is unreachable, not slow. Check the
cluster and the connection alarm. If connections are at the ceiling, a collector
is leaking sessions and the fix is to restart the worker service, not the API.

`status: degraded` with `database_reachable: true` means collection is stale.
That is the collection stalled alarm's problem, not this one, and it does not
cause 5xx.

## Step 2: is it one route

```
fields @timestamp, request_id, status, path, error_type
| filter status >= 500
| stats count() by path
| sort by count() desc
```

Keep the window under 24 hours. FEAT-014 applies to Meter's own queries first.

A single path is a bug in that route. Every path is the database, the scope
resolver, or the deploy.

## Step 3: is it the deploy

```bash
aws ecs describe-services --cluster meter-<env> --services meter-<env>-api \
  --query 'services[0].deployments[].{status:status,desired:desiredCount,running:runningCount,rollout:rolloutState}'
```

The service has a deployment circuit breaker with rollback enabled, so a broken
image should already have rolled itself back. If `rolloutState` is
`IN_PROGRESS` and has been for a while, the new tasks are failing their health
check, and the previous task definition is still serving. That is the system
working.

To roll back deliberately, change `image_tag` to the previous commit sha and
apply. Terraform owns the task definition, so a rollback is an apply and not an
`aws ecs update-service`. This is also why `image_tag` is never `latest`: there
would be no way to name the previous image.

## Step 4: a scope violation

```
fields @timestamp, request_id, @message
| filter @message like /a read was attempted without a scope/
```

`ScopeViolationError` returns a 500 deliberately. It is a programming error
rather than a client error, and the response says nothing useful on purpose
while the log carries the detail. If this is the cause, the correct action is to
roll back rather than to investigate in production: a route that reached the
repository without a scope is a route that might have read out of scope data,
and the second enforcement point is what stopped it.

Record it as an issue in `tasks/ISSUES.md` at CRITICAL, whatever the outcome.

## Closing it

The alarm clears on its own once the error rate falls. If the cause was a
deploy, the commit that caused it should be reverted rather than left in the
history with a rolled back tag, so the next deploy from `main` does not
reintroduce it.
