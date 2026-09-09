# Threat model

Last updated: 2026-08-23
Update trigger: any new trust boundary, any new data flow crossing one
Method: STRIDE per boundary
Closes: AUDIT-001 finding A001-F11, ISS-055

`docs/05-SECURITY.md` is the policy and the controls. This is the analysis of
who attacks this, how, and which control stops them. A policy does not
substitute for one, which is why this document exists separately.

## What is worth attacking

Stated first, because a threat model that does not name the prize produces
generic threats.

| Asset | Why an attacker wants it |
| --- | --- |
| The hub task role | It can assume a read role into **every** account in the organization |
| The ExternalId | Combined with a role ARN, it is half of the cross account trust |
| `cost_focus_daily` | Resource level spend for the whole organization. Reveals architecture, scale, growth, product launches, and which teams are struggling |
| `org_node` and `cloud_account` | The complete organization structure and every account identifier. A target map |
| Resource inventory, later | Every resource, region, and how they connect. A network map |
| `audit_event` | Who looked at what. Useful for finding a target and for covering tracks |
| The global viewer credential | One session that sees everything, by design |
| The deploy path | Anything running in the hub account inherits the hub role |

Meter is **read only** into member accounts. That bounds the damage: an
attacker gains reconnaissance, not control. That is the single most important
mitigation in this document and it is a design property, not a control that can
be misconfigured. ADR-0004.

## Trust boundaries

```
  [ human ]
      | 1  browser to API, identity and scope
      v
  [ finops-api ] <---- 2  MCP client to API, same boundary, different client
      | 3  API to database
      v
  [ Aurora ]
      ^
      | 4  worker to database
  [ finops-ingest ]
      | 5  hub account to member account, STS AssumeRole
      v
  [ member AWS accounts ]

  [ GitLab ] --6--> [ AWS deploy role ] --> [ ECS ]
```

| # | Boundary | Crosses |
| --- | --- | --- |
| 1 | Human to API | Untrusted network, identity assertion, scope |
| 2 | MCP client to API | Same, plus a model in the loop |
| 3 | API to database | Scope becomes a row filter |
| 4 | Worker to database | Ingested data becomes stored fact |
| 5 | Hub to member account | An organization trust boundary. The important one |
| 6 | Pipeline to AWS | Code becomes running infrastructure |

---

## Boundary 5: hub account to member account

The highest value boundary. Analysed first.

| STRIDE | Threat | Mitigated by | Residual |
| --- | --- | --- | --- |
| **S** | An attacker outside the organization assumes `FinOpsCollectorRole` | Trust policy requires the hub role principal, an ExternalId, **and** `aws:PrincipalOrgID`. All three must hold, and the organization condition cannot be satisfied from outside | Low |
| **S** | A **member account administrator** uses their own collector role against a different account | They cannot. The trust policy names the hub role as principal, not the account. A member admin can delete their own role, not assume another account's | Low. This is the question an auditor asks first |
| **S** | The ExternalId leaks, from a log, a document, or Secrets Manager | ExternalId alone is insufficient: the caller must still be the hub role and inside the organization. Never logged, never in an image layer, stored in Secrets Manager and referenced by name in `cloud_account.external_id_ref` | **Medium.** Rotation is not yet designed. Tracked below |
| **T** | Meter modifies a member account | Impossible by construction. The curated policy grants no write action, and there is no write API call in the codebase. ADR-0004 | Low |
| **R** | An operator denies having read an account | Every live drill down uses `AssumeRoleWithSAML` into the user's own role, so the call carries their identity into the member account's CloudTrail, not Meter's | Low |
| **I** | The curated policy grants more than intended | ~40 actions, each annotated with the collector needing it. Explicitly not `ReadOnlyAccess`, which grants S3 object and SSM parameter reads. ISS-010 | Low |
| **D** | Meter exhausts a member account's API quota and degrades their workloads | Bounded retry, exponential backoff, cadence in `collector_schedule` with a cost per run, and `GetMetricData` batched at 500 metrics per call | **Medium.** No per account rate limit yet. Tracked below |
| **E** | A compromised worker container assumes roles it should not | `FinOpsHubTaskRole` may assume **only** `role/FinOpsCollectorRole`, restricted by `aws:PrincipalOrgID`. Not `sts:AssumeRole` on `*` | Low |

**If the hub task role is fully compromised**, the attacker gets read only
reconnaissance across the organization: account structure, cost, and later
inventory. They cannot create, modify or delete anything in a member account,
cannot read S3 object contents, and cannot read SSM parameters or secrets. The
blast radius is disclosure, not control. Detection is CloudTrail in each member
account, where the calls appear under the collector role.

---

## Boundary 1: human to API

| STRIDE | Threat | Mitigated by | Residual |
| --- | --- | --- | --- |
| **S** | Session token forged or replayed | Signed session, 8 hour hard re auth, entitlements cached with an explicit expiry so a revocation propagates | Low |
| **S** | The local development identity provider reaches production | The application refuses to start when `METER_ENV` is prod and `local_config` is selected. An integration test asserts the refusal. ISS-017 | Low |
| **T** | A user sees cost for an account outside their scope | Scope enforced at a request dependency **and** independently at a repository guard, so a route that forgets the dependency still cannot leak. An adversarial test asserts it. ISS-009 | Low |
| **T** | A partial view is presented as an organization total | Every response carries `scope_coverage`, and the interface states "showing N of M accounts". ISS-016 | Low |
| **R** | A global viewer denies a read | Every scope evaluation writes `audit_event`, and global reads are tagged and separately indexed | Low |
| **I** | Error messages leak account identifiers across a scope boundary | Typed errors carry a `scope_key` the caller is already entitled to see. **Needs a test.** Tracked below | **Medium** |
| **D** | Expensive query floods the API | Pre aggregated rollups, no Athena in the serving path, rate limiting at the API | Low |
| **E** | A viewer performs an owner action | Role name maps to a tier, checked at the dependency | Low |

