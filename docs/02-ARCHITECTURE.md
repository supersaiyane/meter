# Architecture

Last updated: 2026-08-23

Cross cutting architecture that applies to every sub project. Sub project
specific design lives in `docs/specs/`.

## Confirmed technology choices

| Layer | Choice | Reason |
| --- | --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic | boto3 is first class, data work is native, and the existing Grafana prototype is already Python |
| Frontend | React with TypeScript, Cytoscape.js for graphs | Standard, and the topology view needs a real graph renderer |
| Compute | ECS Fargate | No cluster to manage, no 15 minute ceiling on CUR ingest at 300 accounts |
| Infrastructure as code | Terraform | Organization default, and it covers the member account StackSet |
| Application database | Aurora Serverless v2 PostgreSQL | Rollups, application state, node and edge graph |
| Analytics | Athena and Glue over CUR 2.0 Parquet in S3 | Extract and load only, not the serving path |
| Queue | SQS with a dead letter queue | Per unit of work fan out with retry |
| Scheduling | EventBridge Scheduler | Cron without a server |

Deliberately excluded for now: ClickHouse, Redshift, Neptune, Kubernetes.
At 50 to 300 accounts and 10 to 100 GB of CUR per month, pre aggregated
rollups in PostgreSQL serve the interface comfortably. Adding a second engine
now costs more than it earns. The trigger to revisit is p95 dashboard latency
above 1.5 seconds.

## Scale assumptions

| Dimension | Assumption |
| --- | --- |
| AWS accounts | 50 to 300 |
| CUR volume | 10 to 100 GB per month |
| Regions in scope | Multi region, Ireland and London named explicitly |
| Payer accounts | Single payer assumed. Multi payer is a known future change |
| Concurrent users | Tens, not thousands |

## Layering

```
finops-web        React and TypeScript
      |
      v
finops-api        FastAPI. Scope enforcement. No cloud SDK calls.
      |
      v
finops-core       Domain entities and ports. No boto3. No FastAPI. No HTTP.
      ^
      |
finops-providers  aws/ implements the ports. gcp/ and azure/ reserved.
finops-ingest     dispatcher, workers, run ledger, watermarks
```

`finops-core` importing a cloud SDK is the single failure that would turn
multi cloud into a rewrite. It is enforced by an import linter rule in
continuous integration, not by good intentions.

## Ports

A port is a runtime checkable `typing.Protocol` in `finops_core/ports/`. It holds no
implementation and imports no cloud SDK, which is constraint 1. An adapter implements a
port, and nothing in `finops_core` knows which adapter it was handed. Every port also has
an in memory implementation in `finops_fakes`, which is what lets the core and API tests
run with no AWS account. The exception is `QueryParser`, whose one implementation is pure
code in `finops_query`.

### Groups

`finops_core/ports/__init__.py` exports part of the package and sorts what it exports into
groups. `tests/core/test_ports.py` holds the membership of each group and checks every
grouped port: that it is a runtime checkable protocol, that every method names a typed cause
from `finops_core.errors`, and that no signature mentions an ARN or boto.

| Group | What belongs in it |
| --- | --- |
| `PROVIDER_PORTS` | What a cloud provider implements. `FakeProvider` in `finops_fakes/provider.py` implements every one |
| `SURFACE_PORTS` | Not about a cloud: a tool that holds saved queries which cost money when they run. `FakeQuerySurface` in `finops_fakes/surface.py` implements every one |
| `MODEL_PORTS` | The model behind the assistant, ADR-0028. Neither the cloud fake nor a query surface implements it, so it has a group of its own |
| `CATALOG_PORTS` | What AWS sells rather than an estate: its price list, its description of instance types, Savings Plans rates and spot prices, P9. Their fakes are in `finops_fakes/catalog.py` |
| `OWNERSHIP_PORTS` | Where an estate names a resource's owners beyond its tags: the service catalogue and who created it, P11. `FakeServiceCatalogue` and `FakeResourceCreators` in `finops_fakes/ownership.py` implement them |
| No group | Every other protocol in the package. Each is imported from its own module, and the per port checks in `tests/core/test_ports.py` never reach it, ISS-239 |

