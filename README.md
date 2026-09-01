# Meter

A production grade FinOps platform for AWS, built so GCP, Azure and PCF can be
added later as connectors rather than rewrites.

> **Coming back after a break? Read section 1, then section 2. That is enough
> to work safely. Everything else is reference.**

---

## 0. What this is, and why

Meter answers four questions for an entire AWS Organization.

1. What are we spending, on which resource, and why did it change?
2. What are we wasting, and what is the defensible right size?
3. What is about to hurt us, in quota headroom and in runaway query cost?
4. What is running, and how is it connected?

**The trigger.** Grafana dashboards pointed at CloudWatch Logs Insights, left on
a one second auto refresh over a seven day window, produced a 100,000 USD bill
in one week. Nothing detected it, nothing prevented it, and nobody owned it.
Meter treats that class of problem as a first class feature, not an
afterthought. That is sub project P2, and it is the part of this product with no
off the shelf substitute.

**Current state: design phase. No application code has been written yet.**
`tasks/STATUS.md` is the authoritative position.

---

## 1. If you remember nothing else

| # | Rule | Why |
| --- | --- | --- |
| 1 | **`INDEX.md` is the entry point. `docs/registry.yaml` is the source of truth.** | Everything derived is generated. Change a status in the registry, run `make doc-sync` |
| 2 | **Never hand edit a generated block.** They carry a warning header | `make check-docs` fails, and your edit is lost on the next sync |
| 3 | **No dependency without `make dep-check pkg=<name>` passing.** Zero findings, any severity | It scans the whole transitive tree, which is where vulnerable code actually arrives |
| 4 | **Never render a failed collection as zero.** | A confidently wrong total destroys trust in every other number permanently |
| 5 | **Images are `linux/amd64`.** A push never converts an arm64 image | The failure reads as `exec format error`, which looks like a corrupt binary |
| 6 | **No em dashes or en dashes anywhere.** | Enforced by `make check-writing`, in code, docs, commits and UI copy |
| 7 | **Signing without verifying proves nothing.** Every deploy verifies the signature and the SBOM attestation first | Otherwise anyone able to push to ECR can place an unscanned image where the deploy finds it |

Full rules: [CLAUDE.md](CLAUDE.md). Read it before making any change.

---

## 2. Where do I find the answer to X

**`INDEX.md` first, always.** It lists every feature, decision, change, issue
and open question with a pointer to the detail.

| I want to know | Read |
| --- | --- |
| Anything at all, starting point | [INDEX.md](INDEX.md) |
| **Any status**: feature, decision, change, issue, open question | [docs/registry.yaml](docs/registry.yaml) |
| Why this project exists, what counts as success | [docs/00-GOAL.md](docs/00-GOAL.md) |
| What is being built and in what order | [docs/01-ROADMAP.md](docs/01-ROADMAP.md) |
| How the pieces fit together | [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) |
| **Where does this change get recorded** | [docs/03-CHANGE-CONTROL.md](docs/03-CHANGE-CONTROL.md) |
| How code reaches production | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| Security policy, scanners, gates | [docs/05-SECURITY.md](docs/05-SECURITY.md) |
| How often data refreshes, and its limits | [docs/06-DATA-FRESHNESS.md](docs/06-DATA-FRESHNESS.md) |
| **The database schema and migration rules** | [docs/07-DATA-MODEL.md](docs/07-DATA-MODEL.md) |
| Why a decision was made | [docs/adr/](docs/adr/README.md), 14 records |
| What exactly P0 delivers | [docs/specs/](docs/specs/2026-08-23-p0-foundation-design.md) |
| **What to build next, and how** | [docs/plans/P0-implementation-plan.md](docs/plans/P0-implementation-plan.md) |
| What one feature does | `docs/features/FEAT-nnn-*.md`, 42 of them |
| What is done, in progress, remaining | [tasks/STATUS.md](tasks/STATUS.md) |
| What is broken, risky, or undecided | [tasks/ISSUES.md](tasks/ISSUES.md) |
| **Where did the last session stop** | [docs/checkpoint.md](docs/checkpoint.md) |
| The module layout | [project_map.md](project_map.md) |
| How files depend on each other | [docs/architecture/file-graph.md](docs/architecture/file-graph.md) |
| Corrections already received | [tasks/lessons.md](tasks/lessons.md) |
| What each script does | [scripts/README.md](scripts/README.md) |
| **Is the security posture currently clean** | `security/POSTURE.md` |