**The global viewer credential** is a deliberate concentration of risk. It is
required, and it is treated as break glass: multi factor required, shortened
session, every read tagged `is_global_read` on a partial index so reporting on
it is cheap. A control that is expensive to audit does not get audited.

---

## Boundary 2: MCP client to API

The same boundary with a model in the loop, which adds threats the browser does
not have.

| STRIDE | Threat | Mitigated by | Residual |
| --- | --- | --- | --- |
| **T** | A crafted prompt induces the assistant to return data outside the caller's scope | The MCP server calls the HTTP API **over the network with the caller's token**. It has no privileged path. A model cannot ask for what the token cannot fetch. ADR-0009 | Low |
| **T** | The MCP layer grows its own authorization and diverges from the API | An import linter contract forbids `finops_mcp` importing `finops_api.db`, `finops_api.guards`, `finops_providers`, `boto3` and `sqlalchemy`. A second implementation fails CI. A001-F02 | Low |
| **I** | The model presents a partial total as complete | Tool responses preserve the `meta` envelope including `scope_coverage`. A test asserts it. TASK-P0-030 | **Medium.** A model can still narrate carelessly around a correct envelope |
| **I** | Data exfiltration via a tool that returns too much | Tools are typed and enumerable. No free form SQL tool, ever. ADR-0007 | Low |
| **D** | Model driven query amplification | The same rate limit as the API, because it **is** the API | Low |
| **E** | A tool performs a write | No write tool exists. Meter is read only in v1 | Low |

The structural decision doing the work here is ADR-0009: the MCP server is a
facade, not a second door. Every mitigation on boundary 1 applies unchanged
because it is the same door.

---

## Boundaries 3 and 4: application to database

| STRIDE | Threat | Mitigated by | Residual |
| --- | --- | --- | --- |
| **T** | SQL injection | Parameterised queries only, SQLAlchemy, no string concatenation | Low |
| **T** | A repository method omits the scope filter | The base repository **raises** rather than returning everything when a scoped table is queried without a scope. `Scope` has no default value | Low |
| **I** | Database credentials in an image or a log | Secrets Manager, injected at runtime by the task role. Never in a layer, never in `docker-compose` for a real environment | Low |
| **I** | Data at rest | Aurora encrypted, not publicly accessible, private subnets only | Low |
| **T** | A collector writes a fact with no provenance | `as_of`, `collected_at`, `ingest_run_id` and `source_fingerprint` are all `NOT NULL` | Low |
| **D** | A runaway backfill locks a large table | Data migrations are separate revisions, batched and resumable. `CREATE INDEX CONCURRENTLY` on populated tables | Low |

---

## Boundary 6: pipeline to AWS

| STRIDE | Threat | Mitigated by | Residual |
| --- | --- | --- | --- |
| **S** | A pipeline in another project assumes the deploy role | OIDC trust restricted by subject claim to this project and to the branches allowed to deploy | Low |
| **T** | An unscanned image is deployed | Provenance verification before deploy checks the cosign signature **and** the SBOM attestation. An image without an attestation was never scanned by this pipeline | Low |
| **T** | A tag is repointed at a different image after scanning | ECR tag immutability, in TASK-P0-016. ISS-054 | Low |
| **T** | A malicious dependency enters | Admission gate scans the whole transitive tree before a dependency is added, and a CI job repeats it on any manifest change so editing the file directly does not bypass it | **Medium.** A gate catches known vulnerabilities, not a deliberate backdoor in a clean package |
| **I** | Secrets in CI variables | None exist. GitLab OIDC only. No long lived AWS key | Low |
| **E** | A privileged runner is compromised | Kaniko, so no privileged runner is needed | Low |
| **D** | Supply chain outage blocks a deploy | Base image digests pinned and mirrored into the project's own ECR | Low |

---

## Residual risks, tracked

Every `Medium` above, with an owner and a route to closure. A residual risk with
no tracking row is an accepted risk nobody agreed to accept.

| Risk | Issue | Route |
| --- | --- | --- |
| ExternalId rotation is not designed | ISS-073 | Design rotation in P0, before TASK-P0-014. A per tenant ExternalId with a documented rotation runbook |
| No per account API rate limit, so Meter could degrade a member account | ISS-074 | A token bucket per account in the credential broker, sized against the smallest published service quota |
| Error messages may leak identifiers across a scope boundary | ISS-075 | An adversarial test in TASK-P0-024 asserting no out of scope identifier appears in any error body |
| A model can narrate carelessly around a correct envelope | ISS-076 | Assistant responses must cite provenance per figure. Design in P7, and the eval suite must include a partial scope case |
| A deliberate backdoor in a package that scans clean | ISS-077 | Out of reach of a CVE scanner. Mitigate by pinning digests, preferring fewer dependencies (ADR-0013 rung one), and reviewing any new direct dependency by hand |

## Explicitly out of scope

| Not modelled | Why |
| --- | --- |
| Physical security of AWS | AWS shared responsibility model |
| Compromise of the AWS control plane | Outside any mitigation available here |
| An insider with the global viewer credential and legitimate access | A detection problem, addressed by `audit_event`, not a prevention problem |
| Denial of service against AWS itself | Not a Meter threat |

## When to redo this

- A new trust boundary, for example an in cluster agent in P6, which introduces
  a boundary from a customer workload into Meter.
- Any write path into a member account. That would invalidate the single most
  important mitigation in this document.
- A change to the identity model, which is currently OPEN-01.
- Before any external exposure of the API.
