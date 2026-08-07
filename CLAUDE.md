# Meter: project rules

These rules are binding for every contributor, human or agent. They sit on
top of the global rules and override them where they conflict.

## Writing rules

1. **No em dashes anywhere.** Not in code, comments, documentation, commit
   messages, UI copy, or generated output. Use a comma, a colon, parentheses,
   or restructure the sentence. En dashes are also banned. The only acceptable
   dash is a hyphen inside a compound word or a list bullet.
2. Plain English. No filler, no marketing voice, no hedging.
3. Every number in a document states whether it is measured or modelled.
4. Absolute dates only. Write `2026-08-23`, never `tomorrow` or `last week`.

A pre commit hook enforces rule 1 once tooling lands. Until then, run:

```bash
grep -rn $'—\|–' --include='*.md' --include='*.py' --include='*.ts' --include='*.tsx' . && echo "EM DASH FOUND" || echo "clean"
```

## Documentation maintenance

Documentation is not optional output produced at the end. It is updated as
part of the same change that makes it stale.

| Document | Update trigger | Owner |
| --- | --- | --- |
| `tasks/STATUS.md` | End of every work session | Whoever did the work |
| `tasks/ISSUES.md` | The moment an issue or open question is found or closed | Finder |
| `docs/checkpoint.md` | End of every completed task | Whoever did the work |
| `project_map.md` | Any new module, moved module, or changed responsibility | Author of the change |
| `context_index.md` | Any new or removed public function or class | Author of the change |
| `docs/01-ROADMAP.md` | Sub project status change | Whoever changed the status |
| `docs/adr/` | Any decision that is expensive to reverse | Decision maker |
| `tasks/lessons.md` | Every time a correction is received | Recipient of the correction |

Batch these updates into one commit at the end of a task. Do not write one
commit per document.

## Definition of done

A change is done when all of the following are true.

- Tests exist and pass, and coverage for the changed area is at or above 80 percent.
- Errors are typed and surfaced, never swallowed and never collapsed into zero.
- No secrets, no hardcoded account identifiers, no hardcoded region strings.
- `tasks/STATUS.md` and `docs/checkpoint.md` reflect the change.
- Commit message follows the format below.
- A staff engineer would approve it in review.

Reading your own code back is not evidence. Running the test and pasting the
output is evidence.

## Architectural constraints

These are not style preferences. Breaking them costs a rewrite.

1. **`finops-core` never imports boto3.** No cloud SDK, no framework, no
   HTTP client. Domain and ports only. This is what makes GCP and Azure a
   connector instead of a rewrite.
2. **The canonical cost schema is FOCUS 1.1.** Do not invent a cost schema.
   Normalize at ingest.
3. **Scope is enforced in two places**, a request dependency and a repository
   guard. A route that forgets the dependency must still not be able to read
   out of scope data.
4. **Every fact carries `as_of`.** Every screen shows freshness.
5. **Partial failure is first class.** One account failing never fails a run.
   Error causes are typed: AccessDenied, Throttled, NotOptedIn, NoData. Never
   collapse them, and never render a failure as the number zero.
6. **Read only in v1.** No write API call into a member account. Remediation
   is delivered as a generated infrastructure as code pull request.
7. **The platform meters itself.** Every platform resource is tagged
   `finops:module`, and the platform's own cost is on the front page.

## Commit format

```
<type>: <description>

<body explaining why, not what>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

One logical change per commit. No em dashes in the message. No attribution
trailer.

## Repository layout

```
finops-core/        domain entities and ports, no cloud SDK
finops-providers/   aws/ adapter, gcp/ and azure/ reserved
finops-ingest/      dispatcher, workers, run ledger, watermarks
finops-api/         FastAPI application and scope enforcement
finops-web/         React and TypeScript frontend
infra/terraform/    hub stack, member StackSet, org reader role
docs/               goal, roadmap, architecture, ADRs, specs, plans
project_map.md      module level map, kept current
docs/checkpoint.md  session continuity log with resume vectors
tasks/              status, issues, lessons
```
