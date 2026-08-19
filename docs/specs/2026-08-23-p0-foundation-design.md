# P0 Foundation: design specification

Date: 2026-08-23
Status: In review
Sub project: P0
Depends on: nothing
Blocks: P1, P2, P3, P4, P5, P6, P7

## 1. Purpose

P0 is the spine. It delivers no cost data and no recommendations. It delivers
the things every other sub project needs and that cannot be retrofitted
cheaply: account onboarding, the organization tree, cross account credentials,
the provider abstraction, the canonical cost schema, the ingestion framework,
the authorization seam, and platform self metering.

## 2. Definition of done

A user logs in, sees the full organization parent to child tree, sees every
account with its onboarding and role health status, sees an ingest and
freshness dashboard with typed per account errors, and sees Meter's own
monthly AWS cost broken down by module. An account newly vended into an
organizational unit appears in Meter within one hour with no human step.

## 3. Out of scope for P0

Cost data, rightsizing, recommendations, alerting, AWS Config ingestion,
Kubernetes agents, any non AWS connector, any write action into a member
account, and the language model layer. Listed explicitly so that adding any of
them is a visible decision rather than a drift.

## 4. Module structure

```
finops-core/
  domain/         entities: Tenant, CloudAccount, OrgNode, Principal, Scope,
                  IngestRun, PlatformCost, CostRecord (FOCUS shaped)
  ports/          AccountDiscovery, CredentialBroker, CostExport, MetricSource,
                  ResourceInventory, QuotaSource, IdentityProvider,
                  EntitlementResolver
  errors.py       typed error taxonomy
finops-providers/
  aws/            the six cloud ports implemented against boto3
  fake/           all ports implemented in memory, used by every core and API test
  gcp/            README only, reserved
  azure/          README only, reserved
finops-ingest/
  dispatcher.py   enumerate units of work, publish to SQS
  worker.py       consume, claim a run, execute a collector, record outcome
  ledger.py       run ledger and watermarks
  collectors/     org_tree.py, account_health.py, platform_cost.py
finops-api/
  main.py         FastAPI application
  deps.py         scope dependency
  routes/         accounts, org, ingest, platform, me
  guards.py       repository level scope guard
finops-web/
  src/            React and TypeScript
infra/terraform/
  hub/            VPC, ECS, Aurora, SQS, S3, EventBridge, hub role
  member/         StackSet template for FinOpsCollectorRole
  management/     FinOpsOrgReaderRole
```

The import linter rule that fails continuous integration:
`finops-core` may not import `boto3`, `botocore`, `fastapi`, `sqlalchemy`, or
`requests`.

## 5. Data model

PostgreSQL. All tables carry `tenant_id` even though P0 is single tenant, so
that a future multi tenant move is a policy change rather than a migration.

### 5.1 Identity and tenancy

```sql
tenant(tenant_id pk, name, created_at)

principal(principal_id pk, tenant_id, subject, display_name, email,
          tier, is_global, created_at, last_seen_at)

principal_scope(principal_id, account_id, ou_id, granted_via, resolved_at,
                expires_at)
```

`principal_scope` is a cache of the resolved entitlement, with an expiry. It is
never the source of truth. The source of truth is whatever `EntitlementResolver`
returns at authentication time.

### 5.2 Accounts and organization tree

```sql
cloud_account(account_pk pk, tenant_id, provider, account_id, name, email,
              status, payer_account_id, joined_at, onboarded_at,
              collector_role_arn, external_id_ref, role_health,
              role_health_checked_at, role_health_error, as_of)

org_node(node_pk pk, tenant_id, node_id, node_type, parent_node_id, name,
         path, depth, as_of)
```

`node_type` is one of `ROOT`, `OU`, `ACCOUNT`. The tree is a plain adjacency
list traversed with a recursive common table expression. `path` and `depth` are
denormalized for cheap filtering and are rebuilt on every refresh.

`role_health` is one of `HEALTHY`, `ACCESS_DENIED`, `NOT_DEPLOYED`,
`THROTTLED`, `UNKNOWN`. It is what makes onboarding failures visible instead
of silent.

### 5.3 Ingestion

```sql
ingest_run(run_id pk, tenant_id, collector, scope_key, idempotency_key unique,
           started_at, finished_at, status, items_written, bytes_read,
           error_type, error_detail, as_of_window_start, as_of_window_end)

ingest_watermark(tenant_id, collector, scope_key, as_of, updated_at,
                 primary key (tenant_id, collector, scope_key))

sync_error(error_id pk, tenant_id, collector, scope_key, error_type,
           detail, first_seen_at, last_seen_at, occurrences)
```

`scope_key` is a stable string, for example `aws:111122223333:eu-west-1`.
`idempotency_key` is `sha256(collector, scope_key, as_of_window_start,
as_of_window_end)`.

