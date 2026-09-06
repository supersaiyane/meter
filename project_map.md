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
│   ├── design/                hand written interface mocks. home-redesign.html
│   │                          carries the three tier front page, its four open
│   │                          decisions, and the severity to accent collision
│   ├── reference/             source Meter was built from, read never imported.
│   │                          sample_lambda.py.txt is the 2,740 line prototype
│   │                          P2 was planned against, byte identical to the
│   │                          import. The .txt is deliberate: check-writing
│   │                          greps every .py and the prototype has em dashes,
│   │                          and correcting it would stop it being evidence
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
│                              person against a live database
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
│   │                          rotate_checkpoint.py, add_lesson.py
│   ├── ci/                    code_review.py, check_flags.py, check_hardcoded.py,
│   │                          check_forbidden_imports.py, check_memory.py,
│   │                          refresh_base_images.py, flag and hardcoding checks,
│   │                          forbidden imports, the memory gate, base image resolver
│   ├── ops/                   erase_principal.py, run by a person against a live
│   │                          database. Deliberately not an API route.
│   │                          seed_demo.py fills a local database by running all
│   │                          collectors. DEMO_TABLES is its teardown, and a test
│   │                          derives it from the schema so a new tenant scoped
│   │                          table cannot be forgotten there. ISS-176
│   │                          --days runs the collectors once per day at that
│   │                          day's clock, which is how a trend gets a history,
│   │                          and passes each run its distance from the newest
│   │                          day so the fake estate reports the past as quieter
│   │                          four real collectors against the fake adapters and
│   │                          through the real run ledger, so seeded rows cannot
│   │                          drift from collected ones and the ingest and
│   │                          freshness screens fill from the same act. Refuses
│   │                          any non local host before an engine exists, and
│   │                          make unseed clears it by its fixed tenant.
│   │                          restore_drill.py restores a copy into a scratch
│   │                          database, migrates it, starts the application
│   │                          against it and reads the freshness route. The
│   │                          same non local refusal, for the same reason
│   └── deploy/                migration task runner
│
├── tests/                     the suite, 777 tests. conftest.py refuses to run
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
│       ├── metrics.py         MetricSource
│       ├── inventory.py       ResourceInventory
│       ├── quotas.py          QuotaSource
│       └── identity.py        IdentityProvider and EntitlementResolver
├── finops_providers/          IN BUILD  aws/, grafana/, fake/, gcp/, azure/
│   ├── aws/                   the only package that imports boto3
│   │   ├── client.py          bounded config, and provider code to typed cause
│   │   ├── credentials.py     assume role, cached until before expiry
│   │   ├── accounts.py        the exact org tree. Every call paginated
│   │   ├── health.py          is the role usable, and if not, whose fix is it
│   │   ├── platform_cost.py   the one Cost Explorer request, grouped
│   │   └── query_evidence.py  runs from CloudTrail, bytes from query history.
│   │                          A window that saw nothing returns an absent key,
│   │                          never a zero: absent means unobserved
│   ├── grafana/               AMG only, per OPEN-04 re answered 2026-09-02
│   │   ├── client.py          raises a typed cause. A workspace it cannot read
│   │   │                      must not report zero dashboards
│   │   └── amg.py             QuerySurface over AMG. A region it cannot list
│   │                          becomes a visible unreachable instance, never a
│   │                          shorter list. The token is a loan, revoked in a
│   │                          finally. v1 writes nothing, constraint 6
│   └── fake/                  in memory, the ports, no network, no clock
│       ├── fixtures.py        one root, two units, five accounts, one denied
│       ├── provider.py        the failure plan. Any of the six, for any scope.
│       │                      Takes the time it is observed at, because the
│       │                      constants are right for a test and wrong for a
│       │                      demo estate
│       ├── health.py          role health. Separates an account whose role is
│       │                      misconfigured from one Meter could not ask about
│       │                      at all, which are different fixes and owners
│       ├── platform_cost.py   Meter's own bill, untagged bucket included
│       ├── evidence.py        CloudTrail and query history in memory. days_ago
│       │                      reports the same queries run fewer times, at the
│       │                      same bytes per run, so a measured cost is carried
│       │                      by the run count while the scan size holds still
│       ├── surface.py         the dashboards, and queries_as_of, which returns
│       │                      them as they stood. A modelled cost is computed
│       │                      from the definition, so it steps on the day
│       │                      somebody edited one rather than drifting daily
│       ├── surface.py         QuerySurface in memory. discover raises only when
│       │                      nothing could be enumerated, and an empty listing
│       │                      means empty rather than a failed read
│       └── evidence.py        QueryEvidence in memory, keyed on the query as
│                              executed rather than as stored, because that is
│                              the gap match_observed exists to cross
├── finops-web/                IN BUILD  Vite, React and TypeScript
│   ├── README.md              why the versions are pinned where they are
│   ├── e2e/                   five Playwright journeys against the built
│   │                          bundle, not the test renderer. They are what
│   │                          proves the honesty rules survive the build
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
│       └── screens/           ten built. Three of the four P2 screens read live
│                              routes since TASK-P2-021; enforcement stays
│                              fixture backed and says so, because TASK-P2-016 is
│                              parked
│           ├── querySeverity.ts       the word to the ramp. Its own module
│           │                          because two screens rank the same findings
│           │                          and a second copy is a second answer
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
│       ├── retention.py       six jobs. Anonymises, never removes a principal row
│       └── partitions.py      months created ahead. Without one, cost rows are refused
│   └── metrics.py             only SLO 1 needs a custom metric. The other three are AWS's
├── finops_api/                IN BUILD  FastAPI, scope enforcement, routes
│   ├── flags.py               flag resolution, tenant then environment then declared
│   ├── main.py                app factory. Refuses to start on a bare route
│   ├── deps.py                the first scope point. Scope comes from the resolver
│   ├── middleware.py          request id on every line and back on the response
│   ├── schemas.py             the meta envelope. degraded is computed, never set
│   ├── routes/                the seven P0 routes, all returning the envelope
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
│       └── 0003_p2_tables.py  the six P2 tables. Three of its constraints are
│                              the feature: a deny cannot be written without an
│                              expiry, a modelled row cannot claim a measured
│                              count, and a change cannot exist without its undo
├── finops_query/              IN BUILD  P2, query cost governance
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
└── infra/terraform/           IN BUILD  three root modules, none applied yet
    ├── management/            one read only role in the management account
    ├── member/                a service managed StackSet, so new accounts self onboard
    └── hub/                   the VPC with no NAT, Aurora, SQS, ECR, ECS, ALB, alarms
```

## Planned module responsibilities

| Module | Responsibility | Depends on | Must not depend on |
| --- | --- | --- | --- |
| `finops_core` | Domain entities, the nine ports, the typed error taxonomy | nothing | boto3, botocore, fastapi, sqlalchemy, requests |
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
| What is done and what is left | `tasks/STATUS.md` |
| What is broken, what is risky, what is undecided | `tasks/ISSUES.md` |
| Where did the last session stop | `docs/checkpoint.md` |
| What rules must a change follow | `CLAUDE.md` |
| Where is a specific function | `context_index.md` |

## Source material outside the repository

| Item | Location | Relevance |
| --- | --- | --- |
| Grafana query cost audit prototype | `publicsampledashboard.zip`, containing `sample_lambda.py` and `sample_report.html` | The starting point for sub project P2. Assessed in `tasks/ISSUES.md`, ISS-020 to ISS-027 |
