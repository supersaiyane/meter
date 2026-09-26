# Lessons

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: Corrections received, converted into rules. This is the compounding
     half of the project: a mistake recorded once is a mistake not repeated.
     Grade B here: copy it, then replace the lessons themselves. The four field format and the
     rule rather than a feeling constraint carry over.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

Corrections received, converted into rules so they are not repeated.
A lesson must be a rule that can be followed, not a feeling.

Update trigger: every time a correction is received.

---

## 2026-08-23: no em dashes

**Mistake:** Used em dashes throughout the requirement review and design
discussion.

**Correction:** "need this as a proper project no emdash any where".

**Rule:** Never use an em dash or an en dash in any output: code, comments,
documentation, commit messages, user interface copy, or chat responses.
Use a comma, a colon, parentheses, or restructure the sentence. Before
finishing any task that writes files, run the em dash grep from `CLAUDE.md`
and paste the result.

**Triggers:** writing any file, writing any commit message, writing any
response.

---

## 2026-08-23: documentation is a deliverable, not an afterthought

**Mistake:** Treated design output as chat responses and specification files,
without a goal document, a status tracker, an issue register, a checkpoint
log, or a project map.

**Correction:** "Also create proper documentation, What is the goal, What we
have done, what is remaining, What issues we got, have we fixed then,
checkpoints, Complete project map and update them on regular interval, create
proper git commits, need this as a proper project".

**Rule:** At the start of any project, create the documentation spine before
writing code: goal, roadmap, architecture, decision records, status, issues,
checkpoint, project map, context index. Update them on the triggers listed in
`CLAUDE.md` and commit them with the change that made them stale, never as a
separate cleanup pass later.

**Triggers:** new project, first commit, end of any work session, any change
that adds or moves a module.

## 2026-09-06: scope of a user interface request
**Mistake:** Asked which progress the user wanted to see, framing every option
inside P2, when the request was for the whole product's interface.
**Correction:** "UI, i needed is for complete product, we have not planned it
yet, what to show where to show, what would be the design for the dashboard."
**Rule:** When a request names a surface rather than a task, establish the
scope boundary before offering options: is this the current sub project, or the
product. Ask which, do not infer it from the sub project in flight.
**Triggers:** "plan the UI", "design the dashboard", "what should we show",
any request naming a surface with no task identifier attached.

## 2026-08-29: a route that has never been called is not evidence

**Mistake:** Shipped three API routes with a full unit suite, a clean lint, a
clean type check and a clean build, and every one of them returned 500 on the
first real call. The six tables they read were never registered in
`SCOPED_TABLES`, and `UUID` was never imported into the module that declares
their response models. Then three more defects, each of which alone stopped the
local stack from showing any data at all, none of which any test could see.

**Correction:** None was needed from the user. The defects were found by
calling the routes with curl and by opening the screen, after the suite was
already green. This is the fifth time in this project that a green signal was
hollow: axe reported contrast "incomplete" while never reading a colour,
pip-audit aborted before writing the report that summaries read as zero
findings, a skipped test read as a pass, and a wheel shipped without its
subpackages while every local test passed.

**Rule:** Before marking a task done that adds or changes an HTTP route, a
container, or anything a person reaches through a browser, run it and reach it
the way a person would. For a route that means an actual request against the
running stack and reading the body. For a screen it means opening the screen.
Paste what came back. A passing suite is evidence that the code does what the
test says, and says nothing about whether the thing is reachable, wired, or
configured.

**Triggers:** a new route or endpoint, a change to `SCOPED_TABLES` or any
registry a route depends on, a new response model, anything touching
`docker-compose.yml`, a Dockerfile, or nginx, "the tests pass so it works",
"imports cleanly", marking a task done, and **changing the signature of anything
called during application assembly**: on 2026-09-05 turning `get_settings` into
a request dependency left 750 tests green and the container unable to boot,
because every test passes settings explicitly and only the image calls the
factory.

## 2026-09-06 - an exit code from the wrong end of a pipe

**Mistake:** told the user "image build done" and "the rebuilt image carries the
change". Neither was true. `docker compose build api 2>&1 | tail -3` reports
`tail`'s exit code, not the build's, and the build wrote nothing to the log, so
a run that produced no image looked identical to a successful one. Then
`docker compose restart api` was used to pick the new image up, which restarts
the container that already exists and never touches the image at all. The
demo the user was shown came from the host venv while the containers ran three
hour old code, and the difference only surfaced because the ad hoc screen
returned 14 rows where the database held 2.

**Correction:** self caught, by seeding through the documented path and reading
a number that disagreed with the one from the host.