---

## 3. Common tasks

```bash
make help                  # every target, 39 of them
```

### Starting a session

```bash
cat docs/checkpoint.md     # where the last session stopped, with a resume vector
cat tasks/STATUS.md        # what is done and what is next
```

### Ending a session

```bash
make session-end           # regenerates derived docs, runs the checks,
                           # then lists what is left to do by hand
```

It will remind you to add a checkpoint row with a resume vector, update
`tasks/STATUS.md` if a task changed state, and add a lesson if you were
corrected.

### Changing a status

```bash
$EDITOR docs/registry.yaml   # one line
make doc-sync                # every derived view updates together
```

Never edit the status in `INDEX.md`, the roadmap, `STATUS.md` or a feature
header. Those four are generated from the registry.

### Before adding a dependency

```bash
make dep-check pkg=some-library          # Python
make dep-check pkg=some-package npm=1    # frontend
```

### Before a merge request

```bash
make verify     # lint, writing rules, doc checks, tests, security scan
```

### Local development

```bash
make hooks-install  # once per machine: pre commit and pre push gates
make setup          # virtualenv plus frontend dependencies
make up             # PostgreSQL, LocalStack, API, dispatcher, worker, web
make migrate        # apply Alembic migrations
make psql           # database shell
make down           # stop, keep data.  make nuke  deletes the volume
```

**What LocalStack is doing in the stack.** It emulates the AWS APIs Meter
calls: STS, SQS, S3, Secrets Manager, Organizations, Cost Explorer, Logs and
CloudWatch. Without it, running the ingestion loop locally needs a real AWS
account, real credentials on every developer machine, and it **bills for every
Cost Explorer and `GetMetricData` call**. For a product whose purpose is
stopping runaway cloud spend, a development loop that quietly bills per
keystroke is the wrong default.

**What it is not.** LocalStack is not AWS. Community edition **does not enforce
IAM**, its pagination and throttling behaviour differ, and its error codes are
not always the real ones. It proves the plumbing works. It does not prove the
AWS semantics are right.

```bash
pytest -m contract -v         # the real check: same contract, fake and aws adapters
pytest tests/providers/aws    # moto backed, closer to real behaviour
```

Never conclude "it works" from LocalStack alone, and **never test a permission
boundary against it**. See gotcha 5.10.

### Building and scanning images

```bash
make buildx-setup   # once, creates the cross platform builder
make build          # builds linux/amd64 and verifies it
make scan-local     # scans the built images via the compose security profile
```

`make up` does not start the scanners. They live in a `security` profile,
because a container cannot gate an image that already exists and is already
running. See section 4.

---

## 4. Security: how nothing vulnerable gets in

**The threshold is zero findings at any severity.** Not zero critical, not zero
high. Zero.

### Six layers, and which ones actually stop something

They are not equivalent. It matters which ones can stop a deploy.

| # | Layer | When | Stops a deploy | Skippable |
| --- | --- | --- | --- | --- |
| 1 | Dependency admission, `make dep-check` | Before a dependency is added | Stops the addition | Yes, locally |
| 2 | Pre commit hooks | Before a commit exists | No | Yes, locally |
| 3 | Pre push hooks | Before code leaves the machine | No | Yes, locally |
| 4 | Pipeline scan stage | After build, before deploy | **Yes** | **No** |
| 5 | **Provenance verification** | Immediately before deploy | **Yes** | **No** |
| 6 | Nightly posture scan | Against the running digest | Raises, does not roll back | **No** |

Layers 1 to 3 are convenience. They make the answer arrive in seconds rather
than minutes. Skipping them only defers the same answer to layer 4, which is
why they are allowed to be skippable.

```bash
make hooks-install   # once per machine, gives you layers 2 and 3
```

Every commit: secrets, writing rules, lint, generated document drift, and the
dependency gate **only when a manifest changed**. Scanning the whole transitive
tree on every commit would make committing unbearable and the hook would be
disabled within a week, which is how a security control dies. Every push: the
full scan and the tests.

### What each layer does