### Every port

Modules are in `finops_core/ports/`. Implementations are in `finops_providers/` unless the
path names another package. Fake only means nothing outside `finops_fakes` implements the
port.

| Port | Module | Group | Responsibility | AWS implementation |
| --- | --- | --- | --- | --- |
| `AccountDiscovery` | `accounts.py` | Provider | Read which accounts exist and how the organization arranges them | `aws/accounts.py` `AwsAccountDiscovery`, over AWS Organizations |
| `ContainerSource` | `containers.py` | Provider | Read the clusters in an account and region and what runs on them, and what each workload asked for against what it used | `aws/container_insights.py` `ContainerInsightsSource`, over CloudWatch Container Insights |
| `CostExport` | `cost.py` | Provider | Find the billing export and read charge rows out of it | `aws/cur.py` `AthenaCostExport`, over Data Exports CUR 2.0 in S3, read through Athena |
| `CredentialBroker` | `credentials.py` | Provider | Produce a scoped session for a target account | `aws/credentials.py` `AwsCredentialBroker`, STS AssumeRole with the ExternalId held in Secrets Manager |
| `EntitlementResolver` | `identity.py` | Provider | Turn a principal into the scope it may read | None. `finops_api/identity/local_config.py` `LocalConfigIdentityProvider` reads people from a file and never runs in production |
| `IdentityProvider` | `identity.py` | Provider | Turn a credential a caller presents into a principal | None. The same `LocalConfigIdentityProvider` |
| `MetricSource` | `metrics.py` | Provider | Read observed values for a resource over a window | Fake only. `aws/waste.py` `CloudWatchWasteMetrics` has `read_many` over CloudWatch `GetMetricData` and no `read_series`, so it does not satisfy the port, ISS-240 |
| `QuotaSource` | `quotas.py` | Provider | Read the quotas that apply to an account and region, and every increase request on record | `aws/quotas.py` `AwsQuotas`, over Service Quotas, CloudWatch, EC2 and the Support API |
| `ResourceInventory` | `inventory.py` | Provider | Read what exists in an account, and what depends on what | Fake only. The AWS Config aggregator adapter implements `TopologySource` instead, ISS-240 |
| `QuerySurface` | `query.py` | Surface | Find the instances of a tool that holds saved queries, list their queries, and apply a control to one | `grafana/amg.py` `AmgQuerySurface`, over Amazon Managed Grafana |
| `RefreshFloor` | `query.py` | Surface | Read and set the smallest refresh interval an instance accepts from anybody | The same `AmgQuerySurface` |
| `PanelRewrite` | `query.py` | Surface | Read and replace one element's stored definition | Fake only, ISS-240 |
| `LlmProvider` | `llm.py` | Model | Complete a conversation, asking for tools along the way | `aws/bedrock.py` `BedrockModel`, over the Bedrock Converse API |
| `PriceCatalog` | `catalog.py` | Catalog | Read the current version of a service's price list in every Region it is sold in, and every on demand and reserved price in one version | `aws/price_list.py` `AwsPriceCatalog`, TASK-P9-004 |
| `InstanceCatalog` | `catalog.py` | Catalog | Read EC2's own description of every instance type in a Region | `aws/instance_types.py` `AwsInstanceCatalog`, TASK-P9-005 |
| `SavingsPlansRates` | `catalog.py` | Catalog | Read every Savings Plans rate for EC2 in a Region, versioned by their own digest | `aws/savings_plans.py` `AwsSavingsPlansRates`, through the relay, TASK-P9-012 |
| `SpotPrices` | `catalog.py` | Catalog | Read every spot price reading in a Region's window | `aws/spot.py` `AwsSpotPrices`, through the relay, TASK-P9-013 |
| `ServiceCatalogue` | `ownership.py` | Ownership | Read an account's applications, the owner each names, and the tags that mark its resources | `aws/appregistry.py` `AwsServiceCatalogue`, over AWS AppRegistry, TASK-P11-003 |
| `ResourceCreators` | `ownership.py` | Ownership | Read who created a resource, or that it predates the record | `aws/cloudtrail_creators.py` `AwsResourceCreators`, over CloudTrail's event history, TASK-P11-004 |
| `InvoiceSource` | `invoice.py` | None | Read the payer's invoices and credit memos for a span of billing periods, FEAT-076 | `aws/invoices.py` `AwsInvoices`, over the Invoicing API through the relay, ADR-0035 |
| `BudgetSource` | `budget.py` | None | Read the payer's budgets | `aws/budgets.py` `AwsBudgets`, over AWS Budgets |
| `CloudWatchEstate` | `cloudwatch_estate.py` | None | Read what CloudWatch holds, its alarms, log groups and storage price, rather than the values in it | Fake only, ISS-240 |
| `CommitmentReport` | `commitment.py` | None | Read utilization per commitment and coverage per dimension | `aws/commitment.py` `CostExplorerCommitmentReport`, over Cost Explorer |
| `PullRequestSink` | `pull_requests.py` | None | Open a pull request on a code host, where a person reviews a change before anything happens | Fake only, OPEN-13 |
| `QueryEvidence` | `query.py` | None | Read what an account actually executed, as opposed to what it has defined | `aws/query_evidence.py` `CloudTrailQueryEvidence`, over CloudTrail and CloudWatch Logs |
| `QueryParser` | `query.py` | None | Read meaning out of a vendor's saved query, so that an adapter never imports `finops_query` | Not an adapter. `finops_query/parser.py` `GrafanaQueryParser`, which a collector hands to the adapter |
| `RecommendationSource` | `recommendations.py` | None | Read what the provider already knows is wasteful | `aws/recommendations.py` `CostRecommendationSource`, over Compute Optimizer, Cost Optimization Hub and Trusted Advisor |
| `StateSource` | `iac.py` | None | Read the resources the configured infrastructure as code state names | `aws/terraform_state.py` `S3TerraformState`, over Terraform state objects in S3 |
| `TicketSink` | `tickets.py` | None | Open a ticket where a person will see the work, and say whether it is still open | Fake only, OPEN-05 |
| `TopologySource` | `inventory.py` | None | Read every node and edge one account and region shows, plus what could not be read | `aws/config_inventory.py` `ConfigAggregatorInventory`, over an organization Config aggregator, with `aws/topology.py` `AwsEdgeSupplement` for the edges Config does not cover. `finops_ingest/collectors/topology.py` `CompositeTopologySource` joins them |