### 5.4 Cost, defined in P0 and populated in P1

```sql
cost_focus_daily(...)   FOCUS 1.1 columns, plus tenant_id, as_of,
                        ingest_run_id, source_fingerprint.
                        Partitioned by billing_period.

cost_provider_extra(...) provider specific columns that FOCUS does not carry,
                         keyed by the same fact.
```

Created in P0 so the schema contract is fixed before any consumer exists.
No rows are written until P1.

### 5.5 Platform self metering and audit

```sql
platform_cost(tenant_id, day, module, service, amortized_cost, as_of)

audit_event(event_id pk, tenant_id, principal_id, action, resource,
            scope_evaluated, outcome, occurred_at, request_id)
```

Every scope evaluation writes an `audit_event`. Access by a global viewer is
tagged so it can be reported on separately.

## 6. Error taxonomy

A closed set, defined in `finops-core/errors.py`. Collapsing these, or
rendering any of them as the number zero, is a defect.

| Error | Meaning | User facing treatment |
| --- | --- | --- |
| `AccessDenied` | The collector role is missing or the policy is insufficient | Account shown as not onboarded, with the remediation step |
| `Throttled` | API rate limit reached | Transient, retried with backoff, shown as degraded not failed |
| `NotOptedIn` | The service is not enabled for this account or region | Shown as not applicable, with the enablement step |
| `NoData` | The call succeeded and returned nothing | Shown as zero, and this is the only case where zero is correct |
| `Unreachable` | Network path failure, for example a private subnet with no endpoint | Shown as failed, with the network cause |
| `SchemaDrift` | The upstream payload no longer matches expectations | Shown as failed, and raised as an issue automatically |

## 7. Ingestion flow

```
EventBridge Scheduler (hourly)
   -> dispatcher task
        reads cloud_account, expands to (tenant, account, region, collector)
        publishes one SQS message per unit with a dedup key
   -> SQS main queue, dead letter queue after 3 attempts
   -> Fargate worker service, scaled on ApproximateNumberOfMessagesVisible
        claims an ingest_run by idempotency_key
        obtains credentials from CredentialBroker
        runs the collector
        upserts results, updates the watermark, records the outcome
   -> failures write to sync_error and the account is marked, the run continues
```

P0 collectors.

1. `org_tree`. Runs against the management account through
   `FinOpsOrgReaderRole`. `ListRoots`, then `ListOrganizationalUnitsForParent`
   and `ListAccountsForParent` recursively. Rebuilds `org_node` and upserts
   `cloud_account`. Hourly.
2. `account_health`. For each account, attempts an STS AssumeRole into
   `FinOpsCollectorRole` and a single cheap call. Records `role_health`.
   Hourly.
3. `platform_cost`. Reads Cost Explorer for the hub account, grouped by the
   `finops:module` tag. Daily.

## 8. API surface

### 8.0 Why an HTTP API rather than only an MCP server

The question was raised whether MCP could replace the API. It cannot, and it
does not need to, because both exist. Decided in ADR-0009.

The HTTP API is the **single enforcement point**. Scope filtering, the audit
log, rate limiting and the freshness envelope are implemented once here.

The MCP server, in `finops-mcp`, is a thin facade that calls this API over the
network with the caller's token. It does not reach into the service layer,
because the scope dependency lives at the HTTP boundary and reimplementing it
inside the MCP layer is exactly the defect ISS-009 describes.

Four reasons MCP alone is not sufficient. A browser cannot speak MCP, and the
frontend needs REST. MCP has no notion of a browser session, of pagination for
a table, or of HTTP caching. Authorization would need a second implementation.
Operational tooling, load balancer health checks, access logs, tracing and WAF
rules, all work on HTTP and none work on stdio JSON-RPC.

P0 exposes four MCP tools: `list_accounts`, `get_org_tree`, `get_ingest_status`
and `get_platform_cost`. The tool schemas are generated from the same Pydantic
models the API uses, so a drift between the two surfaces is a build failure.

### 8.1 Routes

