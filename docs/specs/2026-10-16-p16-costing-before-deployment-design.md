# P16 Costing before deployment: design specification

Date: 2026-10-16
Status: Chosen by the owner on 2026-10-16 as the next build, proposal 6 of `next-in-scope.txt`, with OPEN-45 answered the same day. OPEN-44, how a plan reaches Meter, is held by the owner and blocks TASK-P16-010 alone; every other task is in build
Sub project: P16
Features: FEAT-095, FEAT-096, FEAT-097, FEAT-098
Depends on: P9 for the price catalogue, P4 for FEAT-057's map of what Terraform manages, P15 for the GitHub App and the repository mapping, P10 for the bill in FOCUS 1.4, P12 for the composition every new collector joins, P13 for ADR-0036's worker only route to the internet. Proof against a real repository waits on a GitHub App installation, ISS-300, and on OPEN-44

## 1. Purpose

A change to infrastructure is cheapest to question before it is applied, and today nobody can see
what it will cost until the bill arrives a month later. The engineer writing the change does not
know the price of an `r6i.4xlarge`; the reviewer does not know either; FinOps finds out from the
invoice.

P16 prices a Terraform plan in its pull request. The organization's own pipeline runs `terraform
plan` and `terraform show -json`, as it already does; Meter never runs Terraform. Meter prices
every resource the plan creates, changes or destroys from P9's catalogue, and writes one comment on
the pull request with the monthly change, a line per resource, and every resource it could not
price with the reason. A month after the change is applied, Meter compares the estimate with the
bill for each resource the plan created, and publishes how close its estimates come. The estimate is
modelled; the bill is measured; every figure says which it is.

## 2. Definition of done

- A plan as `terraform show -json` writes it is reduced on arrival to what is priced: each managed
  AWS resource change, its address, type, actions and Region, and the attributes that set its
  price, before and after. Nothing else of the plan is stored.
- Each resource change of a type the catalogue prices is priced at the newest catalogue version for
  its service and Region: on demand, list price, 730 hours a month. A resource of any other type,
  in a Region the catalogue does not hold, or with a priced attribute Terraform knows only after
  apply, is listed with its reason and no figure, never as zero.
- One comment per pull request and folder carries the estimate and is edited in place when a plan
  for a newer commit arrives. A plan for an older commit never overwrites a newer one. The comment
  quotes list prices only, never a figure from the bill.
- Once a merged pull request's created resources are seen in the mapped state, each is compared
  with thirty billed days at list cost, effective cost beside it, and the accuracy is published by
  resource type. A resource that cannot be compared says why.
- A plan reaches Meter from the repository's pipeline by the route OPEN-44 chooses.

## 3. Out of scope

- Running Terraform, reading state through Terraform, or holding a credential for a member
  account. The pipeline plans; Meter reads its output. Constraint 6.
- Blocking a merge. The comment informs; it fails nothing, OPEN-45.
- Usage priced from history: data transfer, requests, Lambda invocations, NAT gateway bytes, S3
  storage. Each is listed as usage based and not priced.
- Commitment discounts in the estimate. The estimate is at list price and says so; the comparison
  shows effective cost beside list cost.
- Comparing a change to an existing resource, or a destroy, with the bill. A plan's creations and
  replacements are compared; FEAT-029 measures a change a recommendation drove.
- An autoscaling group's instances, which come from a launch template the plan references by an
  identifier known only after apply. Listed as not priced, with that reason.
- GitLab, Atlantis and Terraform Cloud. The route OPEN-44 chooses decides which pipelines can hand a
  plan over; posting the comment is GitHub's, P15.

## 4. The gap, measured on 2026-10-16

| What | Today | Measured or modelled |
| --- | --- | --- |
| Plans Meter has priced | 0; nothing reads a plan | Measured, from the code |
| Services the catalogue prices | 5: EC2 instances with EBS, RDS, ElastiCache, Redshift, OpenSearch | Measured, `SERVICES` in `finops_ingest/collectors/price_catalog.py` |
| Regions the catalogue holds | Every commercial Region, polled every 8 hours | Measured, P9 spec section 14 |
| Estimates compared with a bill | 0 | Measured, from the code |
| Callers the API accepts other than a signed in person | None; `finops_api/identity/session.py` signs sessions for people | Measured, from the code |
| Cost at AWS of pricing and comparing | Nothing new: the catalogue and the bill are already read | Modelled |

## 5. Decisions

### 5.1 How a plan reaches Meter, OPEN-44, held by the owner

Three routes, raised on 2026-10-16 and held by the owner the same day:

1. **The worker reads it.** The pipeline uploads the plan as a workflow artifact named
   `meter-plan`; the worker, through P15's GitHub App with `actions: read` added, finds it on each
   open pull request in a mapped repository. No new caller of the API and no secret in the
   pipeline; GitHub Actions only; the comment within ten minutes. Recommended.
2. **The pipeline sends it, signed by GitHub.** The pipeline posts the plan to the API with the
   OpenID Connect token GitHub issues a workflow. No secret in the pipeline, but the API gains a
   second kind of caller, and the worker has to keep GitHub's signing keys in the database, since
   the API does not reach the internet, ADR-0036.
3. **The pipeline sends it with a token Meter issues.** One token per repository, stored hashed and
   revocable. Works from any pipeline; a long lived secret lives in each one.

Whichever is chosen hands the same things to the same place: the tenant, the repository, the pull
request's number, the commit the plan was made from, the folder, and the plan. The reduction in
5.2 runs on arrival, and the rest of P16 reads only what it keeps, so every task but TASK-P16-010
is built and proven with plans the tests and the demo lay down directly.

### 5.2 A plan is reduced on arrival and never stored whole

`terraform show -json` writes every value Terraform knows, the ones marked sensitive included, in
plain text: user data, passwords, connection strings, policy documents, tags, and the prior state.
Corrected on 2026-10-16 by TASK-P16-002 from Terraform's own documentation; this section first said
sensitive values were left out. Meter keeps, per managed resource change from the `hashicorp/aws`
provider, the address, the type, the actions, the Region, and the attributes its pricing reads,
before and after, with the names of those Terraform knows only after apply. A priced attribute its
author marked sensitive is named and not kept, and its line goes unpriced. The reduction is a pure
function in `finops_query`. It refuses with the reason a document that is not a plan, a
`format_version` whose major version is not 1, and a plan over 50 MiB, modelled as ten times the
largest plan Meter's own Terraform writes. Data sources, other providers, and `no-op`, `read` and
`forget` changes are dropped.

The Region of a resource is read, in order, from its own `region` argument, which version 6 of the
AWS provider added, from its availability zone, and from the provider configuration that the
resource names, a constant or a variable the plan carries. A resource whose Region none of these
gives is not priced, and says so.

### 5.3 What is priced

| Terraform type | Priced | Not priced, and listed |
| --- | --- | --- |
| `aws_instance` | The type's hourly price, Linux, shared tenancy; its root and EBS block devices as volumes | A Windows or licensed image costs more; the line says it is priced as Linux |
| `aws_ebs_volume` | Storage for every volume type; IOPS for io1 and gp3 above 3,000; throughput for gp3 above 125 MiB/s | io2 IOPS, which are priced in tiers |
| `aws_db_instance` | The class's hourly price for MySQL, PostgreSQL and MariaDB, single or Multi-AZ; storage and provisioned IOPS | Oracle and SQL Server, whose price depends on the licence; backup storage |
| `aws_rds_cluster_instance` | The class's hourly price | Aurora storage and I/O, which are usage based |
| `aws_elasticache_cluster`, `aws_elasticache_replication_group` | The node type's hourly price times the nodes | Data tiering and backups |
| `aws_redshift_cluster` | The node type's hourly price times the nodes | RA3 managed storage, usage based |
| `aws_opensearch_domain`, `aws_elasticsearch_domain` | Data, dedicated master and warm instances; EBS storage per data node | UltraWarm and cold storage beyond the instances |
| Every other type | Nothing | Named with its type and the reason: usage based, or not in the catalogue's five services |

A line for a change is its monthly figure before and after; a creation has no before, a destroy no
after, and a change the difference. The comment and the screen show the unpriced count before the
total, so a partial figure is never read as the whole.

### 5.4 The figures a line rests on

On demand, list price, 730 hours a month, in USD, at the newest catalogue version for the service
and Region when the plan is priced. Each line keeps the price identifiers and the unit prices it
used, and the version, as figures and not as references, so the catalogue pruning a superseded
price never changes a past estimate. Every figure is modelled.

### 5.5 One comment, edited in place, OPEN-45

One comment per pull request and folder, found again by a marker hidden in its text, edited each
time a plan for a newer commit is priced. A plan whose commit is no longer the pull request's head
is priced and kept, and does not touch the comment. The comment shows the monthly change, before
and after, a line per priced resource, every unpriced one with its reason, the assumptions in 5.4,
and the catalogue version and date. It quotes list prices, which AWS publishes, and never a figure
from the bill, so a reader of the repository learns nothing of the organization's spend. Posting
needs nothing beyond what P15 granted: GitHub accepts an issue comment on a pull request from an
app with Pull requests write. Answered by the owner on 2026-10-16: one comment, edited.

### 5.6 The estimate compared with the bill

For a merged pull request, the last plan priced for each folder is the one compared. When FEAT-057
first sees, after the merge, an address that plan created or replaced in the state the folder is
mapped to, the resource's identifier joins the bill as FEAT-029 joins it, `cost_focus_daily`'s
`resource_id`. The first full billed day after it was seen is skipped, as a resource's first day
is partial, and the next thirty days are the window. The window's list cost, scaled to 730 hours,
is set against the line's monthly estimate; effective cost is shown beside it, since commitments
lower it and the estimate does not know of them.

The verdict is `WITHIN` when list cost is within 10 percent of the estimate, `ABOVE` or `BELOW`
otherwise, and `NOT_COMPARED` with its reason for a folder with no mapped state, a resource not
seen within sixty days of the merge, or a window with no billed row, typed `NoData`. A line is
judged once the bill covers its window, and again on each later run, so a restated bill restates
the verdict. Accuracy is published by resource type: lines compared, lines within, and the median
absolute percentage error.

### 5.7 The worker prices and posts; the API reads

The `plan_estimates` collector prices each plan recorded, writes the estimate, posts or edits the
comment, and follows the pull request's state through P15's tracker. Only the worker reaches
GitHub, ADR-0036. Pricing reads the catalogue from the database, so it could run anywhere, and
runs in the worker so that an estimate and its comment are written by one run.

### 5.8 Payer wide

A plan names no account until it is applied: a resource's account is decided by the provider's
credentials in the pipeline, which the plan does not carry. Plans, estimates and comparisons are
payer wide, ADR-0025, read by a person whose scope is the organization. Engineers see their
estimate in their pull request.

## 6. Data model

New tables, each with `as_of` and `collected_at`, constraint 10, payer wide:

- `terraform_plan`: one per plan received: the repository, the pull request, the commit, the
  folder, the state the folder is mapped to where one is, the route it came by, its status,
  `RECEIVED`, `PRICED` or `REFUSED`, and a refusal's reason. `as_of` is the plan's own timestamp
  where it carries one. Unique by repository, pull request, folder and commit.
- `planned_change`: one per resource change kept, 5.2: the address, the type, the actions, the
  Region, the priced attributes before and after, and the names of those unknown until apply.
- `plan_estimate`: one per plan priced: monthly before, after and change, lines priced and not
  priced, the comment's identifier and link, when it was written, a failure's typed cause, and the
  pull request's state.
- `plan_estimate_line`: one per resource change: monthly before and after, the components with
  their unit prices, price identifiers and version, or the reason it is not priced. A check holds
  that a line not priced carries no figure, and that a priced one carries at least one.
- `estimate_comparison`: one per line compared: the resource's identifier, the window, the
  estimate, list and effective cost scaled to a month, the variance, the verdict or the reason, and
  the bill's `as_of`. A check holds that `NOT_COMPARED` carries a reason and no variance.

Kept for 400 days, then pruned by the retention collector: the comparison needs sixty days after a
merge, and a year of accuracy is what is published.

## 7. Collectors and cadence

| Collector | Unit | Cadence | Reads and writes |
| --- | --- | --- | --- |
| `plan_estimates` | organization | every 10 minutes | Prices each plan received, writes its estimate, posts or edits its comment, and follows its pull request |
| `estimate_comparison` | billing | daily | Compares each merged pull request's created resources with the bill once their window is billed, and restates the verdict as the bill is restated |

Both join the registry, both compositions, the fakes, and a migration installing their cadence for
existing tenants. Neither costs anything new at AWS: the catalogue and the bill are already read,
and GitHub's API is free within its rate limit, modelled.

## 8. Interface

- `GET /v1/estimates`: the plans priced, newest first, by repository and pull request, with their
  totals, the comment's link and the pull request's state. Global scope.
- `GET /v1/estimates/{plan_id}`: its lines, components and reasons, and the assumptions. Global
  scope.
- `GET /v1/estimates/accuracy`: by resource type and in all, lines compared, lines within 10
  percent, and the median absolute percentage error, each labelled modelled against measured.
  Global scope.
- The route OPEN-44 chooses for a plan's arrival, TASK-P16-010.
- A screen, Estimates, at `/cost/estimates`: the plans priced, one's lines, and the accuracy.

Every response carries `as_of` and `collected_at`, constraint 10. The MCP facade gains the read
routes, ADR-0009.

## 9. Testing

The reduction is tested without a database on plans written by Terraform 1.x for every priced type,
including values unknown until apply, resources inside modules, `count` and `for_each` instances,
an aliased provider, and a Region given each of the three ways; a test plants a value in every
field the reduction drops and finds it in no stored column. Pricing is tested against a catalogue
fake built from the real price list rows P9's tests hold, for every line in 5.3 and every reason.
The comment is rendered without GitHub and posted through httpx's mock transport against recorded
response shapes: the comments listed a page at a time, the marker found, edited or written, and
each typed failure. The comparison's verdict is pure and tested at every boundary; both collectors
are tested against the database. The routes are tested for a narrowed principal refused, and the
screen has unit tests and a Playwright journey.

## 10. Risks

- Nothing reaches Meter from a real pipeline until OPEN-44 is answered and a GitHub App is
  installed, ISS-300.
- An `aws_instance` from a Windows or licensed image is understated. The line says it is priced as
  Linux.
- A plan full of usage based resources has a small priced share. The unpriced count is shown first.
- An estimate compared at list cost against a tenant whose commitments cover the resource looks
  right at list and high at effective; both are shown, and accuracy is published at list.
- A pipeline that applies days after the merge is compared from when the resource is seen, not
  from the merge, so it is compared fairly, later.

## 11. Open questions

- OPEN-44: how a plan reaches Meter, 5.1. Held by the owner; blocks TASK-P16-010 and exit criterion 6.
- OPEN-45: where the estimate shows in the pull request. Answered by the owner on 2026-10-16: one
  comment, edited in place, 5.5.

## 12. Features delivered

- FEAT-095: A Terraform plan reduced and priced from the catalogue.
- FEAT-096: The estimate as one comment on the pull request, edited in place.
- FEAT-097: The estimate compared with the bill, and its accuracy published.
- FEAT-098: A plan reaching Meter from the pull request's pipeline, by the route OPEN-44 chooses.

## 13. Exit criteria

1. A plan creating an instance, a gp3 volume, an RDS instance, an ElastiCache replication group, a
   Redshift cluster and an OpenSearch domain is priced from the catalogue, each figure the unit
   price times its quantity and 730 hours where hourly; a resource outside 5.3, in a Region the
   catalogue lacks, or with a priced attribute unknown until apply, is listed with its reason and no
   figure.
2. Nothing of a plan beyond what 5.2 keeps is stored: a value planted in every dropped field is
   found in no table.
3. A pull request has one comment per folder, edited when a plan for its head is priced and left
   alone by a plan for an older commit; it quotes list prices only.
4. A merged pull request's created resources, once seen in the mapped state, are compared with
   thirty billed days at list cost with effective cost beside it, and accuracy is published by type;
   a resource never seen is not compared, with the reason.
5. The routes and the screen show plans, lines and accuracy to a person whose scope is the
   organization, and refuse a narrowed person.
6. A plan from a repository's pipeline reaches Meter by the route OPEN-44 chooses.
