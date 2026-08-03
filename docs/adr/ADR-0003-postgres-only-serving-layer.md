# ADR-0003: PostgreSQL only for the serving layer, no ClickHouse in P0

Date: 2026-08-23
Status: Accepted

## Context

Cost dashboards are read heavy and latency sensitive. The obvious instinct is
a columnar store. The confirmed scale is 50 to 300 accounts and 10 to 100 GB
of CUR per month.

## Decision

Athena and Glue over CUR 2.0 Parquet in S3 for extract and load only.
Aurora Serverless v2 PostgreSQL holds pre aggregated rollups, application
state, and the node and edge graph, and serves every interface query.

No ClickHouse, no Redshift, no Neptune in P0.

The trigger to revisit is measured, not felt: p95 dashboard latency above
1.5 seconds on the pre aggregated rollups.

## Consequences

Positive.

- One database to operate, back up, secure and reason about.
- Pre aggregated rollups at day, account, service, region, resource,
  charge category and tag grain are small enough that PostgreSQL is
  comfortable at this scale.
- Lower platform cost, which matters because Meter meters itself and the
  front page shows that number.

Negative.

- If scale grows past the assumption, notably a move to multi payer or
  thousands of accounts, a columnar serving layer will be needed. The rollup
  tables are designed to be portable to one.

## Alternatives rejected

**Athena directly behind the interface.** Rejected outright. Athena bills 5 USD
per terabyte scanned. Putting interactive dashboards on it recreates, inside
the FinOps tool, the exact failure the product exists to prevent.

**ClickHouse from day one.** Rejected as premature. A second engine adds
operational surface, a second security boundary and a second failure mode, in
exchange for latency headroom that is not yet needed.
