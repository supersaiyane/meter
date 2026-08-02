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

Six interfaces, defined in `finops-core`, implemented per provider. A
`FakeProvider` implements all six so that core and API tests run with no AWS
access at all.

| Port | Responsibility | AWS implementation |
| --- | --- | --- |
| `AccountDiscovery` | Enumerate accounts and the organization tree | AWS Organizations |
| `CredentialBroker` | Produce a scoped session for a target account | STS AssumeRole with ExternalId |
| `CostExport` | Locate and read billing data | Data Exports CUR 2.0 in S3, read through Athena |
| `MetricSource` | Read time series for a resource | CloudWatch GetMetricData |
| `ResourceInventory` | Enumerate resources and their relationships | AWS Config aggregator, Resource Explorer |
| `QuotaSource` | Read limits and current usage | Service Quotas, AWS/Usage namespace, Trusted Advisor |

Adding a provider means implementing six interfaces. It does not mean touching
the domain, the API, or the frontend.

## Canonical cost schema: FOCUS 1.1

The FinOps Open Cost and Usage Specification is the canonical internal cost
schema. It is not invented here. AWS Data Exports emits FOCUS natively, and
GCP and Azure both publish FOCUS exports.

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