| # | Detail |
| --- | --- |
| 1 | Resolves the dependency into a throwaway environment and scans the **whole transitive tree**, not just the named package. A CI job repeats it on any manifest change, so it cannot be skipped by editing `pyproject.toml` directly |
| 4 | grype plus trivy plus a syft SBOM plus a cosign signature, on every image. Two scanners deliberately, because their databases differ and the difference is where a missed finding lives |
| 5 | Verifies the cosign signature **and** the SBOM attestation before deploy. An image with no attestation was never scanned by this pipeline |
| 6 | Scans the digest **actually running** in each environment, read from the ECS task definition |

**Layer 5 is the admission control for this project, and it is the one most
projects leave out.** Signing at build time proves an image came from this
pipeline. Verifying immediately before deploy is what makes the signature
useful, because without verification anyone able to push to ECR can put an
unscanned image where the deploy will find it.

**Layer 6 is the one people forget.** A CVE published tonight against a
dependency shipped last week turns a green build red with no code change. A
pipeline that scans only at build time reports zero forever while the deployed
image degrades silently.

Two registry side settings complete the posture:

- **ECR enhanced scanning** (Amazon Inspector) on every repository, which
  continuously rescans stored images as advisories are published. If both it
  and the nightly job are silent, an image is genuinely clean rather than
  merely unscanned.
- **Immutable tags**, so a tag cannot be repointed at a different image after
  it was scanned and signed.

### Base images

Minimus from `reg.mini.dev`, built from source with only runtime dependencies,
rebuilt continuously. For contrast, the official Python image ships 400 plus
known vulnerabilities before your first line of code.

### Why the scanners are not a compose service

A reasonable instinct is to put a scanner in `docker-compose.yml` so nothing
runs unscanned. It does not work, for a structural reason.

**A container cannot gate an image that already exists and is already
running.** By the time a compose service starts, the image is built, on disk,
and startable by anyone with Docker. Worse, it produces a false sense of
enforcement, which is more dangerous than none because it stops people looking
for the real gate.

So the scanners live in a `security` profile that does not start with
`make up`:

```bash
make scan-local     # build, then scan with the compose security profile
```

Convenience, not a control. The controls are layers 4, 5 and 6.

### If a finding does get through

```bash
make security-scan      # full scan, writes a timestamped HTML report
make security-fix-dry   # what it would change, and what it will not touch
make security-fix       # applies on a branch, runs tests, re scans
```

The HTML report lists every finding with its severity, package, installed and
fixed version, which scanners saw it, and **the exact remediation command**.

`security-fix` applies patch and minor upgrades to published fixed versions,
runs the full test suite, and re scans to confirm the finding actually closed.

> **It applies to a branch and never auto merges.** An unattended upgrade that
> breaks production is worse than the vulnerability it closed, and the change
> has to be evidenced and approved anyway. Major version bumps, findings with no
> published fix, and transitive packages with no direct pin are **proposed with
> the reason attached, never applied**, because each needs a judgement a script
> cannot make.

### If a finding genuinely cannot be fixed

Add a time boxed entry to `security/policy/allowlist.yaml` with a named owner
and an expiry no more than 90 days out.

**Never lower a threshold.** A lowered threshold is invisible. An expiring
allowlist entry is not, and an expired entry breaks the build rather than
lapsing silently into permanent acceptance.

### If a dependency is blocked entirely

Do not write custom code. Follow the escalation in
[ADR-0013](docs/adr/ADR-0013-seven-rung-ladder-and-disqualification.md):
document the disqualification with evidence, **exhaust the current rung first**
(a patched version? an alternative package? a maintained fork?), escalate one
rung at a time, write an ADR, and get a security sign off if a CVE was the
trigger.

The most common wrong turn is jumping straight to custom code because a
dependency has a CVE.

### Where the evidence lives

```
security/POSTURE.md               current posture, regenerated by every scan
security/reports/latest/          the most recent full report
security/reports/YYYY-MM-DD-.../  every past scan, committed
security/sbom/                    one SBOM per image per build
security/reviews/                 automated code review reports
security/policy/allowlist.yaml    exceptions, each with an owner and expiry
```

Reports are committed, so the posture at any commit is reconstructable. An
auditor asking what was known on a given date gets an answer from the
repository, not from memory.

---

## 5. Gotchas that will bite you

Each one costs an afternoon the first time. Each entry shows what you actually
see, and what to type.

---

### 5.1 `exec format error` on the server

**You see**

```
standard_init_linux.go:228: exec user process caused: exec format error
Essential container in task exited
```

