# Project map

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: The module level map, read before opening any source file, so
     orientation costs one read instead of ten.
     Grade B here: copy it, then replace the tree and the responsibilities. The format and the
     update trigger carry over.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

Module level map. Check this before reading any source file, and before
searching. If it does not answer the question, the map is wrong and should be
rebuilt from source rather than worked around.

Last updated: 2026-08-23
Master index: `INDEX.md`
Verified against the tree: 2026-10-09
Update trigger: any new module, moved module, or changed responsibility.

## Current reality

P0 is in build. The Python packages now exist as empty namespaces, created at
TASK-P0-029 so the policy checks have something to scan. They carry no
application code yet beyond the workspace itself. `PLANNED` means the module
has no working code. Five of
them now have a directory and an `__init__.py`, created by TASK-P0-029 because
the policy checks needed something to scan,
so the map is never mistaken for a description of what exists.

```
meter/
├── INDEX.md                   master index, the entry point for the project
├── README.md                  what Meter is, and the documentation map
├── Makefile                   every routine task, run `make help`
├── pyproject.toml             dependencies, lint rules, import linter contract
├── docker-compose.yml         local stack only, never used to deploy
├── .gitlab-ci.yml             verify, security, build, scan, plan, deploy
├── .env.example               every value, what it does, which file reads it
├── .pre-commit-config.yaml    local gates: secrets, writing rules, lint, doc drift,
│                              dependency admission on manifest change. Pre push
│                              runs the full scan and the tests
├── CLAUDE.md                  binding project rules, writing rules, definition of done
├── .gitignore
├── context_index.md           function level index, empty until code exists
│
├── project_map.md             this file, module level map
│
├── docs/
│   ├── 00-GOAL.md             goal, success criteria, north star, non goals
│   ├── 01-ROADMAP.md          the eight sub projects, build order, status
│   ├── 02-ARCHITECTURE.md     cross cutting architecture, ports, FOCUS, ingestion
│   ├── 03-CHANGE-CONTROL.md   where each kind of change is recorded
│   ├── 04-DEPLOYMENT.md       GitLab to ECR to Terraform to ECS
│   ├── 05-SECURITY.md         zero vulnerability policy, scanners, gates
│   ├── 06-DATA-FRESHNESS.md   refresh cadence per collector, and its limits
│   ├── 07-DATA-MODEL.md       every table, constraint, index, Alembic rules
│   ├── 08-THREAT-MODEL.md     STRIDE across six trust boundaries
│   ├── 09-DATA-CLASSIFICATION.md  classes, retention, erasure
│   ├── 10-OBSERVABILITY.md    four SLOs, ten alerts, two of which page
│   ├── 11-COMPETITIVE-REVIEW.md  what we took, rejected, and why
│   ├── 12-UI-DESIGN.md        provenance language, state matrix, components
│   ├── runbooks/              one per paging alert, written with the alert
│   ├── registry.yaml          SOURCE OF TRUTH for the generated documents
│   ├── feature-flags.yaml     every flag, its owner, reason, expiry, removal
│   ├── features/              one document per feature, 50 of them
│   ├── architecture/          generated file dependency graph
│   ├── templates/             spec, task, ADR, change and issue templates
│   ├── checkpoint.md          session continuity log with resume vectors
│   ├── adr/                   architecture decision records, 0001 to 0008
│   ├── specs/                 design specs, one per sub project
│   │   ├── 2026-08-23-p0-foundation-design.md
│   │   └── 2026-08-23-p2-query-cost-governance-design.md
│   │   └── 2026-08-23-p0-foundation-design.md
│   └── plans/                 implementation plans, written per sub project
│       ├── P0-implementation-plan.md
│       └── P2-implementation-plan.md
│
├── audits/                    point in time reviews, one file per audit
│   ├── README.md              naming convention, finding ids, cadence
│   └── AUDIT-001-...          full project, before coding
│
├── tasks/
│   ├── STATUS.md              done, in progress, remaining
│   ├── ISSUES.md              issue and open question register with fixed status
│   └── lessons.md             corrections converted into rules
│
├── docker/                    three Dockerfiles on Minimus, plus nginx.conf
│   └── base-images.lock       pinned digests, chosen by measurement. ADR-0010
│   └── base-images.lock       pinned digests, resolved by measurement at TASK-P0-029
├── docker-compose.yml         local stack, plus a `security` profile of one shot
│                              scanners that does NOT start with `make up`
│
├── security/                  everything a scan produces, and the policy
│   ├── POSTURE.md             current posture, generated, never hand edited
│   ├── policy/                grype.yaml, trivy.yaml, allowlist.yaml,
│   │                          accepted.yaml for unfixable findings. ADR-0018,
│   │                          accepted.yaml for unfixable findings, ADR-0018
│   ├── reports/               one directory per scan, committed
│   ├── sbom/                  one SBOM per image per build
│   └── reviews/               automated code review reports
│
├── .env.example               every value, what it does, which file reads it
├── .editorconfig              formatting that is not a matter of taste
├── .pre-commit-config.yaml    local gates: secrets, writing rules, lint, doc drift
├── CODEOWNERS                 who approves what. ADR-0013 needs a security owner
├── SECURITY.md                vulnerability disclosure route
├── local-auth.example.yaml    development identity, copied to a gitignored file
│
├── scripts/                   every script in the project, nothing executable elsewhere
│   ├── README.md              what each script does and how it is run
│   ├── security/              scan, admission gate, pre commit deps, report,
│   │                          auto fix, allowlist validation
│   ├── docs/                  sync.py, check_index.py, check_feature_docs.py,
│   │                          build_file_graph.py, build_context_index.py,
│   │                          rotate_checkpoint.py, add_lesson.py
│   ├── ci/                    code_review.py, check_flags.py, check_hardcoded.py,
│   │                          check_forbidden_imports.py, check_memory.py,
│   │                          refresh_base_images.py, flag and hardcoding checks,
│   │                          forbidden imports, the memory gate, base image resolver
│   └── deploy/                migration task runner
│
├── tests/                     the suite. conftest.py refuses to run against a
│                              real AWS account when no endpoint override is set.
│                              test_checkpoint_rotation.py covers the only script
│                              that deletes rows from the memory log
│
├── finops_core/               IN BUILD  domain and ports. No boto3, no framework
│   ├── errors.py              the six typed failure causes, closed set, no catch all
│   ├── config.py              every METER_ variable, typed. No defaults except flags
│   ├── constants.py           the values that are decisions rather than deployments
│   └── domain/                frozen entities, no persistence and no cloud concern
│       ├── fact.py            the as_of and collected_at pair, inherited not repeated
│       ├── account.py         Provider, AccountKey, CloudAccount. Never a bare id
│       ├── tenant.py          Tenant and Scope. No wildcard, empty means nothing
│       ├── org.py             OrgNode and the closed ROOT, OU, ACCOUNT set
│       ├── identity.py        Principal and Entitlement
│       ├── ingest.py          IngestRun, CollectionFailure, Watermark
│       ├── cost.py            CostRecord, FOCUS 1.1 names, Decimal money
│       ├── metrics.py         MetricPoint. `at` is the instant, `as_of` the freshness
│       ├── resource.py        ResourceRef. Opaque identifier, never parsed
│       └── quota.py           QuotaUsage. Unpublished usage is None, never zero
│   └── ports/                 eight protocols. No implementation, no cloud import
│       ├── accounts.py        AccountDiscovery
│       ├── credentials.py     CredentialBroker plus the opaque ProviderSession
│       ├── cost.py            CostExport
│       ├── metrics.py         MetricSource
│       ├── inventory.py       ResourceInventory
│       ├── quotas.py          QuotaSource
│       └── identity.py        IdentityProvider and EntitlementResolver
├── finops_providers/          IN BUILD  aws/, fake/, gcp/, azure/
│   └── fake/                  in memory, all eight ports, no network and no clock
│       ├── fixtures.py        one root, two units, five accounts, one denied
│       └── provider.py        the failure plan. Any of the six, for any scope
├── finops_ingest/             PLANNED  dispatcher, worker, ledger, collectors
│                              Directory exists, __init__.py only
├── finops_api/                IN BUILD  FastAPI, scope enforcement, routes
│   └── flags.py               flag resolution, tenant then environment then declared
├── finops-web/                PLANNED  React and TypeScript
├── finops_mcp/                PLANNED  MCP server, a facade over the HTTP API
│                              Directory exists, __init__.py only. Ships as a
│                              second process on the api image, ADR-0009
└── infra/terraform/           PLANNED  hub/, member/, management/
```