`ProviderSession` in `credentials.py` and `Classified` in `query.py` are protocols with no
methods. They are types an adapter passes around rather than ports, and no group holds them.

This section was checked against the code on 2026-10-05. The protocols to check it against
again are listed by:

```bash
grep -n -E "^class .*\(Protocol\)" finops_core/ports/*.py
```

Adding a provider means writing an adapter for each port in `PROVIDER_PORTS`, and for any
other port that provider can serve. It does not mean touching the domain, the API, or the
frontend.

## Canonical cost schema: FOCUS 1.4

The FinOps Open Cost and Usage Specification is the canonical internal cost
schema. It is not invented here. AWS Data Exports emits FOCUS natively, and
GCP and Azure both publish FOCUS exports.

Since P10, ADR-0034, the row carries every column FOCUS 1.4 makes mandatory for
Cost and Usage and the two that tie a row to its invoice: `BillingAccountName`,
`BillingCurrency`, `ChargeClass`, `PricingUnit`, `ServiceProviderName`,
`HostProviderName`, `InvoiceId` and `InvoiceDetailId` beside the columns below.
Each is read from AWS's FOCUS 1.2 export where its table has it, and null where it
does not. Invoices and billing periods are FOCUS 1.4 datasets of their own,
`invoice_detail` and `billing_period`, and FEAT-076 compares each invoice with
the rows carrying its id.