**What happened.** You built on an Apple Silicon machine, so the image is
`linux/arm64`. **A push does not convert it.** The registry now holds an arm64
image and the amd64 host cannot run it. The message looks like a corrupt
binary, which is why this costs an afternoon.

**Check**

```bash
docker image inspect meter-api:$(git rev-parse --short HEAD) --format '{{.Os}}/{{.Architecture}}'
# want: linux/amd64
# bad:  linux/arm64
```

**Fix**

```bash
make buildx-setup     # once per machine
make build            # pins linux/amd64, then verify-platform checks it
```

---

### 5.2 `docker exec` into a running container fails

**You see**

```
OCI runtime exec failed: exec failed: unable to start container process:
exec: "sh": executable file not found in $PATH
```

**What happened.** The runtime images have **no shell and no package manager**.
That is deliberate: it is most of why the image has near zero vulnerabilities.
See ADR-0010.

**Fix.** Do not add a shell back. Debug from outside instead.

```bash
docker compose logs -f api                          # local
aws logs tail /ecs/meter-api-dev --follow            # deployed

# Need a shell to poke at dependencies? Use the builder stage, which has one.
docker build --target builder -f docker/Dockerfile.api -t meter-api-dbg .
docker run --rm -it meter-api-dbg sh
```

---

### 5.3 A container will not start, and the logs are empty

**You see** the task starting and stopping with no application output.

**What happened.** Something in the image uses shell form, for example
`CMD ["sh", "-c", "python -m finops_ingest.${METER_ROLE}"]`. With no shell,
nothing expands `${METER_ROLE}` and there is no shell to report the failure.

**Fix.** Exec form only, and pass the variable part as an argument.

```dockerfile
ENTRYPOINT ["/opt/venv/bin/python", "-m"]
CMD ["finops_ingest.worker"]
```

```json
// ECS task definition, dispatcher service
"command": ["finops_ingest.dispatcher"]
```

---

### 5.4 `make check-docs` fails after you edited a document

**You see**

```
FAIL: 1 generated document(s) out of step

  INDEX.md: generated block differs from the registry

Run 'make doc-sync'. Do not hand edit a generated block, see ADR-0014.
```

**What happened.** You edited inside a block marked
`<!-- generated:features start -->`. Those are rebuilt from
`docs/registry.yaml`, so your edit would be silently lost on the next sync.

**Fix.** Make the change where the fact lives.

```bash
$EDITOR docs/registry.yaml    # change status: Planned -> Specified
make doc-sync                 # index, roadmap, status and the feature header all update
```

---

### 5.5 The build fails on a dependency that worked yesterday

**You see**

```
FAIL: 1 finding(s) not covered by a valid allowlist entry.
  [High      ] CVE-2026-11111       examplelib 2.3.0 -> 2.4.1
```

**What happened.** Nothing you did. A new advisory was published against a
dependency you already shipped. This is normal and it is why the nightly scan
exists.

**Fix**

```bash
make security-fix-dry    # what it would change, and what it will not touch
make security-fix        # applies on a branch, runs tests, re scans
```

If there is no published fix, or it is a major version bump, the script will
say so with the reason. Then follow ADR-0013: look for a patched version, then
an alternative package, then escalate one rung. **Do not write custom code
because a dependency has a CVE.** That is the single most common wrong turn.

---

### 5.6 The build fails and the allowlist "looks fine"

**You see**

```
FAIL: 1 problem(s) in security/policy/allowlist.yaml

  CVE-2026-11111: EXPIRED on 2026-08-20. Make a fresh decision and add a
  new entry. Do not edit the date.
```

**What happened.** An exception someone accepted 90 days ago has expired. That
is the entire point of the expiry: an accepted risk gets re examined rather
than becoming permanent by forgetting.

**Fix.** Re examine it. Is there a fix now? Then take it and delete the entry.
Still no fix and still acceptable? Add a **new** entry with today's date and a
current reason.

```yaml
exceptions:
  - id: CVE-2026-11111
    package: examplelib
    target: meter-api
    reason: >
      Re examined 2026-08-23. Vulnerable path is the XML parser, which this
      service does not call. Upstream fix still unreleased, tracked at
      https://github.com/example/examplelib/issues/412
    owner: name@example.com
    added: 2026-08-23
    expires: 2026-11-21
```

Editing the old date instead is how an accepted risk quietly becomes permanent.

