# FEAT-095: A Terraform plan reduced and priced from the catalogue

| Field | Value |
| --- | --- |
| Sub project | P16 |
| Status | In build |
| Specification | [P16 spec](../specs/2026-10-16-p16-costing-before-deployment-design.md), sections 5.2 to 5.4, 5.7 and 5.8 |
| Tasks | TASK-P16-002 to TASK-P16-005 |
| Decisions | OPEN-44 |
| Issues addressed | None yet |
| Refresh cadence | Every 10 minutes |

## What it does

Reduces a plan, as `terraform show -json` writes it, to each AWS resource change and the attributes that set its price, and prices every change of a type the catalogue sells: instances and their volumes, EBS volumes, RDS, ElastiCache, Redshift and OpenSearch. Each line is a monthly figure before and after, or the reason it has none.

## Why it exists

Proposal 6 asks for the cost of a change before it is applied. The engineer and the reviewer see what a change adds to the bill while it is still a pull request, and FinOps stops learning of it from the invoice.

## How it works

Built so far, TASK-P16-002: `reduce_plan` in `finops_query/plan_reading.py` keeps the address, type, actions, Region and priced attributes of each managed `hashicorp/aws` resource change, the names of priced attributes Terraform knows only after apply, and the names of those marked sensitive, which are never kept; the rest of the plan is dropped in memory. `PRICED` lists the attributes per type. The Region comes from the resource's own `region`, its availability zone, or the provider configuration it names, a constant or a root variable, and is None otherwise. A document that is not a 1.x plan, or is over 50 MiB, is refused with the reason. TASK-P16-003: `price_plan` in `finops_query/plan_pricing.py` prices each change at the newest catalogue version for its service and Region, read by `StoredCatalogue`: on demand, list price, 730 hours a month. An instance is its hours as Linux and its block devices as volumes; a volume is its storage, with gp3's IOPS and throughput above what it includes and io1's IOPS. A line that cannot rest on its principal part carries the reason and no figure; a secondary part left out is a note. Each component keeps its unit price, price identifier and version as figures. TASK-P16-004: `finops_query/plan_services.py` prices RDS for MySQL, PostgreSQL and MariaDB with its storage and provisioned IOPS and throughput, Aurora instances as Aurora Standard, ElastiCache clusters and replication groups by their nodes, Redshift clusters by their nodes, and OpenSearch domains by their data, master and warm nodes and the EBS storage on each data node, each asked of the catalogue by the attributes AWS's own lists tell prices apart by. Licensed engines, Aurora Serverless and usage based storage are reasons or notes. TASK-P16-005: migration 0065 keeps a plan as `terraform_plan` and its kept changes as `planned_change`, written by `finops_ingest/plan_records.py` whichever route arrives; the `plan_estimates` collector prices every plan received every ten minutes and writes `plan_estimate` and a `plan_estimate_line` per change, figures to six places, and the database refuses a line with a reason that carries a figure. Still to come: the routes and the screen, TASK-P16-008.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| A plan from the pull request's pipeline | Each plan, by the route OPEN-44 chooses | Ten minutes after it arrives |
| P9's price catalogue | Every 8 hours | Eight hours |

## Measured or modelled

Modelled: every figure is a list price times a modelled quantity, 730 hours a month where hourly.

## Failure behaviour

A resource of a type not priced, in a Region the catalogue lacks, or with a priced attribute known only after apply is listed with its reason and no figure, never as zero; a database check holds it. A plan that cannot be read is refused with the reason. One plan failing fails no other.

## Security considerations

A plan carries every value Terraform knows, the ones marked sensitive in plain text. Meter keeps only the priced attributes, never one marked sensitive, and stores no plan; a test plants a value in every dropped field and finds it in no table. Meter never runs Terraform and holds no credential for a member account. Plans and estimates are payer wide, ADR-0025.

## Interface

`GET /v1/estimates` and `GET /v1/estimates/{plan_id}`, and the Estimates screen at `/cost/estimates`.

## Not doing

Running Terraform, usage based charges, commitment discounts, or an autoscaling group's instances.