All responses carry a `meta` block: `{ as_of, collected_at, scope_coverage:
{ visible, total }, degraded }`. Two timestamps, not one: `as_of` is when the
data was true at the source, `collected_at` is when Meter fetched it. See
ADR-0012 and ISS-038.

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/me` | Principal, tier, scope summary |
| `GET /api/v1/accounts` | Accounts in scope, with role health and freshness |
| `GET /api/v1/org/tree` | Organization tree, filtered to scope, unreachable branches marked rather than hidden |
| `POST /api/v1/accounts/{id}/recheck` | Force a role health recheck |
| `GET /api/v1/ingest/runs` | Recent runs with status and typed errors |
| `GET /api/v1/health/freshness` | Per collector, per scope freshness and staleness |
| `GET /api/v1/platform/cost` | Meter's own cost by module and day |

Scope is applied by a FastAPI dependency and independently by a repository
guard. An adversarial test asserts that a route registered without the
dependency still cannot return out of scope rows.

## 9. Frontend

Five screens. No charting library beyond a sparkline in P0.

1. **Shell.** Navigation, principal menu, a persistent scope coverage banner
   reading "showing N of M accounts", and a global freshness indicator.
2. **Accounts.** Table with account identifier, name, organizational unit,
   status, role health, last successful ingest. Filter by role health so that
   broken onboarding is one click away.
3. **Organization map.** Two views of the same data. A collapsible tree, which
   is the default because it is fast and keyboard navigable, and a graph view
   rendered with Cytoscape.js for the visual parent to child map.
4. **Ingest and freshness.** Per collector and per scope status, with typed
   errors and their remediation text. This is the operational screen that
   proves the platform is honest about what it does not know.
5. **Platform cost.** Meter's own spend by module, with a 30 day sparkline.

## 10. Infrastructure

Terraform, three root modules.

- `hub`. VPC with private subnets and VPC endpoints for STS, S3, SQS, Secrets
  Manager, Cost Explorer and Logs, so the workers do not need a NAT Gateway.
  ECS cluster with an API service and a worker service, Aurora Serverless v2,
  SQS with a dead letter queue, S3 for raw exports, EventBridge Scheduler,
  Secrets Manager for the ExternalId, and `FinOpsHubTaskRole`.
- `member`. The `FinOpsCollectorRole` CloudFormation template, delivered as a
  service managed StackSet with automatic deployment to the organization root.
- `management`. `FinOpsOrgReaderRole`.

Every resource carries `finops:module`, which is what makes self metering work.

The VPC endpoint decision is deliberate. A NAT Gateway is billed per hour and
per gigabyte processed, and this workload is chatty across hundreds of
accounts. Interface endpoints are cheaper here and keep traffic off the public
internet.

## 11. Testing

| Layer | Approach |
| --- | --- |
| Domain | Pure unit tests |
| Ports | Contract test suite run against both `fake` and `aws` adapters |
| AWS adapter | `moto`, with botocore `Stubber` where `moto` lacks coverage |
| Repositories | testcontainers PostgreSQL |
| Ingestion | Idempotency test: run a collector three times, assert one row set and one run |
| Scope | Adversarial test: a route without the dependency still cannot leak |
| API | FastAPI test client against `FakeProvider` |
| Frontend | Vitest and Testing Library, Playwright for login through to the organization map |

Coverage target 80 percent.

Three tests that specifically encode the lessons of this design.

1. A collector that raises `AccessDenied` for one account must produce a run
   that completes, an account marked unhealthy, and correct data for every
   other account.
2. A collector returning `NoData` and a collector raising `AccessDenied` must
   produce visibly different states, never both rendering as zero.
3. Selecting `LocalConfigIdentityProvider` while the environment is production
   must prevent the application from starting.

## 11a. Security

Governed by `docs/05-SECURITY.md` and ADR-0010. The parts that bind P0.

- Base images are Minimus from `reg.mini.dev`. The runtime images have no shell
  and no package manager, so every `CMD` and `ENTRYPOINT` is in exec form, and
  health checking is done by the ALB target group rather than a `HEALTHCHECK`
  instruction.
- No dependency is added without `make dep-check` passing against its whole
  transitive tree.
- The policy is zero findings at any severity. `make security-scan` runs as
  part of `make verify`.
- A nightly job scans the digest actually running in each environment, because
  a build time scan reports zero forever while the deployed image degrades.

## 12. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Management account cooperation is needed once for StackSet trusted access and the organization reader role | P0 cannot complete | Raised as an external dependency with an owner and a date, tracked as ISS-002 |
| The identity decision is unresolved | Production login is not deliverable in P0 | Ports isolate it. P0 ships local authentication gated to non production. Tracked as OPEN-01 |
| Organizations API throttling at 300 accounts | Slow or failed tree refresh | Exponential backoff, hourly rather than continuous refresh, and the tree is cached with `as_of` |
| Cost Explorer charges per request | Self metering becomes a cost of its own | Daily rather than hourly, one grouped request, and the cost is itself shown in `platform_cost` |
| Scope enforcement bypass | Data leak across accounts | Two independent enforcement points plus an adversarial test |
| A Minimus tag for Python 3.12 or a `-dev` variant is unavailable or named differently | The images do not build | Verified at TASK-P0-029 before any image work. Fallback is a distroless equivalent, recorded as a change, never a silent return to the official image |
| A dependency cannot pass the admission gate | A build is blocked | Intended. The escape is a time boxed allowlist entry with an owner, never a threshold change |

## 13. Open questions

Tracked in `tasks/ISSUES.md`. OPEN-01 authentication is the only one that
affects P0 delivery, and it is isolated behind ports.