---

### 5.7 `make check-writing` fails on a file you did not touch

**You see** the check print the offending file and line, with the line quoted
back at you, and then:

```
FAIL: em dash or en dash found. See CLAUDE.md writing rules.
```

**What happened.** An em dash or en dash arrived in a paste, or from an editor
that auto converts a double hyphen while you type.

**Fix.** Replace it with a comma, a colon, or parentheses.

```bash
make check-writing        # prints file and line for every instance
```

Note the trap: writing the offending characters into a document **about** the
rule makes the check fail on its own documentation. That happened twice while
writing this project, once in `CLAUDE.md` and once in this very section. Refer
to the characters by name, never by reproducing them.

Turn off smart substitution in your editor. On macOS: System Settings,
Keyboard, Text Input, Text Replacements, and disable smart dashes.

---

### 5.8 Cost numbers look stale

**You see** a figure that has not moved since yesterday, and a screen showing
`as_of 2026-08-22` while `collected_at` says twenty minutes ago.

**What happened.** Probably nothing wrong. **CUR refreshes at most three times
a day** and Cost Explorer is roughly 24 hours behind. Freshness is capped by
AWS, not by Meter, which is why every figure carries two timestamps.

**Check.** Is the collector actually running, or is the source simply that old?

```bash
curl -s localhost:8000/api/v1/health/freshness | jq
```

A collector past its configured cadence is flagged stale even when it has data.
If the collector is healthy and the number is old, the number is correct and
the source is old. See `docs/06-DATA-FRESHNESS.md`.

---

### 5.9 A number is zero and you are not sure whether that is real

**You see** an account showing 0 in a total.

**What happened.** One of two completely different things, and telling them
apart is a design goal of this product. Either the source genuinely returned no
data, or a collection failed and something rendered the failure as a zero. The
second is a defect, tracked as ISS-015.

**Check.** The ingest screen distinguishes them, and so does the API.

```bash
curl -s localhost:8000/api/v1/ingest/runs | jq '.data[] | {collector, scope_key, status, error_type}'
```

`NoData` is the only error type that legitimately renders as zero.
`AccessDenied`, `Throttled`, `NotOptedIn`, `Unreachable` and `SchemaDrift` must
never do so.

---

### 5.10 LocalStack says it works, then real AWS does not

**You see** a collector that passes locally and returns `AccessDenied` or a
truncated result against a real account.

**What happened.** LocalStack is not AWS. Community edition **does not enforce
IAM**, and its pagination and throttling behaviour differ. It proves the
plumbing, not the semantics.

**Fix.** Never conclude "it works" from LocalStack, and never test a permission
boundary against it.

```bash
pytest -m contract -v    # runs the same contract against fake and aws adapters
pytest tests/providers/aws -v    # moto backed, closer to real behaviour
```

---

## 6. Identifiers

| Prefix | Meaning | Lives in |
| --- | --- | --- |
| `FEAT-nnn` | A capability the product provides | `docs/registry.yaml`, detail in `docs/features/` |
| `ADR-nnnn` | A decision expensive to reverse | `docs/adr/` |
| `CHG-nnnn` | A material change | `docs/registry.yaml` |
| `ISS-nnn` | A defect, risk or gap | `docs/registry.yaml`, detail in `tasks/ISSUES.md` |
| `OPEN-nn` | A question awaiting a person | `docs/registry.yaml` |
| `TASK-Pn-nnn` | A unit of implementation work | `docs/plans/` |

Identifiers are never reused and never renumbered. A withdrawn item is marked
`WITHDRAWN` and kept.

---

## 7. Build order

Deliberately not numeric. P2 is second because a working prototype already
exists, its return is provable in the first month, and stopping a 100,000 USD
per week bleed buys the political capital to fund the rest.

```
P0 Foundation
   |
   +--> P2 Query Cost Governance   (fast, visible, differentiated)
   +--> P1 Cost Intelligence
           +--> P3 Utilization and Rightsizing
           +--> P4 Inventory and Topology --> P5 Quotas and Limits
           +--> P6 Containers, EKS and ECS
                   +--> P7 Insight and LLM layer
```

**Start with TASK-P0-029, not TASK-P0-001.** It verifies the Minimus image tags
actually exist and that every declared dependency passes the admission gate.
Discovering at task 016 that a base image is missing would invalidate three
Dockerfiles and a pipeline.