**Rule:** never read success from a pipeline's exit code. Run the build
unpiped, or capture with `nohup cmd > log 2>&1` and read the log. Then prove
the artifact rather than the command: `docker images` for the timestamp, and a
`docker compose run --rm --no-deps <svc> python -c "import ...; print(...)"`
that asks the image for the symbol that was just added. To make a running
container use a new image, `docker compose up -d --force-recreate <svc>`.
`restart` is not a deployment.

**Triggers:** any `docker compose build`, any `| tail`, `| head` or `| grep` on
a command whose success matters, "the build finished", "the image is rebuilt",
restarting a service after a code change, and any claim about what a container
is running that was not read out of that container.

## 2026-09-20: a test that names its subject instead of deriving it

**Mistake:** three tests asserted that an unbuilt screen names the sub project
that will bring it, and each did so by naming one path. `/cost` shipped, so I
repointed all three at `/cost/anomalies`. That shipped too, and the same three
went red again. Twice I read the failure, saw a path that was now built, and
repointed it at the next path on the roadmap, which set the same trap one task
further out. The assertions were about a mechanism and were written as facts
about a particular screen, so every one of their failures looked like a
regression in work that was actually correct.

**Correction:** self caught on the second repeat, when the fix I was about to
apply was identical to the fix I had applied the day before.

**Rule:** when a test's subject is a mechanism that applies to a category
("an unbuilt screen", "a fixture backed surface", "a partial scope"), derive the
member from the source of truth at run time and assert the property over it.
`allScreens().filter((s) => s.arrives !== null)` and
`page.locator('a[data-arrives]').first()` cannot go stale, because the thing
that changes when a screen ships is the same thing the test reads. Naming a
member is only correct when the test is about that member. And the second time a
fix is byte for byte the fix from last time, the test is wrong, not the code.

**Triggers:** a test failing because the thing it pointed at now works, any
assertion containing a literal route, id or fixture name where the test title
says "a" or "an" rather than that name, and writing the same repair to a test
twice.

## 2026-09-20: a type check that checked nothing

**Mistake:** I used `npx tsc --noEmit` in `finops-web` a dozen times across a
session as my proof that a change type checked, and it exits 0 without reading a
single file. The root `tsconfig.json` is `{"files": [], "references": [...]}`, and
project references are only followed by `tsc --build`. Plain `--noEmit` against a
solution file has no input, finds no errors and reports success. When I finally
ran `tsc -p tsconfig.app.json` for an unrelated reason, three type errors were
sitting there, one of them in a file I had edited two commits earlier.

**Correction:** self caught, and only because a stub client was obviously missing
a method the interface now required, which made a clean type check impossible to
believe.

**Rule:** in `finops-web`, type check with `npx tsc --build` (or `npm run build`,
which runs `tsc --build && vite build`). Never `tsc --noEmit` there. More
generally: before trusting any checker's silence, make it fail once. A checker
that reports success over zero inputs is indistinguishable from a checker that
reports success over correct inputs, and the first one is what a solution style
tsconfig, an empty glob or a wrong path gives you. `make verify` was never fooled,
because `build-web` runs `tsc --build`; only my ad hoc command was.

**Triggers:** `tsc --noEmit`, any checker invoked with a config I did not read,
"types are clean", a lint or type run that finishes suspiciously fast, and any
tsconfig containing `"files": []`.

## 2026-09-20: a row count in the accounts slot, three times

**Mistake:** `build_meta(visible=...)` feeds a coverage banner that counts
accounts, and I have now passed something else into it three times. A line item
count rendered "showing all 450 accounts" on an estate with five. A count of
anomalies rendered "4 missing, outside your scope" to a reader entitled to
everything. A count of commitments rendered "4 of 5 accounts" above four
commitments. Every one of them passed every test, because no test asserted on the
banner, and every one was found by opening the screen.

**Correction:** self caught each time, by looking at the rendered page rather than
at the payload.

**Rule:** `visible` is a count of the thing `coverage_unit` names, and nothing
else. When a route's rows are not accounts, either pass the account count the
repository can produce, or pass `coverage=(n, m)` with a `coverage_unit` that
names what was actually counted. Then assert it: a test that reads
`meta.scope_coverage` and checks the unit and the figure, comparing against
another route rather than against a number written down. A banner with no test is
a sentence the product says to every reader that nobody has ever read.

**Triggers:** any `build_meta` call, `visible=len(`, adding a route whose rows are
not accounts, and any screen that renders a count next to a noun.

## 2026-09-21: a checker whose exit code the shell threw away

**Mistake:** I ran `mypy ... | tail -1 && git commit`, saw "Found 1 error in 1
file" scroll past, and committed anyway. The `&&` was testing `tail`, which
succeeds whatever it is fed. The error sat in a commit until I happened to re run
the check a minute later. This is the same family as the `tsc --noEmit` lesson
from 2026-09-20, arriving through a different door: there the checker examined
nothing, here the checker worked and the shell discarded its verdict.

