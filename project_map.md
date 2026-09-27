# Project map

Module level map. Check this before reading any source file, and before
searching. If it does not answer the question, the map is wrong and should be
rebuilt from source rather than worked around.

Last updated: 2026-08-23
Master index: `INDEX.md`
Update trigger: any new module, moved module, or changed responsibility.

## Current reality

The repository contains documentation, the build layer and the deployment
pipeline. No application code has been written. The tree below marks planned
modules as `PLANNED` so the map is never mistaken for a description of what
exists.

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
│   ├── runbooks/              one per paging alert, written with the alert
│   ├── registry.yaml          SOURCE OF TRUTH for the generated documents
│   ├── feature-flags.yaml     every flag, its owner, reason, expiry, removal
│   ├── features/              one document per feature, 42 of them
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
├── docker-compose.yml         local stack, plus a `security` profile of one shot
│                              scanners that does NOT start with `make up`
│
├── security/                  everything a scan produces, and the policy
│   ├── POSTURE.md             current posture, generated, never hand edited
│   ├── policy/                grype.yaml, trivy.yaml, allowlist.yaml
│   ├── reports/               one directory per scan, committed
│   ├── sbom/                  one SBOM per image per build
│   └── reviews/               automated code review reports
│
├── scripts/                   every script in the project, nothing executable elsewhere
│   ├── README.md              what each script does and how it is run
│   ├── security/              scan, admission gate, pre commit deps, report,
│   │                          auto fix, allowlist validation
│   ├── docs/                  sync, index check, feature doc check, file graph
│   ├── ci/                    code review
│   └── deploy/                migration task runner
│
├── finops-core/               PLANNED  domain and ports. No boto3, no framework
├── finops-providers/          PLANNED  aws/, fake/, gcp/, azure/
├── finops-ingest/             PLANNED  dispatcher, worker, ledger, collectors
├── finops-api/                PLANNED  FastAPI, scope enforcement, routes
├── finops-web/                PLANNED  React and TypeScript
├── finops-mcp/                PLANNED  MCP server, a facade over the HTTP API
└── infra/terraform/           PLANNED  hub/, member/, management/
```

## Planned module responsibilities

| Module | Responsibility | Depends on | Must not depend on |
| --- | --- | --- | --- |
| `finops-core` | Domain entities, the eight ports, the typed error taxonomy | nothing | boto3, botocore, fastapi, sqlalchemy, requests |
| `finops-providers/aws` | The six cloud ports implemented against boto3 | `finops-core`, boto3 | `finops-api`, `finops-web` |
| `finops-providers/fake` | Every port implemented in memory, used by all core and API tests | `finops-core` | boto3 |
| `finops-ingest` | Dispatcher, worker, run ledger, watermarks, collectors | `finops-core`, a provider | `finops-web` |
| `finops-api` | HTTP surface, scope dependency, repository guard | `finops-core`, a provider | boto3 directly |
| `finops-web` | User interface | `finops-api` over HTTP | anything Python |
| `finops-mcp` | MCP tools for any model client | `finops-api` over HTTP | the service layer, repositories, boto3 |
| `infra/terraform` | Hub stack, member StackSet, management role | nothing | nothing |

The rule that keeps multi cloud cheap: `finops-core` never imports a cloud
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
