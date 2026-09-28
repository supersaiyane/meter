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

## Counted, not claimed

<!-- generated:map-counts start -->
<!-- This block is GENERATED from the source by scripts/docs/check_map_counts.py. Hand edits here are overwritten and make check-docs will fail. Every figure below is derived, which is the point: three sweeps in two days found stale counts in this file when they were written by hand. See ADR-0014 and tasks/lessons.md. -->

| Counted | Now | Derived from |
| --- | --- | --- |
| Screens built | 22 of 26 | `arrives: null` in finops-web/src/shell/sections.ts |
| Playwright journeys | 15 in 4 spec files | `test(` calls in finops-web/e2e/*.spec.ts |
| Inventory routes | 7 | `@router.` in finops_api/routes/inventory.py |
| Collectors | 21 | modules in finops_ingest/collectors, excluding __init__ |
| Migration revisions | 20 | files in migrations/versions, all of which are listed below in this file |
| Test files | 124 | test_*.py under tests/ |
| Test functions | 1709 | functions named test_* under tests/. Not the pytest collected total, which counts every parametrised expansion and which only `make verify` can report |

No prose line in this file repeats a figure from this table. That is the rule, and it
exists because the figures in the prose were wrong on three consecutive sweeps.

<!-- generated:map-counts end -->

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
├── Makefile                   every routine task, run `make help`. `verify` is
│                              the gate: backend tests, frontend unit tests, a
│                              typed web build and the Playwright journeys.
│                              `test-e2e` depends on `build-web` because vite
│                              preview serves the build output without building
│                              it, and the journeys once passed against a bundle
│                              seven hours older than the source.
│                              `test` is every backend test in one invocation,
│                              integration included, so `verify` needs Docker.
│                              It was the not integration subset until
│                              2026-09-06, which left 211 tests outside the gate
│                              and is where ISS-175 and ISS-177 both lived.
│                              `test-unit` and `test-integration` are slices for
│                              narrowing down a failure and report no coverage,
│                              because a fraction graded against the whole
│                              suite's threshold cannot be read. ISS-154
├── pyproject.toml             dependencies, lint rules, import linter contract.
│                              Packages are found, not listed: an explicit list
│                              is top level only and left subpackages out of the
│                              built wheel
├── docker-compose.yml         local stack only, never used to deploy. Every
│                              python service takes env_file, so a new setting
│                              does not have to be added twice, and the postgres
│                              host port is overridable with METER_POSTGRES_PORT
├── .gitlab-ci.yml             verify, security, build, scan, plan, deploy. Its
│                              test job runs both suites against the PostgreSQL
│                              service beside it, through METER_TEST_DATABASE_URL.
│                              **Never executed**: the repository has no remote,
│                              so nothing here is a result. ISS-178, ISS-179
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
│   ├── registry.yaml          SOURCE OF TRUTH for the generated documents.
│   │                          Edit here then run make doc-sync, never edit
│   │                          ISSUES.md or INDEX.md by hand. A colon followed
│   │                          by a space in a plain scalar breaks the parse
│   ├── feature-flags.yaml     every flag, its owner, reason, expiry, removal
│   ├── features/              one document per feature, 51 of them
│   ├── architecture/          generated file dependency graph, plus
│   │                          overview.html, the one hand written file there:
│   │                          the whole system drawn, and the only place that
│   │                          says in one view what has never run against AWS
│   ├── design/                hand written interface mocks, wired to nothing.
│   │                          home-redesign.html carries the three tier front page,
│   │                          its four open decisions, and the severity to accent
│   │                          collision. 2026-09-27-home-direction.html is the
│   │                          answer to the design pass of that day being rejected
│   │                          in full: a different visual language built from the
│   │                          seeded figures, and its header says which of its
│   │                          numbers are real, because a mockup that passed
│   │                          invented numbers off as measured ones would be doing
│   │                          the thing this product exists to stop
│   ├── reference/             source Meter was built from, read never imported.
│   │                          sample_lambda.py.txt is the 2,740 line prototype
│   │                          P2 was planned against, byte identical to the
│   │                          import. The .txt is deliberate: check-writing
│   │                          greps every .py and the prototype has em dashes,
│   │                          and correcting it would stop it being evidence
│   ├── templates/             spec, task, ADR, change and issue templates
│   ├── checkpoint.md          session continuity log with resume vectors
│   ├── adr/                   architecture decision records, 0001 to 0008
│   ├── specs/                 design specs, one per sub project. P1's section 3
│   │                          named what it deferred, and its section 16
│   │                          records what changed when that came back
│   │   ├── 2026-08-23-p0-foundation-design.md
│   │   ├── 2026-08-23-p2-query-cost-governance-design.md
│   │   ├── 2026-09-18-p1-cost-intelligence-design.md
│   │   ├── 2026-09-20-p3-utilization-and-rightsizing-design.md
│   │   │                      Section 5.5 is the one to read: what a realized
│   │   │                      saving can honestly claim, and why a third
│   │   │                      verdict of inconclusive exists
│   │   ├── 2026-09-20-p4-inventory-and-topology-design.md
│   │   │                      Section 6 is the whole sub project: an edge Meter
│   │   │                      cannot see is not an absent edge, and a partial
│   │   │                      graph still renders and answers wrongly
│   │   ├── 2026-09-20-p5-quotas-and-limits-design.md
│   │   │                      Section 6 is a refusal: a quota increase is a
│   │   │                      write, so Meter drafts and tracks it and never
│   │   │                      submits it. The IAM permission is absent
│   │   └── 2026-09-20-p6-containers-design.md
│   │                          Section 5.4 is the cost of having no agent in the
│   │                          cluster, stated per signal so the trade can be
│   │                          revisited with evidence rather than memory
│   └── plans/                 implementation plans, written per sub project.
│                              `sync.py` reads task status out of these, so the
│                              Status row in each task is data, not prose. It
│                              globs rather than listing them, since a literal
│                              list once hid P1's whole plan from the table
│       ├── P0-implementation-plan.md
│       ├── P1-implementation-plan.md
│       ├── P2-implementation-plan.md
│       ├── P3-implementation-plan.md    20 tasks, not started
│       ├── P4-implementation-plan.md    11 tasks, not started
│       ├── P5-implementation-plan.md     8 tasks, not started
│       └── P6-implementation-plan.md    12 tasks, first cut, not started
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
├── docker/                    three Dockerfiles on Minimus, plus three nginx
│                              configs: nginx.conf is the deployed one,
│                              nginx.local.conf adds the /api proxy the load
│                              balancer does in a real environment, and
│                              nginx.disabled.conf is empty and copied over the
│                              base image's own server block, which would
│                              otherwise win every request whose Host is
│                              localhost. ISS-150 and ISS-151.
│                              Builder stages run as root and are discarded; the
│                              runtime stages keep USER 65532:65532, which is the
│                              posture ADR-0010 protects. The api image also
│                              carries scripts/ops, because those are run by a
│                              person against a live database, and carries neither
│                              scripts/demo nor finops_fakes, because a module that
│                              fabricates a bill has no business in the image that
│                              reports a real one. ADR-0022
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
│   ├── reports/               one directory per scan. `latest` is a committed
│   │                          symlink and is relative, because an absolute one
│   │                          stored an author's home directory, ISS-164.
│   │                          Whether every timestamped directory belongs in the
│   │                          repository is open, ISS-165
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
│                              Linted and type checked since 2026-09-02. They are
│                              the gates, and were outside the linter until then
│   ├── README.md              what each script does and how it is run
│   ├── security/              scan, admission gate, pre commit deps, report,
│   │                          auto fix, allowlist validation
│   ├── docs/                  sync.py, check_index.py, check_feature_docs.py,
│   │                          build_file_graph.py, build_context_index.py,
│   │                          rotate_checkpoint.py, add_lesson.py.
│   │                          sync.py derives the sub projects in the task
│   │                          table from the plan files present. It used to
│   │                          iterate a literal, and P1 was absent from the
│   │                          table rather than shown as 13 not started
│   ├── ci/                    code_review.py, check_flags.py, check_hardcoded.py,
│   │                          check_forbidden_imports.py, check_memory.py,
│   │                          check_env_keys.py, refresh_base_images.py. Flag and
│   │                          hardcoding checks, forbidden imports, the memory
│   │                          gate, base image resolver. check_env_keys names the
│   │                          settings .env.example has gained that a local .env
│   │                          never did, before make up starts anything: it is
│   │                          copied once and never again, so eleven accumulated
│   │                          over one session and the failure was eleven lines of
│   │                          Field required from inside a container. It reports
│   │                          and never writes, because the one thing worse than a
│   │                          missing key is a credential quietly replaced with an
│   │                          example value. check_memory also reads the Next
│   │                          action section and refuses a numbered candidate
│   │                          naming an issue the registry says is FIXED: that
│   │                          section went stale twice in two days by proposing
│   │                          work that had just been finished, and it is the part
│   │                          of the checkpoint a cold session reads first
│   ├── ops/                   run by a person against a live database, which is
│   │                          why the api image carries this directory and only
│   │                          this one. erase_principal.py, deliberately not an
│   │                          API route. local_token.py mints a session.
│   │                          restore_drill.py restores a copy into a scratch
│   │                          database, migrates it, starts the application
│   │                          against it and reads the freshness route. Refuses
│   │                          any non local host before an engine exists
│   ├── demo/                  needs the fakes, so it is not in the image and not
│   │                          in `scripts/ops`. Split out 2026-09-21 with
│   │                          ADR-0022, so what the image contains follows from
│   │                          where a file lives rather than from a comment.
│   │                          seed_demo.py fills a local database by running the
│   │                          real collectors against the fake adapters and
│   │                          through the real run ledger, so seeded rows cannot
│   │                          drift from collected ones and the ingest and
│   │                          freshness screens fill from the same act.
│   │                          DEMO_TABLES is its teardown, and a test derives it
│   │                          from the schema so a new tenant scoped table cannot
│   │                          be forgotten there. ISS-176. --days runs the
│   │                          collectors once per day at that day's clock, which
│   │                          is how a trend gets a history. It writes no charges
│   │                          of its own since ISS-197: the bill names every
│   │                          estate resource, so the savings screen reads the
│   │                          rows a cost screen shows. Refuses any non local
│   │                          host before an engine exists, and make unseed
│   │                          clears it by its fixed tenant.
│   │                          export_fake_estate.py writes the estate to CSV,
│   │                          which is build output and is never committed
│   └── deploy/                migration task runner
│
├── tests/                     the suite. Its size is in the counted table above, as test
│                              files and test functions; the pytest total is what `make
│                              verify` prints and is not repeated here, because it counts
│                              parametrised expansions and nothing else can compute it.
│                              conftest.py refuses to run
│                              against a real AWS account when no endpoint
│                              override is set, and its session scoped `engine`
│                              starts a PostgreSQL container and migrates it,
│                              which is why the gate needs Docker and why one
│                              invocation is cheaper than two.
│                              METER_TEST_DATABASE_URL runs against a database
│                              that already exists instead, for a runner with a
│                              service and no socket. Not METER_DATABASE_URL,
│                              which every `.env` sets, and the host is checked
│                              because the fixture migrates and writes. ISS-178.
│                              test_checkpoint_rotation.py covers the only script
│                              that deletes rows from the memory log.
│   ├── api/                   test_fixture_surfaces.py reads the frontend's
│   │                          FIXTURE_SURFACES and fails the build if one of
│   │                          those templates is a live route, so a screen
│   │                          cannot keep serving invented numbers. It also
│   │                          asserts it examined something: a check that finds
│   │                          nothing must not report success
│   ├── contract/              one suite, parameterised over providers. Run with
│   │                          make test or pytest -m contract
│   └── scripts/               the gates tested as code: the index checker, the
│                              pipeline shape, the layer orderings held equal, the
│                              alarms against their runbooks, and the lint scope
│                              asked of the filesystem rather than of a list
│
├── finops_core/               IN BUILD  domain and ports. No boto3, no framework
│   ├── errors.py              the six typed failure causes, closed set, no catch all
│   ├── config.py              every METER_ variable, typed. No defaults except flags
│   ├── constants.py           the values that are decisions rather than deployments
│   └── domain/                frozen entities, no persistence and no cloud concern.
│                              cost.py holds CostRecord in FOCUS 1.1, plus
│                              BillingPeriod, whose end is exclusive and whose
│                              is_open takes the clock from the caller, and
│                              CostTotal, which cannot exist without a
│                              CostMeasure saying which of the four it is
│                              source_fingerprint is here too, so both cost
│                              adapters hash a line item's identity the
│                              same way. It takes no cost, on purpose
│       ├── fact.py            the as_of and collected_at pair, inherited not repeated
│       ├── account.py         Provider, AccountKey, CloudAccount. Never a bare id
│       ├── tenant.py          Tenant and Scope. No wildcard, empty means nothing
│       ├── org.py             OrgNode and the closed ROOT, OU, ACCOUNT set
│       ├── identity.py        Principal and Entitlement
│       ├── ingest.py          IngestRun, CollectionFailure, Watermark
│       ├── cost.py            CostRecord, FOCUS 1.1 names, Decimal money.
│       │                      Also CommitmentUse and CommitmentCoverage, kept
│       │                      apart for the reason the port keeps its methods
│       │                      apart, and BillingPeriod and source_fingerprint
│       ├── metrics.py         MetricPoint. `at` is the instant, `as_of` the freshness
│       ├── resource.py        ResourceRef. Opaque identifier, never parsed
│       └── quota.py           QuotaUsage. Unpublished usage is None, never zero
│   └── ports/                 protocols only. No implementation, no cloud import.
│                              query.py also declares QueryParser and
│                              QueryEvidence, which exist so an adapter can name
│                              what it needs without importing the layer above it
│       └── query.py           QuerySurface, the first port not about a cloud,
│                              plus QueryParser. An adapter may not import
│                              finops_query, so it names the parsing it needs
│                              here and a collector supplies it
│       ├── accounts.py        AccountDiscovery
│       ├── credentials.py     CredentialBroker plus the opaque ProviderSession
│       ├── cost.py            CostExport
│       ├── commitment.py      CommitmentReport, two methods on purpose.
│       │                      Utilization is per commitment, coverage is per
│       │                      service, because a covered dollar cannot be
│       │                      attributed to one of several overlapping plans.
│       │                      One method returning both would invite that
│       │                      fabrication. Not a widening of CostExport: a
│       │                      Savings Plan is not a line item
│       ├── metrics.py         MetricSource
│       ├── inventory.py       ResourceInventory
│       ├── quotas.py          QuotaSource
│       └── identity.py        IdentityProvider and EntitlementResolver
├── finops_providers/          IN BUILD  aws/, grafana/, gcp/, azure/. The fakes
│                              left this package on 2026-09-21, ADR-0022
│   ├── aws/                   the only package that imports boto3
│   │   ├── client.py          bounded config, and provider code to typed cause
│   │   ├── credentials.py     assume role, cached until before expiry
│   │   ├── accounts.py        the exact org tree. Every call paginated
│   │   ├── health.py          is the role usable, and if not, whose fix is it
│   │   ├── platform_cost.py   the one Cost Explorer request, grouped
│   │   ├── commitment.py      utilization and coverage, four Cost Explorer
│   │   │                      calls. **Never yet run**, ISS-122. Savings
│   │   │                      Plans report money and reservations report
│   │   │                      hours, so half its figures are measured and
│   │   │                      half are modelled, and _reservation_money says
│   │   │                      which is which
│   │   ├── query_evidence.py  runs from CloudTrail, bytes from query history.
│   │   │                      A window that saw nothing returns an absent key,
│   │   │                      never a zero: absent means unobserved
│   │   └── cur.py             the billing export through Athena. **Never yet
│   │                          run**, ISS-122, and COLUMNS is the part only a
│   │                          real export can settle. A period comes back
│   │                          whole or raises, never short, because short and
│   │                          retracted look identical to the collector's
│   │                          delete. That buys a memory ceiling, ISS-181
│   ├── grafana/               AMG only, per OPEN-04 re answered 2026-09-02
│   │   ├── client.py          raises a typed cause. A workspace it cannot read
│   │   │                      must not report zero dashboards
│   │   └── amg.py             QuerySurface over AMG. A region it cannot list
│   │                          becomes a visible unreachable instance, never a
│   │                          shorter list. The token is a loan, revoked in a
│   │                          finally. v1 writes nothing, constraint 6
├── finops-web/                IN BUILD  Vite, React and TypeScript
│   ├── README.md              why the versions are pinned where they are
│   ├── components/BarChart.tsx  the days, drawn. Hand rolled SVG like Sparkline,
│   │                          so no charting dependency needs admitting and
│   │                          nothing animates a bar up from zero, which is a
│   │                          number lying for four hundred milliseconds. Not a
│   │                          sparkline: that one refuses to be read off and this
│   │                          one has a scale and a labelled peak. Bars start at
│   │                          zero, because a non zero baseline makes a normal
│   │                          week look like a crisis
│   ├── components/BudgetBar.tsx  spend against a limit with the calendar drawn on
│   │                          top of it. The tick is the point: ninety five
│   │                          percent spent is healthy on the twenty eighth and
│   │                          alarming on the fourth, so the fill alone carries no
│   │                          finding. Shared by the home tile and the budgets
│   │                          screen, because a fill computed one way in one place
│   │                          and another way in the other is two pictures of one
│   │                          fact. The fill is clamped, so an overspent budget
│   │                          draws full and says OVER beside it rather than
│   │                          running past its own track
│   ├── components/lateness.ts  the age over the cadence, and nothing else. Its
│   │                          own module because the screen's count and the bar
│   │                          must decide lateness the same way: a sentence saying
│   │                          one collector is late above bars showing two is the
│   │                          fault a reader finds first
│   ├── components/CadenceBar.tsx  how late a collector is against its own
│   │                          cadence, which is a third scaling rule because
│   │                          neither of the other two fits: collectors do not
│   │                          add up so a share of a total is wrong, and there is
│   │                          no maximum so a fraction of one is wrong too. The
│   │                          track runs to twice the cadence with the due point
│   │                          in the middle, so the only question a reader has is
│   │                          answered by which side of the tick the fill ends on.
│   │                          Past twice, the bar stops and the end is notched,
│   │                          because a collector at nine times and one at two and
│   │                          a half would otherwise draw identically. Two
│   │                          absences with two sentences: no age is never
│   │                          collected, no cadence is not scheduled, and they
│   │                          need different actions
│   ├── scripts/build_world.mjs  generates the coastline from Natural Earth 110m,
│   │                          run by `make world`. Its two dependencies are dev
│   │                          only and never reach a browser: what ships is a
│   │                          committed string of path data, so the page draws a
│   │                          real coastline with no mapping library and no fetch
│   ├── components/worldPaths.ts  GENERATED, never edited by hand. The projection
│   │                          it was made with travels in the same file, because a
│   │                          second copy that drifted would put every marker in
│   │                          the wrong sea
│   ├── components/worldLand.ts  where each continent's marker sits, and nothing
│   │                          else now. It held hand written coastlines for one
│   │                          revision and they drew shapes nobody recognised.
│   │                          Coordinates may be written down here when a region
│   │                          coordinate table may not, and that is the whole
│   │                          distinction: a region table is a fact about somebody
│   │                          else's estate and goes stale the day they open
│   │                          another region, while a coastline is a fact about
│   │                          the world
│   ├── components/WorldMap.tsx  the estate on a world map, equirectangular and
│   │                          cropped to the latitudes people run things in. It
│   │                          shipped first as a graticule and two dots, on the
│   │                          argument that a coastline implies a precision the
│   │                          prefix lacks, and that was wrong about where the
│   │                          claim lives: a coastline says this is the world, and
│   │                          it is the marker position that would claim a
│   │                          datacentre. Markers are sized by area, so
│   │                          four times the resources is four times the ink:
│   │                          sizing by radius would claim four times again. The
│   │                          positions live here rather than in the domain because
│   │                          where a continent sits in a picture is a fact about
│   │                          the picture, and a geography with no position is
│   │                          still in the legend and counted in a sentence. The
│   │                          SVG is aria-hidden and the legend is the content and
│   │                          the control, since markers are not reachable from a
│   │                          keyboard
│   ├── screens/GeographyScreen.tsx  FEAT-061. The map, three leftovers that are
│   │                          never added together, and the resources of whichever
│   │                          continent was clicked. Nothing loads until one is
│   │                          chosen, because a screen that loads the first has
│   │                          decided which continent matters
│   ├── components/rankedRows.ts  the collapse and the truncation, and the one
│   │                          place a ranked chart can be quietly wrong: a total
│   │                          taken after the remainder was folded in makes every
│   │                          share too large and the picture still looks right.
│   │                          On the largest basis nothing is summed at all, not
│   │                          even into a rest row, because that sum is the number
│   │                          the basis exists to avoid
│   ├── components/PercentCell.tsx  a percentage in a table cell with a rule
│   │                          under it. A fraction of a hundred and never a share
│   │                          of a total, which is why it is not RankedBars: two
│   │                          services at eighty percent coverage are both at
│   │                          eighty percent and neither is half of anything. It
│   │                          owns the absence, because that is the rule most
│   │                          likely to be undone by a later edit while every
│   │                          rendering assertion still passes: a null renders the
│   │                          caller's words and draws no bar, since an empty
│   │                          track reads as a measurement that came back zero and
│   │                          for a commitment that says the money was wasted.
│   │                          Deliberately not built on BudgetBar, which is a ten
│   │                          pixel card bar with a pace tick: the two share three
│   │                          lines of clamping and no context
│   ├── components/RankedBars.tsx  the second chart. Horizontal and CSS rather
│   │                          than SVG, because its axis is categories and a
│   │                          category is a word: vertical bars would need
│   │                          rotated labels nobody reads or truncation that
│   │                          hides what the row is about. Bars are a share of
│   │                          the total and not of the largest, since scaling to
│   │                          the largest makes one owner at ninety percent look
│   │                          like three evenly matched. Past the limit the
│   │                          remainder is summed into a row that says how many
│   │                          it stands for, because showing the top eight of
│   │                          forty silently is a lie by omission. The bars are
│   │                          aria-hidden decoration and every number is written
│   │                          as text, which is the opposite of BarChart, where
│   │                          twenty six rows would be unreadable. Hatch means
│   │                          modelled and an outline means a row that is not one
│   │                          of the things being ranked, one device each, because
│   │                          a mark with two meanings cannot be read. Used by the
│   │                          allocation screen and the waste queue
│   ├── screens/BudgetsScreen.tsx  FEAT-060. Budgets with a number, then the ones
│   │                          without, counted, with the reason on each card. Two
│   │                          reasons kept apart because they need different
│   │                          actions: an unsupported scope is never fixed by
│   │                          waiting and an uncollected period is
│   ├── src/tokens.css         the palette, and the only file that decides what a
│   │                          colour means. Three surface depths because a card
│   │                          needs to differ from the page without a shadow,
│   │                          three inks because a dense screen needs a value, a
│   │                          label and a thing worth skipping, and an accent
│   │                          reserved for interactive alone. The severity ramp
│   │                          and the hatch fills predate the 2026-09-27
│   │                          direction and survived it, because provenance
│   │                          carried by fill rather than by colour is the
│   │                          product rather than the styling
│   ├── src/layout.css         the shell, the tables, and since 2026-09-27 the
│   │                          vocabulary a screen writes for itself. That last
│   │                          section exists because nothing styled it: p was
│   │                          used twenty two times with no selector, so every
│   │                          heading, list and control fell back to the
│   │                          browser and twenty screens of careful tokens read
│   │                          as an unstyled document
│   ├── e2e/                   the Playwright journeys, counted in the table above,
│   │                          against the built bundle rather than the test
│   │                          renderer. They are what proves the honesty rules
│   │                          survive the build. The figure is read from what
│   │                          `make verify` runs, not from counting files: this
│   │                          line said five for three sub projects, which is
│   │                          how long a count in prose stays wrong
│   ├── eslint.config.js       flat config. eslintrc is not read by ESLint 9.
│   │                          Names all three tsconfig projects: a file in none
│   │                          of them is a fatal parse error, not a skip
│   ├── tsconfig.e2e.json      the project the journeys and playwright.config.ts
│   │                          belong to. Lint only, deliberately outside the
│   │                          build so specs stay out of the declarations
│   └── src/
│       ├── tokens.css         light and dark in one declaration, via light-dark().
│       │                      Tokens, and the classes that carry meaning. The
│       │                      severity ramp is warm because a blue one ended on
│       │                      the accent, the dark failure red is saturated
│       │                      rather than light so it outranks the prose beside
│       │                      it, and the faces are IBM Plex, self hosted, so a
│       │                      column of figures is the same width everywhere
│       ├── storage.ts         the one place that knows browser storage is
│       │                      allowed to refuse. A blocked browser throws on
│       │                      the property access, and reading the token
│       │                      without this stopped the application starting
│       ├── shell/AppShell.tsx the frame. Trust strip, the page heading, and a
│       │                      navigation column that collapses to 56 px, hidden
│       │                      rather than covered, remembered per browser
│       ├── shell/sections.ts  the seven navigation groups, one matchFor behind
│       │                      screenTitleFor and activeGroupFor so the heading
│       │                      and the open accordion cannot disagree, and
│       │                      the one place a screen's name is decided, so the
│       │                      heading and the menu cannot disagree
│       ├── layout.css         where things sit. Element selectors, because
│       │                      DataTable is the only table and Figure the only
│       │                      numeral. Needs no component to accept a className,
│       │                      which is the property ADR-0021 was decided on
│       ├── components/        built once, used by every sub project. All ten of
│       │                      12-UI-DESIGN section 11 exist, plus FixtureBand,
│       │                      which that inventory predates
│       │   ├── Figure.tsx     the load bearing one. Nothing else renders a number.
│       │   │                 Dense inside a table, and its accuracy clause keeps
│       │   │                 its comma on the word before, so a wrap in a narrow
│       │   │                 surface never starts a line with punctuation
│       │   ├── provenance.ts  the union that makes a point forecast unsayable
│       │   ├── StateBoundary.tsx  all seven states from design section 8, plus
│       │   │                 coverageShownElsewhere, which drops the coverage
│       │   │                 sentence and never the rows, for tiles that sit
│       │   │                 under a shell already making the claim
│       │   ├── surfaceState.ts    which of the seven a query is in, one decision
│       │   ├── DataTable.tsx  virtualised past 200 rows, headless
│       │   ├── tableConfig.ts column widths and alignment. Numerals right, always
│       │   ├── TypedError.tsx cause and remediation. Never a numeral
│       │   ├── CoverageBanner.tsx  not dismissible. The condition does not go away
│       │   ├── FreshnessIndicator.tsx  age against cadence, not a fixed threshold
│       │   ├── SeverityBadge.tsx   sequential ramp, because severity is ordered
│       │   ├── OrgTree.tsx    keyboard navigable. The accessible path, not the fallback
│       │   ├── orgNodes.ts    tree to flat nodes. Unreachable branches survive it
│       │   ├── GraphCanvas.tsx     Cytoscape, server filtered, tree is its equivalent
│       │   ├── Sparkline.tsx  30 day, no axes, provenance aware
│       │   ├── FixtureBand.tsx  says a screen is not connected yet. Not gated
│       │   │                on a build flag: a marker shown only in development
│       │   │                is absent exactly when it matters
│       │   └── index.ts       exports no formatter, deliberately
│       ├── App.tsx            BrowserRouter and the routes. An unbuilt screen
│       │                      renders differently from a wrong address
│       ├── api/               typed client. Refuses a response with no envelope
│       │   ├── queries.ts     one hook per route, plus useQuerySurface for a
│       │   │                  surface whose route does not exist yet
│       │   ├── fixtureSeam.ts FIXTURE_SURFACES and resolveSurface. Route
│       │   │                  templates, not urls, so a detail path matches.
│       │   │                  A failing route raises, it never falls back
│       │   └── fixtures/      ships in the bundle. Production code, not test
│       │       └── query.ts   findings, details, instances and enforcement
│       │                      actions. Carries a null count beside a genuine
│       │                      zero, and an unreachable instance beside a
│       │                      reachable one. A happy path only fixture pins the
│       │                      wrong screen
│       ├── shell/             the trust strip. One band, full width, above
│       │                      everything, per 13-UI-ARCHITECTURE section 8. It
│       │                      was in the sidebar, where the freshness line fell
│       │                      below the fold on a 1440 px screen, ISS-156.
│       │                      Coverage states one line per thing counted, since
│       │                      a page can hold panels counting different things
│       │                      and no single ratio is true of both, ISS-157
│       │   └── sections.ts    GROUPS, the seven of ADR-0020. It never grows: a
│       │                      sub project adds screens inside an existing group
│       └── screens/           how many are built is in the counted table above, derived
│                              from the `arrives` field in sections.ts, which is why that
│                              field exists. This line stated it anyway for three sub
│                              projects and was wrong twice. Three of the
│                              four P2 screens read live routes since TASK-P2-021;
│                              enforcement stays fixture backed and says so,
│                              because TASK-P2-016 is parked. TopologyScreen is
│                              P4's, and its map is the second Cytoscape surface:
│                              the table beside it is the accessible path rather
│                              than the fallback, as on the organization screen
│           ├── querySeverity.ts       the word to the ramp. Its own module
│           │                          because two screens rank the same findings
│           │                          and a second copy is a second answer
│           ├── sliceCoverage.ts       how a slice that was not read whole is
│           │                          said. Extracted for FEAT-053, because the
│           │                          map says it above the drawing and the
│           │                          entity page above the neighbour list, and
│           │                          that is one claim about one row
│           ├── EntityScreen.tsx       FEAT-053, one resource. Reached from the
│           │                          map rather than from the navigation, like
│           │                          the query finding detail page. Two of its
│           │                          five sections are admissions: the coverage
│           │                          of the slice it came from, above the
│           │                          neighbour list, and the count of findings
│           │                          in the account that joined to no resource
│           │                          at all, which is ISS-205 measured rather
│           │                          than argued about
│           ├── HomeScreen.tsx          owns no data of its own. Three tiers: a
│           │                           summary of four tiles, the findings worth
│           │                           acting on, then ArrivingRail. The tiles
│           │                           read four hooks that four other screens
│           │                           already own, and each links to its owner.
│           │                           An unfilled slot still
│           │                           names the sub project that will fill it,
│           │                           in one rail rather than a panel each, so
│           │                           a promise does not outweigh a number.
│           │                           Every figure is read through the owning
│           │                           screen's own hook
│           ├── QueryFindingDetailScreen.tsx  the working, and since ISS-172 the
│           │                           cost on every day it was audited. One
│           │                           observation is said in words, never drawn
│           ├── QueryAdhocScreen.tsx    the queries that belong to nobody. Every
│           │                           figure measured, because there is no
│           │                           definition to model one from
│           ├── QueryFindingsScreen.tsx ranked by cost as decimals, with a trend
│           │                           column since ISS-172. The reason is
│           │                           a column, because a tooltip is invisible
│           │                           in a screenshot
│           ├── QueryFindingDetailScreen.tsx  publishes the working. A test
│           │                           derives each cost from its own inputs,
│           │                           because a sum that fails when checked is
│           │                           worse than no sum
│           ├── findingFigure.ts        cost to figure. Accuracy is passed through
│           │                           only when published, never invented
│           ├── QuerySurfacesScreen.tsx unreachable instances listed with their
│           │                           cause. A null count is not a zero, and
│           │                           both appear here so neither is mistaken
│           ├── EnforcementScreen.tsx   revoke absent, not disabled, when the API
│           │                           says so. Constraint 8: one enforcement
│           │                           point, not two
│           ├── enforcementTime.ts      both expiry forms, dated and in UTC. A
│           │                           bare time made a three day old control
│           │                           read as this morning
│           ├── AccountsScreen.tsx      broken onboarding is one filter, not four
│           ├── OrganizationScreen.tsx  tree default, graph secondary
│           ├── IngestScreen.tsx        runs with typed causes per account
│           ├── FreshnessScreen.tsx     per collector, against its own cadence
│           ├── PlatformScreen.tsx      Meter's own cost, untagged named
│           ├── platformRollUp.ts       one grouped total, no second definition
│           └── surfaceStateFor.ts      the screen side of surfaceState
│
├── finops_fakes/              NOT SHIPPED  the estate, and every port in memory.
│                              Outside `finops_providers` and absent from the wheel
│                              since 2026-09-21, because a module that fabricates a
│                              bill has no business in the image that reports a real
│                              one. An import contract forbids all six production
│                              packages from reaching it, and it is linted and type
│                              checked to the same standard as production code,
│                              because a fake nobody checks drifts from its port.
│                              ADR-0022. Imported by the tests and by scripts/demo/.
│                              No network and no clock, enforced by a test that walks
│                              the syntax tree refusing any name that reads like one
│   ├── cur.py             the estate's bill. One line per estate resource, so a
│   │                     charge joins to the thing it is about, plus aggregate
│   │                     lines for the two services that name no resource. 22
│   │                     percent untagged on purpose, and the account Meter
│   │                     cannot read is on it, because the bill comes from the
│   │                     payer. LANDED moves three resources' cost and usage by
│   │                     different amounts from one day, which is what lets the
│   │                     realized savings collector reach all three verdicts
│   │                     from charges rather than from a fixture. ISS-197
│   ├── prices.py          what every estate resource costs, derived from its own
│   │                     configuration. Invented, and labelled as invented. Read
│   │                     by cur.py and by estate_metrics.py, because two price
│   │                     lists drifting apart is how an estimated saving and a
│   │                     realized saving disagree about the fixture rather than
│   │                     about the estate
│   ├── utilization.py     the generated estate: 36 resources, two years of
│   │                     hourly behaviour, three regions. Deterministic, so
│   │                     the 29 MB export is output and this is the source,
│   │                     and the export is never committed
│   ├── estate_shape.py    the curves every generator shares: diurnal,
│   │                     seasonal, jitter from a seed, and the calendar
│   │                     predicates. No clock and no randomness, enforced
│   │                     by a test that walks the syntax tree
│   ├── estate_metrics.py  the estate behind the MetricSource port, so a
│   │                     collector reads it through the port it already
│   │                     speaks. A refusal omits its key rather than failing
│   │                     the batch, because absent means unobserved
│   ├── planted.py         58 expected outcomes with a reason each, the oracle
│   │                     a detector is checked against. The NO_FINDING half
│   │                     is the valuable half: it names the false positives,
│   │                     and it found two on its first run, ISS-195 and 196
│   ├── containers.py      clusters, workloads and node groups. P6's estate
│   ├── topology.py        95 nodes and 129 edges. P4's estate
│   ├── quotas.py          130 quotas including the ones nothing can measure,
│   │                     and five increase requests with their status
│   │                     history. P5's estate
│   ├── fixtures.py        one root, two units, five accounts, one denied
│   ├── provider.py        the failure plan. Any of the six, for any scope.
│   │                     Takes the time it is observed at, because the
│   │                     constants are right for a test and wrong for a
│   │                     demo estate
│   ├── health.py          role health. Separates an account whose role is
│   │                     misconfigured from one Meter could not ask about
│   │                     at all, which are different fixes and owners
│   ├── platform_cost.py   Meter's own bill, untagged bucket included
│   ├── evidence.py        CloudTrail and query history in memory. days_ago
│   │                     reports the same queries run fewer times, at the
│   │                     same bytes per run, so a measured cost is carried
│   │                     by the run count while the scan size holds still
│   ├── surface.py         the dashboards, and queries_as_of, which returns
│   │                     them as they stood. A modelled cost is computed
│   │                     from the definition, so it steps on the day
│   │                     somebody edited one rather than drifting daily
│   ├── surface.py         QuerySurface in memory. discover raises only when
│   │                     nothing could be enumerated, and an empty listing
│   │                     means empty rather than a failed read
│       └── evidence.py        QueryEvidence in memory, keyed on the query as
│                             executed rather than as stored, because that is
│                             the gap match_observed exists to cross
├── finops_ingest/             IN BUILD  dispatcher, worker, ledger, collectors
│   ├── ledger.py              idempotent claims, watermarks that only advance
│   ├── registry.py            what a collector is. Cadence lives in the database
│   ├── dispatcher.py          one message per unit, keyed like the ledger claim
│   ├── remediation.py         the only two writes Meter makes, both gated on
│   │                          query_write_level and both recording what they
│   │                          replaced. A rewrite reads back and reverts itself
│   │                          if it did not take, and records nothing when it
│   │                          does, because a change row claims the estate
│   │                          changed and stayed changed
│   ├── worker.py              one transaction per unit. Only the six are caught
│   └── collectors/
│       ├── org_tree.py        whole tree replaced in one transaction, never emptied
│       ├── account_health.py  role_health written every run, including failed ones
│       ├── platform_cost.py   one grouped request a day. Untagged cost is named
│       ├── query_audit.py     six hourly. An instance it cannot read is written
│       │                     as unreachable, and evidence it cannot read is filed
│       │                     under query_evidence in sync_error so the silence is
│       │                     visible. It also writes the ad hoc rows, which are
│       │                     the executions no definition claims
│       │                      unreachable and the run continues, and the upsert
│       │                      is keyed on the day so three runs leave one finding
│       ├── cost_focus.py      the bill, one billing period at a time. Keyed on
│       │                      source_fingerprint, so a restated row lands on the
│       │                      row it corrects. Every row carries the run that
│       │                      last wrote it, and a row this run did not see is
│       │                      removed, scoped to one tenant and one period.
│       │                      A half read removes nothing: the transaction rolls
│       │                      it back, and the removal sits downstream of
│       │                      finishing the read. Creates no partitions on purpose
│       ├── retention.py       six jobs. Anonymises, never removes a principal row.
│       │                      Its cost job also writes cost_focus_monthly, but only
│       │                      for months past the cutoff as it drops them
│       ├── cost_rollup.py    cost_focus_monthly, one body and two predicates,
│       │                    shared by the collector and retention. Only the
│       │                    collector may prune, because retention's rows have
│       │                    to outlive the partitions it drops
│       ├── cost_anomaly.py    judges one day, the most recent with data, because re
│       │                      judging history rewrites verdicts somebody may have
│       │                      acted on. Reads twice the window it needs and takes the
│       │                      last days that have data, so a quiet Sunday does not
│       │                      starve it. Refuses without settings: severity comes
│       │                      from the money and a default would invent one
│       ├── commitment.py      two reads, two upserts, one transaction. A window is
│       │                      replaced rather than accumulated, and NoData is absorbed
│       │                      because a payer with no commitments is a fact rather
│       │                      than a broken collection
│       ├── partitions.py      months created ahead. Without one, cost rows are refused
│       ├── inventory.py       the resources themselves, from AWS Config. ISS-200: it
│       │                      has never made a real call
│       ├── topology.py        the edges between them, four APIs. ISS-202, same footing
│       ├── waste_compute.py   the bespoke candidates, which are the ones carrying an
│       │                      ARN and therefore the ones that join to a node
│       ├── waste_cloudwatch.py  log retention and alarms that have never fired
│       ├── waste_parking.py   FEAT-054. A workload quiet on the same hours every week,
│       │                      judged per hour and never per estate, because a window
│       │                      of a fortnight straddles three Monday weeks
│       ├── commitment_actions.py  FEAT-055. An uncovered baseline as a finding with
│       │                      an owner, in its own table per ADR-0025
│       ├── realized_savings.py  FEAT-041. The only thing in the product allowed to
│       │                      say a saving happened, sixty days after a finding is
│       │                      marked done
│       ├── score.py           the posture score, which is never a bare number
│       ├── iac_state.py       FEAT-057. Presence and never absence: a row means we
│       │                      found a resource in state, no row means we did not look
│       │                      or did not find it, and those are different facts
│       └── budgets.py         FEAT-060. What somebody said this should cost, read from
│                              the provider. Stores nothing derived, retracts nothing,
│                              and counts the budgets whose scope it cannot reproduce
│                              on sync_error rather than dropping them
│   └── metrics.py             only SLO 1 needs a custom metric. The other three are AWS's
│   ├── tests/contract/test_cause_vocabulary.py  the only test that crosses the
│   │                          language boundary. The seven causes are mirrored in
│   │                          six places and the two halves are different
│   │                          languages, so nothing in a type checker or a
│   │                          migration catches a divergence: the collector
│   │                          succeeds, the database accepts the row, and a screen
│   │                          renders a cause it has no label for. ADR-0026 names
│   │                          this and the five tests beside it rather than
│   │                          counting the places, because the count was written
│   │                          by looking and was wrong twice
│   └── tests/providers/aws/test_response_shapes.py  not a module, but the one
│                              place that says what the four unproven adapters
│                              depend on. Every response field they read, every
│                              pagination token and every required request
│                              parameter, checked against the botocore service
│                              model boto3 builds its clients from. It makes no
│                              call and closes nothing: it removes the part of
│                              ISS-200, ISS-202, ISS-209 and ISS-211 that is about
│                              names. It also pins which declared errors fall
│                              through to SchemaDrift, which is ISS-215
├── finops_api/                IN BUILD  FastAPI, scope enforcement, routes
│   ├── flags.py               flag resolution, tenant then environment then declared
│   ├── main.py                app factory. Refuses to start on a bare route
│   ├── deps.py                the first scope point. Scope comes from the resolver
│   ├── middleware.py          request id on every line and back on the response
│   ├── schemas.py             the meta envelope. degraded is computed, never set
│   ├── routes/                the seven P0 routes, all returning the envelope.
│   │                          inventory.py holds P4's routes, counted above: the subgraph,
│   │                          the estate
│   │                          wide coverage banner, the roots to start a map
│   │                          from, FEAT-053's one resource and FEAT-056's list
│   │                          of them all, which is what closed ISS-204. The
│   │                          subgraph response carries the coverage of
│   │                          every slice it crossed, so a screen cannot draw the
│   │                          map without the list of what is missing from it.
│   │                          cost.py is P1's four: summary, by service, by
│   │                          account and trend, plus allocation by tag key.
│   │                          An open period says so in the payload, because
│   │                          two copies of a calendar rule is one that is
│   │                          eventually wrong in one of them
│   │   ├── me.py              principal, tier, scope summary
│   │   ├── accounts.py        accounts in scope, plus the role health recheck
│   │   ├── org.py             the tree. Out of scope branches marked, not hidden
│   │   ├── ingest.py          runs with typed errors, and freshness per cadence
│   │   │                      over every pair that has been attempted rather
│   │   │                      than every pair that has succeeded. A watermark
│   │   │                      only exists after a success, so listing those
│   │   │                      omitted the row a reader comes for, ISS-163
│   │   ├── platform.py        Meter's own cost, unallocated included
│   │   └── query.py           five of the eight P2 routes, including the two
│   │                          that write. Every write refuses first: the level,
│   │                          then whether the finding is an actual violation,
│   │                          then whether a control exists at all. The other five read
│   │                          data that does not exist yet, ISS-148. Coverage
│   │                          here counts workspaces, not findings
│   ├── guards.py              the scope guard. No default, empty means nothing.
│   │                          Three shapes: tenant only, ByAccount for a row
│   │                          that names its account, and Through for one that
│   │                          does not and inherits from the row it hangs off.
│   │                          Through recurses, so a finding is scoped through
│   │                          its definition through its instance
│   ├── identity/              behind the two ports ADR-0008 parked
│   │   ├── local_config.py    users from a file. Refused in prod by config.py
│   │   ├── session.py         signed, carries the scope, always expires
│   │   └── coverage.py        visible over the organization total, never over visible
│   └── db/
│       ├── models.py          twenty tables as SQLAlchemy Core. A second
│       │                      description of the schema, and the drift test is
│       │                      what stops the two disagreeing
│       └── repositories/      the only path to a scoped table, audited on read.
│                              latest_audit_only confines a read to the newest
│                              audit of each thing, per table, because every
│                              audit table is keyed on the day and a list that
│                              ignores that sums a week of them. ISS-175,
│                              ISS-177
│
├── alembic.ini                no database URL in it, env.py reads the settings
├── migrations/                the only way the schema changes
│   ├── env.py                 URL from settings, overridable by a test
│   └── versions/              raw SQL, faithful to 07-DATA-MODEL and to the P2
│                              spec section 5. Additive only, per constraint 12
│       ├── 0001_initial.py    the thirteen P0 tables
│       ├── 0002_cost_monthly.py  somewhere for retention to aggregate into
│       ├── 0004_query_key.py  a nullable query_key, so evidence can attach to a
│       │                      query rather than to one panel drawing it
│       ├── 0005_finding_cause.py  the cause a finding is grouped by, beside the
│       │                      prose that explains it, because a vocabulary nobody
│       │                      can group by is a column nobody reads
│       ├── 0006_refresh_floor.py  the refresh floor a workspace enforces on
│       │                      itself, which is the one query cost input the
│       │                      provider supplies rather than us modelling it
│       ├── 0007_query_adhoc.py  the queries that belong to nobody, FEAT-051
│       ├── 0008_cost_anomaly.py  a day that did not look like the days before
│       │                      it. Three thresholds concurrently, which is the
│       │                      specific thing that stops anomaly detection
│       │                      becoming noise and then being muted
│       ├── 0009_commitment_coverage.py  what was committed, what it consumed and
│       │                      what it covered, at two grains, because a covered
│       │                      dollar cannot be attributed to one of several
│       │                      overlapping plans
│       ├── 0010_recommendations.py  one table for every source, and an append
│       │                      only event log, because a lifecycle column cannot
│       │                      say that somebody accepted a finding and nothing
│       │                      then happened
│       ├── 0011_realized_saving.py  the measured half, in its own table so it
│       │                      cannot be summed with the estimate by accident
│       ├── 0012_realized_usage_unobserved.py  the usage columns go nullable and
│       │                      a paired check refuses a verified saving with no
│       │                      control behind it
│       ├── 0013_finops_score.py  the score and its components in two tables,
│       │                      because last week's components cannot be
│       │                      recomputed once the findings have changed
│       ├── 0014_topology.py    the graph, and graph_coverage, which is the table
│       │                      the sub project exists for. No key on to_node_id,
│       │                      because the far end of a cross account edge is
│       │                      routinely in an account Meter cannot read and a key
│       │                      would refuse exactly those rows. ADR-0023 for why
│       │                      the cause column admits seven values
│       ├── 0015_commitment_action.py  a payer wide finding in its own table,
│       │                      ADR-0025. A commitment cannot be apportioned to the
│       │                      accounts that consumed it, so a finding derived from
│       │                      one inherits that scoping rather than the scoping of
│       │                      the findings table it resembles. The cost is the
│       │                      lifecycle vocabulary written twice, held by a test
│       │                      that compares the two constraints at their source
│       ├── 0016_resource_management.py  presence and never absence. A row means we
│       │                      found a resource in state; no row means we did not
│       │                      find it, which is a different fact from nobody
│       │                      managing it. UNMANAGED is derived per request from a
│       │                      declaration about our own configuration and is never
│       │                      stored, because a stored judgement outlives the
│       │                      configuration it was made under
│       ├── 0020_quotas.py     FEAT-033 and FEAT-034. Every quota, including the
│       │                      ones nothing can measure, which are the majority in
│       │                      a real estate. One check constraint carries the sub
│       │                      project: a usage figure exists if and only if a
│       │                      source is named, refused in both directions, because
│       │                      a figure with no provenance cannot be audited later
│       │                      and renders identically to a measured one, while a
│       │                      source with no figure claims a measurement nobody
│       │                      made. limit_value is nullable too and is a different
│       │                      absence: a few quotas publish no ceiling, and zero is
│       │                      a real value meaning switched off here. The identity
│       │                      index is NULLS NOT DISTINCT, because a global quota
│       │                      carries no region and two nulls never conflict, so
│       │                      every run would add another copy of it.
│       │                      submitted_by_meter is a column that can only be
│       │                      false: constraint 6 in the schema rather than in a
│       │                      comment, so reversing it takes a migration somebody
│       │                      has to write and defend
│       ├── 0019_sizing_refusal.py  FEAT-062, ADR-0027. What a sizing rule
│       │                      examined and declined, with the sentence that
│       │                      decided it. Its own table because a refusal has no
│       │                      saving, and every consumer of recommendation ranks
│       │                      by money: a zero there reads as the least valuable
│       │                      action rather than as the absence of one. The load
│       │                      bearing constraint is a length on the reason, not a
│       │                      NOT NULL, because an empty string satisfies NOT NULL
│       │                      and a refusal reading did not qualify teaches a
│       │                      reader the explanations are empty
│       ├── 0018_misconfigured_cause.py  the seventh cause, ADR-0026. A value this
│       │                      deployment set that does not exist at the provider,
│       │                      which SchemaDrift used to absorb under a word that
│       │                      sent an operator looking for an API change when the
│       │                      fix was one line of their own settings. Widening a
│       │                      check constraint is the backward compatible
│       │                      direction, so this is one migration rather than
│       │                      three. Nothing is backfilled: rows already written
│       │                      as SchemaDrift were correct under the vocabulary of
│       │                      the day, and rewriting them would invent a judgement
│       │                      nobody made. The downgrade refuses rather than
│       │                      deletes, because dropping rows to satisfy a narrower
│       │                      constraint destroys the record of why a collection
│       │                      failed in order to make a schema change succeed
│       ├── 0017_budget.py     what somebody said this should cost, collected and
│       │                      never entered, so it carries a run id and both
│       │                      timestamps like every other fact here. Nothing
│       │                      derived is stored: the status depends on where today
│       │                      falls in the period, so a stored one is wrong by the
│       │                      next morning. limit_amount rather than limit,
│       │                      because LIMIT is reserved and a column called that
│       │                      is quoted in every statement forever. Payer wide per
│       │                      ADR-0025, and ISS-212 is what that costs
│       └── 0003_p2_tables.py  the six P2 tables. Three of its constraints are
│                              the feature: a deny cannot be written without an
│                              expiry, a modelled row cannot claim a measured
│                              count, and a change cannot exist without its undo
├── finops_query/              IN BUILD  P2 query cost governance, P3 waste, P4 graph
│   ├── blast_radius.py        FEAT-044. What a change can reach, and the refusal that
│   │                          is the feature: a score that is sometimes absent beats one
│   │                          always present, because an absent score reads as we do not
│   │                          know and a low one over a graph missing a region reads as
│   │                          this change is safe. A band rather than a number, with the
│   │                          parts published beside it, and CROSS_ACCOUNT is a different
│   │                          kind of fact rather than a wider WIDE. Every answer is a
│   │                          lower bound and the field says so, because an
│   │                          infrastructure graph cannot see an application dependency
│   ├── graph.py               the bounds, the node cap and the return type that
│   │                          carries coverage. Pure: the recursive statement is
│   │                          in the repository, because the guard's scoped_select
│   │                          lives in finops_api and this package may not import
│   │                          it. require_whole() is what FEAT-044 calls, and it
│   │                          refuses rather than answering short
│   ├── waste.py               the sizing arithmetic. p99 for CPU, observed peak
│   │                          plus a margin for memory, and the two are
│   │                          deliberately not unified: a low CPU request
│   │                          throttles, a low memory request kills. Every
│   │                          series is hourly, which is what keeps p99 from
│   │                          quietly becoming the max rule
│   ├── geography.py           FEAT-061. Where a region is, from its name and from
│   │                          nothing else. The prefix rather than a coordinate table,
│   │                          and that is the whole argument: a coordinate table has to
│   │                          name every region, so the next region a provider opens is
│   │                          invisible until somebody notices, which is exactly what
│   │                          check_hardcoded.py exists to prevent. A prefix is not a
│   │                          region, and eu-south-3 resolves on the day it opens. The
│   │                          cost is that it is continental and can never say Dublin,
│   │                          which is ISS-213. Three absences kept apart: no region at
│   │                          all is global and is not a gap, a name with no prefix
│   │                          tells us nothing, and an unknown prefix means the table
│   │                          needs a row. It also reads the compass word a name
│   │                          carries after its prefix, which is ISS-213's
│   │                          reduction: eu-west-1 and eu-central-1 are both
│   │                          Europe and the name says which part, so the drawing
│   │                          can separate them with no table of regions to go
│   │                          stale. A word and never a coordinate, because where
│   │                          a compass point lands in a picture is the picture's
│   │                          business
│   ├── iac.py                 FEAT-057, in finops_core/domain/. Three answers to what
│   │                          manages a resource, and the default is the honest one.
│   │                          Reading state tells you what is managed and never what is
│   │                          not, so UNMANAGED needs a declaration that the configured
│   │                          backends are the whole of an account's code, plus a run in
│   │                          which all of them were read. Never stored: a judgement
│   │                          outlives the configuration it was made under
│   ├── commitment.py          FEAT-055. What an uncovered baseline is worth, and the
│   │                          usage floor, which is the figure that decides whether
│   │                          buying the commitment was a mistake. The plan asked for
│   │                          a break even month and that is one on every row for a no
│   │                          upfront plan, so it would have satisfied the criterion
│   │                          and told a reader nothing
│   ├── parking.py             FEAT-054. A fortnight folded into a 168 hour week,
│   │                          returning the contiguous hours nothing runs. The
│   │                          evidence rule is per hour, not per estate: an hour
│   │                          counts when it was seen in at least two weeks and
│   │                          was quiet in every one of them. Per estate refused
│   │                          everything, because a window of now minus a
│   │                          fortnight straddles three Monday aligned weeks
│   │                          whose ragged ends share no hour. A week quiet
│   │                          throughout returns nothing: that is IDLE_INSTANCE,
│   │                          and two findings saying schedule it and delete it
│   │                          is a pair nobody can act on
│   ├── realized.py            three verdicts from two windows. The most careful
│   │                          arithmetic in the product, because it is where a
│   │                          FinOps tool usually starts lying. Where usage fell
│   │                          faster than cost, the fall cannot be claimed
│   ├── score.py               a posture score that cannot be returned as a bare
│   │                          number, plus movement() which resolves a change
│   │                          between two runs to findings that opened or closed.
│   │                          A component nobody could compute is excluded rather
│   │                          than scored nought, and an unjudged estate has no
│   │                          score at all
│   ├── classify.py            what engine a target runs on. Separate from the
│   │                          arithmetic, so a new engine is a branch not a rate
│   ├── cost_model.py          runs per day, cost per run, quota pressure. No IO,
│   │                          no clock, no client. Every figure is modelled
│   ├── severity.py           the dollar bands, ADR-0016, and the closed cause
│   │                          vocabulary findings are grouped by. Prose cannot
│   │                          be grouped on
│   ├── gate.py               the CI policy gate. No database, no credentials,
│   │                          no network, so it runs in any pipeline. It fails
│   │                          rather than warning, and names the money
│   ├── policy.py              two keys, and the difference is the point.
│   │                          fingerprint identifies one definition, because the
│   │                          unique constraint makes it a row's identity.
│   │                          query_key identifies the query itself, so measured
│   │                          evidence attaches to every panel running it. Both
│   │                          ignore template values, whitespace and comments
│   ├── ownership.py           who ran it, and measured against modelled.
│   │                          resolve_owner takes the folder map, then the last
│   │                          editor, then the CloudTrail principal, and returns
│   │                          unowned rather than inventing one
│   └── parser.py              the QueryParser port, bound to this package. It
│                              exists so the adapter below can parse without
│                              importing the layer above it
│
├── finops_mcp/                IN BUILD  MCP server, a facade over the HTTP API
│   ├── api.py                the only way out of this package, and it is HTTP
│   ├── tools.py              six rows. Schemas generated from the API's own models
│   └── server.py             binds the table to the SDK. No credential of its own
│                              Directory exists, __init__.py only. Ships as a
│                              second process on the api image, ADR-0009
└── infra/terraform/           IN BUILD  four root modules, none applied yet
    ├── management/            one read only role in the management account
    ├── member/                a service managed StackSet, so new accounts self onboard
    ├── config/                the organization Config aggregator and the recorders.
    │                          resource_types.tf is the cost decision, reviewable in
    │                          a diff: twenty two types, each group naming the feature
    │                          that needs it. COST.md carries the working for the
    │                          modelled 1,440 USD a month and says which assumption is
    │                          least certain. Validated, never planned. ISS-203
    └── hub/                   the VPC with no NAT, Aurora, SQS, ECR, ECS, ALB, alarms.
                               cost_exports.tf is P1's export bucket, Glue database
                               and Athena workgroup. The workgroup carries the result
                               location and a bytes scanned cutoff, which is what
                               stops an unpruned query scanning the whole table at
                               full price. Validated, never applied. ISS-122
```

## Planned module responsibilities

| Module | Responsibility | Depends on | Must not depend on |
| --- | --- | --- | --- |
| `finops_core` | Domain entities, the nine ports, the typed error taxonomy | nothing | boto3, botocore, fastapi, sqlalchemy, requests |
| `finops_providers/aws` | The six cloud ports implemented against boto3 | `finops_core`, boto3 | `finops_api`, `finops-web` |
| `finops_fakes` | Every port in memory, plus the generated estate. Used by the tests and by `scripts/demo/`. Not in the wheel, ADR-0022 | `finops_core` | boto3, and every production package is forbidden from importing it |
| `finops_ingest` | Dispatcher, worker, run ledger, watermarks, collectors | `finops_core`, a provider | `finops-web` |
| `finops_api` | HTTP surface, scope dependency, repository guard | `finops_core`, a provider | boto3 directly |
| `finops-web` | User interface | `finops_api` over HTTP | anything Python |
| `finops_mcp` | MCP tools for any model client | `finops_api` over HTTP | the service layer, repositories, boto3 |
| `infra/terraform` | Hub stack, member StackSet, management role, Config aggregator and recorders | nothing | nothing |

The rule that keeps multi cloud cheap: `finops_core` never imports a cloud
software development kit. It is enforced by an import linter rule in
continuous integration, not by good intentions.

## Where to look for a given question

| Question | Answer lives in |
| --- | --- |
| Anything at all, as a starting point | `INDEX.md` |
| Where do I record this change | `docs/03-CHANGE-CONTROL.md` |
| How does code reach production | `docs/04-DEPLOYMENT.md` |
| What exactly do I build next, and how | `docs/plans/P3-implementation-plan.md`, TASK-P3-020, which P4 unblocked: `topology_edge` exists and `finops_query.graph` carries the coverage FEAT-044 has to refuse on. P0 to P4 are otherwise done except for what needs an AWS account. The higher value move is still the account itself, ISS-122, which is what every unproved adapter in P1, P3 and P4 is waiting for |
| Task counts, which change | `grep -c '^### TASK' docs/plans/*.md`. Not written into prose, because a count in prose goes stale silently |
| What does this feature do | `docs/features/FEAT-nnn-*.md` |
| How do these files depend on each other | `docs/architecture/file-graph.md`, `make graph` |
| What is the shape of the whole system | `docs/architecture/overview.html`, open in a browser |
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
| What exactly is P1 delivering | `docs/specs/2026-09-18-p1-cost-intelligence-design.md`. The cost surface, and section 16 for the second cut that delivered anomalies, commitments and the export |
| What exactly is P3 delivering | `docs/specs/2026-09-20-p3-utilization-and-rightsizing-design.md`. What the estate should cost instead, and whether the bill actually moved |
| What exactly is P4 delivering | `docs/specs/2026-09-20-p4-inventory-and-topology-design.md`. What is out there and what is connected to what, and an honest record of what could not be read |
| What exactly is P5 delivering | `docs/specs/2026-09-20-p5-quotas-and-limits-design.md`. Used against limit where that can be measured, and a refusal to write the increase |
| What exactly is P6 delivering | `docs/specs/2026-09-20-p6-containers-design.md`. Namespace cost from the bill and reservation against use, in a first cut. The optimiser and the forecaster are a second |
| What is done and what is left | `tasks/STATUS.md` |
| What is broken, what is risky, what is undecided | `tasks/ISSUES.md` |
| Where did the last session stop | `docs/checkpoint.md` |
| What rules must a change follow | `CLAUDE.md` |
| Where is a specific function | `context_index.md` |

## Source material outside the repository

| Item | Location | Relevance |
| --- | --- | --- |
| Grafana query cost audit prototype | `publicsampledashboard.zip`, containing `sample_lambda.py` and `sample_report.html` | The starting point for sub project P2. Assessed in `tasks/ISSUES.md`, ISS-020 to ISS-027 |