Core columns carried: `BillingAccountId`, `SubAccountId`, `ChargePeriodStart`,
`ChargePeriodEnd`, `BillingPeriodStart`, `BillingPeriodEnd`, `ServiceName`,
`ServiceCategory`, `ResourceId`, `ResourceName`, `RegionId`, `ChargeCategory`,
`ChargeDescription`, `BilledCost`, `EffectiveCost`, `ListCost`,
`ContractedCost`, `CommitmentDiscountId`, `CommitmentDiscountType`,
`CommitmentDiscountStatus`, `ConsumedQuantity`, `ConsumedUnit`, `PricingQuantity`,
`SkuId`, `Tags`, `ProviderName`, `PublisherName`, `InvoiceIssuerName`.

Meter adds a small number of internal columns alongside, never inside, the
FOCUS namespace: `tenant_id`, `as_of`, `ingest_run_id`, `source_fingerprint`.

**Cost measure policy.** Amortized and net amortized are the primary measures
everywhere in the product. With Reserved Instances and Savings Plans in play,
unblended per resource cost is fiction. Unblended is retained for invoice
reconciliation only, and is never the default on a chart.

## Identity and authorization

The identity adapter is deliberately deferred. See `tasks/ISSUES.md`, OPEN-01.

Two ports isolate it so that nothing downstream depends on the decision.

```python
IdentityProvider.authenticate(request) -> Principal
EntitlementResolver.resolve(principal)  -> Scope{account_ids, ou_ids, tier, is_global}
```

The intended production model, subject to confirmation, uses the ADFS SAML
assertion as the source of truth. The AWS role claim in that assertion is
multi valued, carrying one entry per account and role the user is entitled to.
That entitlement list becomes the visibility scope directly, which means there
is no separate permission table to drift out of sync with Active Directory.

Three properties this design must preserve.

1. **Hybrid access.** The entitlement list acts as a row level filter over
   pre aggregated warehouse data, which cannot be fetched per user live. Any
   live drill down, for example describing a resource or running a Logs
   Insights query, uses `AssumeRoleWithSAML` into the user's own role so the
   call carries their identity into CloudTrail.
2. **Role name maps to a permission tier.** A read only role and an
   administrator role must not grant the same thing inside Meter.
3. **Coverage is stated, never implied.** The entitlement list only contains
   accounts where a federated role exists. Log archive, shared services and
   newly vended accounts are commonly absent. The organization tree remains
   the inventory of record, the entitlement list is only a filter, and the
   interface always states "you can see N of M accounts" rather than
   presenting a partial total as an organization total.

Enforcement happens in two places, a request dependency and a repository
guard, so a route that forgets the dependency still cannot read out of scope
data.

A row that belongs to a person rather than to an account, a question asked of
the assistant or what redaction found in it, is confined to that person by the
guard's `ByPrincipal` rule. It is checked before the global case, so a payer
wide scope does not widen it, and the scope carries the principal for that
reason. ADR-0029.

## Ingestion framework

```
EventBridge Scheduler
      |
      v
dispatcher            enumerate (tenant, account, region, collector)
      |
      v
SQS with dedup key
      |
      v
Fargate workers       scale on queue depth
      |
      v
run ledger + watermarks -> PostgreSQL and S3
```

Four properties are built in from the start because retrofitting them is the
classic failure of this kind of platform.

1. **Idempotent.** The idempotency key is a hash of collector, scope key and
   the as of window. Every write is an upsert. CUR is restated throughout the
   month, so re reading must never double count or make a trend line jump.
2. **Partial failure is first class.** Status is tracked per account, per
   region, per collector. One account returning AccessDenied never fails a run.
3. **Errors are typed.** `AccessDenied`, `Throttled`, `NotOptedIn`, `NoData`
   mean entirely different things. Collapsing them into a generic error, or
   worse into the number zero, is how a FinOps tool loses trust permanently.
4. **Everything carries `as_of`.** Every screen displays freshness.

## Self metering

Every Meter resource is tagged `finops:module`. A collector reads Meter's own
Cost Explorer data by that tag into a `platform_cost` table, surfaced on the
front page.

This is not a nice to have. A FinOps tool that cannot show its own bill has no
standing to comment on anyone else's. It also guards against the specific
failure this product exists to prevent, since the ingestion layer itself makes
paid API calls, and `GetMetricData` and Athena scanning are both metered.

## Security posture, v1