**Correction:** self caught, one command later.

**Rule:** a checker and a commit never appear in the same Bash call. The check runs
alone, redirected to a file, with `echo "exit: $?"` on the next line, and I read
that number. The commit is a separate call made after reading it.

Rewritten 2026-09-26, after it happened a second time. The first version said
"never put a checker in a pipeline whose exit code decides anything", which is a
thing to remember at the moment I am typing the pipeline, and that is the moment I
am thinking about something else.

That removes the judgement. There is nothing to notice, because there is no
pipeline and no `&&` for a pipe to sit in front of.

`make verify` was always immune, because each step is its own recipe line. Only ad
hoc chains are exposed, and the second occurrence was `pytest ... | tail -6` with
`git add && git commit` after it, which committed three failing tests.

**Triggers:** any `| tail`, `| head` or `| grep` on mypy, ruff, pytest or tsc;
any `&& git commit` or `&& git add`; a Bash call that both checks and commits; and
the words "it passed" about output I filtered rather than read.

## 2026-09-21: a registry entry that landed in the wrong list

**Mistake:** twice now I have added an entry to `docs/registry.yaml` by finding
the `issues:` key and inserting **before** it, which puts the entry at the end of
the `changes:` list rather than the start of `issues:`. Both lists are sequences
of id first mappings, so YAML parses it happily and only `make doc-sync` notices,
with a `KeyError: 'date'` from a change row that has no date.

**Correction:** self caught both times, by doc-sync, within a minute.

**Rule:** when adding to a YAML list that is followed immediately by another list,
insert **after** the key line rather than before the next one, and verify with a
parse before running anything else:
`python3 -c "import yaml; r=yaml.safe_load(open('docs/registry.yaml')); print(len(r['changes']), len(r['issues']))"`.
The counts moving by one in the list you meant is the check.

**Triggers:** any edit to `docs/registry.yaml`, any insert positioned relative to
a following key rather than a preceding one, and `KeyError` from a generator over
a list that parsed cleanly.

**Amended 2026-09-22, same file and a different way to break it.** Three times in
one day I wrote a colon followed by a space inside an unquoted `summary:` and the
file stopped parsing, because in a plain YAML scalar `": "` is a mapping
indicator. Each time the fix was to rewrite the sentence and each time I had
already written the whole entry.

**Amended again 2026-09-24, fourth occurrence, one day after writing the rule
down.** Writing "no colon in a summary" did not work, because I write the entry
first and proofread it against a rule I have already stopped thinking about. Per
CLAUDE.md section 4, a lesson that fails three times is the wrong rule.

**Rule, mechanical this time.** Do not hand write the YAML. Build the entry as a
Python dict and let the library do the quoting, then insert the dumped block:

```python
import yaml
block = yaml.dump([{"id": "ISS-nnn", "severity": "LOW", "summary": text,
                    "status": "OPEN", "detail": where}],
                  sort_keys=False, width=96, allow_unicode=True)
```

`yaml.dump` quotes whatever needs quoting, so a colon, a hash, a leading dash and
a trailing space all stop being my problem. Prose rules about punctuation rely on
memory at exactly the moment memory is busy writing the prose.

## 2026-09-21: a local database four revisions behind a passing test suite

**Mistake:** I ran `make migrate`, saw it exit zero, and believed the local
database was at head. It was at `0009` while the repository was at `0013`. The
compose `api` image bakes the source in at build time, so the container that ran
`alembic upgrade head` held a snapshot of the tree from the last `make up`, and it
had nothing newer to apply. It printed no output at all, which I read as quiet
success rather than as a command that did nothing. Then `make seed` ran the same
stale image and reported seeding an estate, so two green signals in a row said the
opposite of the truth.

Every test passed throughout, because the integration suite migrates its own
throwaway database from the working tree. The gap was only ever in the database a
person looks at.

**Correction:** self caught, by querying `realized_saving` and being told the
relation does not exist after a seed that claimed to have written 2292 rows.

**Rule:** after `make migrate`, assert the head rather than the exit code:
`docker compose exec -T postgres psql -U meter -d meter -t -c "SELECT version_num FROM alembic_version"`
and compare it to the newest file in `migrations/versions/`. If they differ, run
`make up` first, because the image and not the database is what is stale. The same
applies to any compose `run` of a script I have just edited: a passing test suite
says nothing about the image, because the suite never uses it.

**Triggers:** `make migrate`, `make seed`, any `docker compose run` after editing
Python, a command inside compose that produces no output, and any "relation does
not exist" for a table whose migration is committed.
