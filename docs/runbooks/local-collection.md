# Watching collection on the local stack

How the local stack collects, and how to watch each step. TASK-P12-005, FEAT-079.

## What runs, and what is fake

`make up` starts the same dispatcher and worker a deployment runs, from the same image, on the
fakes instead of AWS. The image carries no fake, ADR-0022; `docker-compose.yml` mounts
`finops_fakes` from this checkout and starts `python -m finops_fakes.dispatcher` and
`python -m finops_fakes.worker`, which run the production processes on the fake composition. The
queue is LocalStack's SQS, made when LocalStack starts by
`docker/localstack/ready.d/10-meter-queues.sh`: `meter-ingest`, and `meter-ingest-dlq` after three
receives, as the hub's queue is shaped.

Nothing in this stack calls AWS. Every figure a collector writes here comes from a fake.

## Run it

1. `make up` starts the stack, migrates the database and runs one dispatch. On an empty database
   that dispatch finds no tenant and sends nothing.
2. `make seed` writes the demo tenant, its accounts and its schedule.
3. `make dispatch` publishes the demo tenant's due collectors. A collector that succeeded within
   its cadence is not due, so a second dispatch soon after the first publishes nothing, and its
   summary says so: `"published": 0`.

## Watch each step

Both processes log one JSON object per line, `finops_core/logs.py`, with each unit's collector,
scope and run as keys. The dispatcher runs in a container that is removed when it exits, so its
summary is the last line `make dispatch` prints, with `tenants`, `published`, `deduplicated` and
`failed_tenants`:

```bash
make dispatch
```

The worker, as it claims, runs and settles each unit:

```bash
docker compose logs -f worker
```

How many units are waiting, and how many are being run:

```bash
docker compose exec localstack awslocal --region eu-west-1 sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/meter-ingest --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

The runs the ledger recorded, newest first:

```bash
docker compose exec postgres psql -U meter -d meter -c "SELECT collector, scope_key, status, started_at, finished_at, error_type FROM ingest_run ORDER BY started_at DESC LIMIT 20"
```

The failures recorded against a scope, which the freshness screen shows:

```bash
docker compose exec postgres psql -U meter -d meter -c "SELECT collector, scope_key, error_type, occurrences, last_seen_at FROM sync_error ORDER BY last_seen_at DESC LIMIT 20"
```

Anything the worker could not read, moved after three receives:

```bash
docker compose exec localstack awslocal --region eu-west-1 sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/meter-ingest-dlq --attribute-names ApproximateNumberOfMessages
```

## Stop it

`docker compose stop worker` sends SIGTERM. The worker finishes the unit in hand and stops; the
units it had not started stay on the queue and are run when it starts again, after the queue's
900 second visibility timeout.

## When something looks wrong

| Seen | Meaning |
| --- | --- |
| The dispatcher exits 78 | A setting is missing. The log names it; `.env` is made from `.env.example` |
| The dispatcher exits 1 | A tenant failed and the others were dispatched. The log has the traceback |
| Units wait and nothing runs | The worker is not running. `docker compose ps worker` |
| A unit is in the dead letter queue | It could not be decoded, or failed three times. The worker log names it |
| A run is FAILED with a typed cause | Read `error_type` and `sync_error`; a fake plants some failures on purpose |
