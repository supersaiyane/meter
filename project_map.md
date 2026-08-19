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
├── Makefile                   28 targets, run `make help`
├── pyproject.toml             dependencies, lint rules, import linter contract
├── docker-compose.yml         local stack only, never used to deploy
├── .gitlab-ci.yml             verify, build with Kaniko, plan, deploy
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
│   ├── features/              one document per feature, 42 of them
│   ├── architecture/          generated file dependency graph
│   ├── templates/             spec, task, ADR, change and issue templates
│   ├── checkpoint.md          session continuity log with resume vectors
│   ├── adr/                   architecture decision records, 0001 to 0008
│   ├── specs/                 approved design specs, one per sub project
│   │   └── 2026-08-23-p0-foundation-design.md
│   └── plans/                 implementation plans and task docs
│       └── P0-implementation-plan.md   28 tasks in 8 waves
│
├── tasks/
│   ├── STATUS.md              done, in progress, remaining
│   ├── ISSUES.md              issue and open question register with fixed status
│   └── lessons.md             corrections converted into rules
│
├── docker/                    three Dockerfiles on Minimus, plus nginx.conf
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
│   ├── security/              scan, admission gate, report, auto fix, allowlist
│   ├── docs/                  index check, feature doc check, file graph
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
| What exactly do I build next, and how | `docs/plans/P0-implementation-plan.md` |
| What does this feature do | `docs/features/FEAT-nnn-*.md` |
| How do these files depend on each other | `docs/architecture/file-graph.md`, `make graph` |
| What is the security policy | `docs/05-SECURITY.md` |
| Is the posture currently clean | `security/POSTURE.md` |
| How often does this data refresh | `docs/06-DATA-FRESHNESS.md` |
| What does this script do | `scripts/README.md` |
| Why does this project exist, what counts as success | `docs/00-GOAL.md` |
| What are we building and in what order | `docs/01-ROADMAP.md` |
| Why was a technology chosen | `docs/adr/` |
| How do the pieces fit together | `docs/02-ARCHITECTURE.md` |
| What exactly is P0 delivering | `docs/specs/2026-08-23-p0-foundation-design.md` |
| What is done and what is left | `tasks/STATUS.md` |
| What is broken, what is risky, what is undecided | `tasks/ISSUES.md` |
| Where did the last session stop | `docs/checkpoint.md` |
| What rules must a change follow | `CLAUDE.md` |
| Where is a specific function | `context_index.md` |

## Source material outside the repository

| Item | Location | Relevance |
| --- | --- | --- |
| Grafana query cost audit prototype | `publicsampledashboard.zip`, containing `sample_lambda.py` and `sample_report.html` | The starting point for sub project P2. Assessed in `tasks/ISSUES.md`, ISS-020 to ISS-027 |