---

## 8. Waiting on a decision from you

These block work and cannot be resolved from inside the repository. Current
list and detail in `INDEX.md` section 6.

| ID | Question | Blocks |
| --- | --- | --- |
| OPEN-01 | ADFS relying party, IAM Identity Center, or reuse the AWS relying party | Production login. Not the P0 build |
| OPEN-02 | Single payer or multiple payer accounts | P1 design |
| OPEN-03 | Is Business or Enterprise support available | P3 and P5 coverage |
| OPEN-04 | Amazon Managed Grafana only, or self hosted and Grafana Cloud too | P2 scope |
| OPEN-05 | Jira or ServiceNow for the recommendation lifecycle | P3 design |
| OPEN-06 | Which regions beyond Ireland and London | P0 dispatcher configuration |

There are also external dependencies needing management account cooperation.
See `tasks/STATUS.md`.

---

## 9. Technology

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic |
| Frontend | React with TypeScript, Cytoscape.js for graphs |
| Compute | ECS Fargate |
| Infrastructure as code | Terraform |
| Database | Aurora Serverless v2 PostgreSQL, Alembic migrations |
| Analytics | Athena and Glue over CUR 2.0 Parquet, extract and load only |
| Base images | Minimus, `reg.mini.dev` |
| Canonical cost schema | FOCUS 1.1 |
| Local AWS emulation | LocalStack, development only, never a permission test |
| Scanners | grype, syft, trivy, pip-audit, npm audit, gitleaks, cosign |
| Scale assumption | 50 to 300 accounts, 10 to 100 GB CUR per month |

Deliberately excluded for now: ClickHouse, Redshift, Neptune, Kubernetes.
The trigger to revisit is measured, not felt: p95 dashboard latency above
1.5 seconds.

---

## 10. Repository layout

```
INDEX.md              master index, the entry point
README.md             this file
CLAUDE.md             binding rules for every change
project_map.md        module level map
context_index.md      function level index

docs/
  00-GOAL.md          goal, success criteria, non goals
  01-ROADMAP.md       eight sub projects, build order
  02-ARCHITECTURE.md  ports, FOCUS, ingestion, security posture
  03-CHANGE-CONTROL.md  where each change is recorded, update cadence
  04-DEPLOYMENT.md    GitLab to ECR to Terraform to ECS
  05-SECURITY.md      zero vulnerability policy and gates
  06-DATA-FRESHNESS.md  refresh cadence and its limits
  07-DATA-MODEL.md    every table, constraint, index, Alembic rules
  registry.yaml       SOURCE OF TRUTH for the generated documents
  checkpoint.md       session continuity, with resume vectors
  adr/                14 architecture decision records
  specs/              approved design specifications
  plans/              implementation plans and task documents
  features/           one document per feature, 42 of them
  architecture/       generated file dependency graph
  templates/          spec, task, ADR, change, issue, feature templates

security/             posture, policy, allowlist, reports, SBOMs, reviews
scripts/              every script, grouped into security, docs, ci, deploy
docker/               three Dockerfiles on Minimus, plus nginx config
tasks/                STATUS.md, ISSUES.md, lessons.md

finops-core/          PLANNED  domain and ports. No cloud SDK, ever
finops-providers/     PLANNED  aws/, fake/, gcp/, azure/
finops-ingest/        PLANNED  dispatcher, worker, ledger, collectors
finops-api/           PLANNED  FastAPI, scope enforcement, routes
finops-mcp/           PLANNED  MCP server, a facade over the HTTP API
finops-web/           PLANNED  React and TypeScript
infra/terraform/      PLANNED  hub/, member/, management/
```

---

## 11. Architectural constraints that are expensive to break

Full list in `CLAUDE.md`. The three that would cost a rewrite:

1. **`finops-core` never imports a cloud SDK.** This is what makes GCP and
   Azure a connector instead of a rewrite. Enforced by an import linter
   contract in `pyproject.toml`, so it fails CI rather than relying on
   intention.
2. **Scope is enforced in two places**, a request dependency and a repository
   guard. A route that forgets the dependency must still be unable to read out
   of scope data. An adversarial test asserts exactly that.
3. **The HTTP API is the single enforcement point.** The MCP server is a facade
   that calls it over the network with the caller's token. Two implementations
   of an authorization rule is how an authorization bug is created.