## Planned module responsibilities

| Module | Responsibility | Depends on | Must not depend on |
| --- | --- | --- | --- |
| `finops_core` | Domain entities, the eight ports, the typed error taxonomy | nothing | boto3, botocore, fastapi, sqlalchemy, requests |
| `finops_providers/aws` | The six cloud ports implemented against boto3 | `finops_core`, boto3 | `finops_api`, `finops-web` |
| `finops_providers/fake` | Every port implemented in memory, used by all core and API tests | `finops_core` | boto3 |
| `finops_ingest` | Dispatcher, worker, run ledger, watermarks, collectors | `finops_core`, a provider | `finops-web` |
| `finops_api` | HTTP surface, scope dependency, repository guard | `finops_core`, a provider | boto3 directly |
| `finops-web` | User interface | `finops_api` over HTTP | anything Python |
| `finops_mcp` | MCP tools for any model client | `finops_api` over HTTP | the service layer, repositories, boto3 |
| `infra/terraform` | Hub stack, member StackSet, management role | nothing | nothing |

The rule that keeps multi cloud cheap: `finops_core` never imports a cloud
software development kit. It is enforced by an import linter rule in
continuous integration, not by good intentions.

## Where to look for a given question

| Question | Answer lives in |
| --- | --- |
| Anything at all, as a starting point | `INDEX.md` |
| Where do I record this change | `docs/03-CHANGE-CONTROL.md` |
| How does code reach production | `docs/04-DEPLOYMENT.md` |
| What exactly do I build next, and how | `docs/plans/P0-implementation-plan.md`, then `P2-implementation-plan.md` |
| Task counts, which change | `grep -c '^### TASK' docs/plans/*.md`. Not written into prose, because a count in prose goes stale silently |
| What does this feature do | `docs/features/FEAT-nnn-*.md` |
| How do these files depend on each other | `docs/architecture/file-graph.md`, `make graph` |
| What is the security policy | `docs/05-SECURITY.md` |
| What does the database look like | `docs/07-DATA-MODEL.md` |
| Where do I change a feature status | `docs/registry.yaml`, then `make doc-sync` |
| What stops an unscanned image deploying | `docs/05-SECURITY.md`, layer 5, and `.gitlab-ci.yml` `verify-provenance` |
| Why LocalStack is in the stack, and its limits | `docker-compose.yml` inline, and `docs/04-DEPLOYMENT.md` |
| What breaks and how to fix it | `README.md` section 5, ten worked examples |
| What an audit found, and when | `audits/`, newest last by filename |
| Is the posture currently clean | `security/POSTURE.md` |
| Which base image digest are we on | `docker/base-images.lock` |
| Why is a vulnerability accepted | `security/policy/accepted.yaml`, and ADR-0018 |
| How a number is rendered, and how a failure is | `docs/12-UI-DESIGN.md` |
| Which tasks are done | `tasks/STATUS.md`, generated from the plan files |
| How often does this data refresh | `docs/06-DATA-FRESHNESS.md` |
| What does this script do | `scripts/README.md` |
| How do I record what a session cost | `make dev` to start, `make stats` to report. See `README.md` |
| Why does this project exist, what counts as success | `docs/00-GOAL.md` |
| What are we building and in what order | `docs/01-ROADMAP.md` |
| Why was a technology chosen | `docs/adr/` |
| How do the pieces fit together | `docs/02-ARCHITECTURE.md` |
| What exactly is P0 delivering | `docs/specs/2026-08-23-p0-foundation-design.md` |
| What exactly is P2 delivering | `docs/specs/2026-08-23-p2-query-cost-governance-design.md` |
| What is done and what is left | `tasks/STATUS.md` |
| What is broken, what is risky, what is undecided | `tasks/ISSUES.md` |
| Where did the last session stop | `docs/checkpoint.md` |
| What rules must a change follow | `CLAUDE.md` |
| Where is a specific function | `context_index.md` |

## Source material outside the repository

| Item | Location | Relevance |
| --- | --- | --- |
| Grafana query cost audit prototype | `publicsampledashboard.zip`, containing `sample_lambda.py` and `sample_report.html` | The starting point for sub project P2. Assessed in `tasks/ISSUES.md`, ISS-020 to ISS-027 |