- Read only. No write API call into a member account.
- Remediation is delivered as a generated infrastructure as code pull request.
- Cross account trust requires an ExternalId and an `aws:PrincipalOrgID`
  condition.
- The member role uses a curated policy of roughly 40 actions, not
  `ReadOnlyAccess`, which grants S3 object reads, SSM parameter reads and
  Secrets metadata that are not needed and cannot be defended in review.
- Every scope evaluation is written to an audit log. Access by the global
  viewer role is audited separately and requires multi factor authentication
  with a shortened session.

## Disaster recovery

Closes AUDIT-001 finding A001-F13, ISS-065. Aurora has default backups, and a
default is not a decision.

### The fact that makes this cheap

**Meter is a derived data system.** Every fact in it exists somewhere in AWS
and can be re ingested. Nothing in Meter is the only copy of anything, with
three exceptions.

| Not re ingestible | Why | Consequence |
| --- | --- | --- |
| `audit_event` | Who read what. AWS does not hold this | Losing it loses the audit trail. This is the one that matters |
| Recommendation lifecycle state, P3 | Accepted, in progress, done, and who owns it | Losing it loses the workflow, not the recommendations |
| `collector_schedule` overrides | Cadence changes and their reasons | Falls back to documented defaults |

Everything else, the organization tree, account health, cost, inventory,
quotas, is a copy of something AWS still has.

### Objectives

| | Target | Basis |
| --- | --- | --- |
| **RPO, audit and workflow data** | 5 minutes | Aurora continuous backup with point in time recovery |
| **RPO, derived data** | 24 hours, and materially less in practice | Re ingestion, bounded by the source cadences in ADR-0012 |
| **RTO, service restored** | 4 hours | Terraform apply into a clean account, plus an Aurora restore |
| **RTO, all data current** | 24 hours | The slowest collector is `cur_focus_final`, monthly. Everything else is hourly to daily |

The asymmetry is deliberate. Tight objectives are bought only for the data that
cannot be rebuilt, which is a small fraction of the database.

### Strategy

| Layer | Position |
| --- | --- |
| Infrastructure | Terraform is the recovery mechanism. A region loss is `terraform apply` with a different provider region |
| Database | Aurora automated backups, point in time recovery, retention **matching the table retention policy** in `docs/09-DATA-CLASSIFICATION.md`, so a backup does not resurrect data that policy dropped |
| Raw exports | CUR lands in S3 with cross region replication. It is the source of record for cost, and AWS keeps its own copy regardless |
| Derived data | Re ingested. Watermarks are reset and collectors replay. Idempotency makes replay safe by construction |
| Secrets | Secrets Manager replication. The ExternalId must survive, or every member role has to be redeployed |
| Images | ECR with the base images mirrored, so a registry outage does not block a recovery deploy |

### The part most projects skip

**A restore that has never been tested is a hypothesis.** So:

- A restore drill is an acceptance criterion of TASK-P0-028, not a later
  intention. Restore into a scratch database, run the migrations, confirm the
  application starts and the freshness screen reports correctly.
- The drill repeats at each sub project boundary, and its result is recorded in
  the audit for that boundary.
- Re ingestion is exercised by the idempotency test that already exists:
  running a collector three times writes one result set. Replay after a restore
  is the same code path.

### What is deliberately not covered

Multi region active active. Meter is an internal reporting platform. An outage
delays a report, it does not stop a payment. Paying for active active would be
the exact behaviour this product exists to discourage in others, and it would
be visible on our own front page in `platform_cost`.

## Testing strategy

| Layer | Approach |
| --- | --- |
| Domain | Pure unit tests, no fixtures needed |
| Ports | Contract tests run against both the fake and the real adapter |
| AWS adapter | `moto` and botocore `Stubber` |
| Repositories | testcontainers PostgreSQL |
| Normalization | Golden file tests for FOCUS mapping |
| API | FastAPI test client against `FakeProvider` |
| Frontend | Vitest and Testing Library, Playwright for critical journeys |

Coverage target is 80 percent, matching the organization standard. Scope
enforcement is tested adversarially: a test asserts that a route which omits
the scope dependency still cannot return out of scope rows.
