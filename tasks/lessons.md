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

**Recurred 2026-09-27, third time.** `make check-memory` exited 2 and the commit ran anyway, because both were in one Bash call joined by newlines: the call's exit code is the last command's, and the last command was the commit. The rule below already says this and I wrote it. What failed was applying it while doing something else, which is when it matters.

**Sharpened rule.** A Bash call that contains `git commit` contains nothing else except `git add` and `git log`. Not a checker, not a test, not a `make` target, not an `echo` of an exit code. If a check has to run first, it runs in its own call and I read its output before the next call is written. There is no version of this where the two are one command and the exit code is still trustworthy.

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

## 2026-09-26: a passing vitest run over code that does not typecheck

**Mistake:** committed FEAT-052 after running `pytest` on the changed backend tests
and `vitest` on the new component test, both green. The commit contained two real
TypeScript errors. `rows()[0]` is `ApiRecommendation | undefined` under
`noUncheckedIndexedAccess`, so spreading it produced an object whose every field was
optional, which is not the type the component takes. The build was broken for the
next two commits and I only found it because the next feature ran `tsc` for its own
reasons.

Vitest transpiles with esbuild and does not typecheck. A green vitest run over a
file with a type error is the expected outcome, not a surprising one, so the test
result carried no information about the thing that was wrong.

**Correction:** self caught, by running `npx tsc --build` while adding a type to
`api/types.ts` and seeing two errors in a file I had already called done.

**Rule:** a change that touches any `.ts` or `.tsx` file is not verified until
`cd finops-web && npx tsc --build` has been run and has printed nothing. Run it
before the commit, in its own Bash call, and read the output rather than the exit
code, because `tsc --build` prints errors and can still be followed by a command
that succeeds. `vitest` passing is not a substitute and never was. The full gate is
`make verify`, and for anything larger than one file that is the thing to run rather
than a subset chosen by which files I remember touching.

**Triggers:** any edit to `.ts` or `.tsx`, any use of `vitest run` as the evidence
for a frontend change, indexing an array whose element type is then spread, and any
commit whose verification was a set of targeted test commands rather than
`make verify`.

## 2026-09-26: a collector wired into the seed that produced nothing

**Mistake:** built FEAT-054's parking collector, wired it into `scripts/demo/seed_demo.py`,
and ran the seed tests. All eighteen passed. The collector had produced zero findings,
for two independent reasons, and nothing anywhere failed.

The filter selected `DEMO_ACCOUNT`, which holds no EC2 candidates at all, so the
collector was handed an empty list and an `if parkable:` guard skipped it in silence.
Underneath that, the fold's evidence rule was wrong: it required every hour to be
present in every week the data touched, and a window of now minus a fortnight starts
and ends mid week, so it straddles three Monday aligned weeks whose ragged ends share
no hour. Nothing was ever quiet. Both bugs produced the same symptom, which is no
symptom.

The unit tests passed throughout, because they generated an aligned fortnight from a
Monday. The aligned fixture was the thing hiding the bug, and it was the fixture I
wrote to make the fold easy to reason about.

**Correction:** self caught, by writing an assertion that the seeded estate holds at
least one row of the new kind and watching it fail.

**Rule:** a new collector is not done until a test asserts the seeded estate contains
at least one row it produced. Write that assertion before wiring the collector up, and
watch it fail for the right reason. A count of rows written is not enough, because a
collector handed an empty candidate list writes zero and returns successfully.

Second rule, for any code that buckets a time series by position in a week or a month:
at least one test window must start and end off the boundary. An aligned fixture makes
the arithmetic easy to read and cannot see the class of bug that only appears when the
window is ragged, which is every real window.

**Triggers:** adding a collector, adding a branch to `seed_demo.py`, any `if rows:` or
`if candidates:` guard around a write, folding a series by hour of week or day of month,
and any fixture whose start time was chosen because it is a Monday or the first of a
month.

## 2026-09-27: a count in the map, stale for the third sweep running

**Mistake:** three sweeps of `project_map.md` in two days, and every one of them found
counts that had drifted. On 2026-09-26 the suite count was two sub projects behind and
the routes block did not mention a module. Later the same day the journey count was nine
behind, written when there was one spec file. On 2026-09-27 the journey count, the screens
count, the route count and the migrations list were all wrong again, and the migrations
list was the worst of the four: a list of revisions that silently stops being a list of
revisions is how a reader concludes the schema has not changed.

The lesson of 2026-08-23 already says to commit documentation with the change that made
it stale, and I have broken it three times. So the rule is wrong rather than
under-applied: it asks me to remember, at the end of a task, which prose numbers a change
moved. Nothing surfaces them, nothing fails, and the map is the one file nobody reads
until they need it.

**Correction:** self caught each time, by sweeping the map on the owner's instruction
rather than by anything in the build.

**Rule:** a number in `project_map.md` is written in one of two forms and never a third.
Either it names where it comes from, as two lines already do ("counted from the `arrives`
field in sections.ts", "read from what `make verify` runs"), or it is not written at all
and the prose describes the thing without counting it. When adding a line with a number,
write the derivation beside it in the same sentence, because that sentence is what makes
the next reader check rather than trust.

This is now enforced rather than remembered. `scripts/docs/check_map_counts.py` derives
every count into a generated block and runs in `check-docs`, so a stale figure fails the
build. It also checks that every revision file is named somewhere in the map, which is a
separate claim from the count: on its first run it found seven revisions the map had never
named, five of them from months earlier, and a count alone would have passed all seven.

**Triggers:** any edit to `project_map.md`, any task that adds a screen, a route, a
journey, a migration or a collector, the instruction "do the projectmap", and any
sentence in a document containing a numeral that was not computed in front of me.

## 2026-09-27: a derived count written from memory
**Mistake:** Wrote "chart coverage is 10 of 25 screens" in a checkpoint row, having
counted earlier in the session and then reasoned forward about it. It was 11. Then,
in the row that recorded fixing that, wrote 13 for the same figure. It was 12. Twice
in one session, the second time inside the correction itself.
**Correction:** Found by running the count rather than by being told, which is the
only reason it was found at all. A wrong number in a checkpoint is exactly the
failure the project's writing rules exist to prevent, and nothing in the toolchain
checks prose figures.
**Rule:** A number that is derived from the repository is computed in the same
command that writes it down. Never state a count in a document from memory, from
arithmetic on an earlier count, or from a number seen earlier in the session. If
the figure cannot be computed in the command that writes it, it does not go in the
document.
**Triggers:** Writing a checkpoint row, a status paragraph, a feature document or a
commit message that contains a count of files, screens, tests, tasks or issues.
Phrases like "N of M", "up from", "now at".

**Related:** the 2026-09-27 lesson above, about counts in `project_map.md` going
stale for three sweeps running, is the same failure in a place where it could be
automated, and `scripts/docs/check_map_counts.py` now covers those seven figures.
This one is the version that cannot be: a count in a sentence in a checkpoint row
has no schema, so the only defence is computing it in the command that writes it.
That is why the rule above is about the command and not about being careful.

## 2026-09-27: a route tested on its data and never on its envelope

**Mistake:** The FEAT-061 geography route returned counts and no timestamps. Eleven
tests passed, including one asserting the parts add up to the whole estate and one
asserting a narrowed reader sees less. Every one of them read `body["data"]`. None
read `body["meta"]`. `build_meta` derives freshness from the rows it is handed, a
grouped row is not a fact row, so `as_of` came back null, and the screen reads
exactly that field to decide whether anything has been collected. A correct estate
of ninety two resources rendered as "not yet collected by topology".

**Correction:** Found by opening the screen, not by the suite. The docstring on
`build_meta` already says a route whose rows are not facts passes its timestamps
explicitly, so the warning existed and the tests did not enforce it.

**Rule:** A route test asserts on the envelope as well as on the payload. At minimum
one case per route asserts `meta["as_of"]` is not null when the route returned rows,
and asserts the coverage unit. A grouped or derived read aggregates `min(as_of)` and
`min(collected_at)` into columns of those names, so the envelope picks them up the
way it does for any fact.

**Triggers:** Adding a route. Writing a repository method with `group_by`,
`with_only_columns` or any aggregate. Any read whose rows are not whole table rows.
Seeing `build_meta(..., rows=rows)` where `rows` came from an aggregate.

## 2026-09-27: a design argument that was right about the risk and wrong about where it lived

**Mistake:** Built the geographic map as a graticule with no coastline, reasoning that
drawing land would imply a precision the region name prefix does not have. The owner
sent back a screenshot: an empty grid with two dots on it, and "this should be on
world map ... it should look good".

**Correction:** The argument was about the right risk and the wrong element. A
coastline says "this is the world". It is the marker's *position* that would claim a
datacentre, and the caption already said a marker is a continent and not a
datacentre. Removing the land did not reduce a false claim, it removed the reference
that made the remaining marks mean anything, so a reader could not tell which dot was
North America without reading the label.

**Rule:** When an honesty argument says to remove something from a drawing, name the
specific element that would carry the false claim and remove only that. If the thing
being removed is context rather than the claim, the drawing loses information and
gains no honesty. A backdrop is not a claim.

**Triggers:** Deciding to leave something out of a visualisation "because it would
imply" something. Any sentence of the form "drawing X would suggest Y" where X is a
reference frame, an axis, a label or a background rather than the data mark itself.

## 2026-09-28: the resume vector proposed work that was already finished

**Mistake:** The "Next action" section of `docs/checkpoint.md` went stale twice in two
days, the same way both times. It named issues as the next thing to do, the work was
done that afternoon, and the section was not rewritten. On 2026-09-27 it proposed
ISS-213 and ISS-214 after both had been closed. On 2026-09-28 it proposed the four
unproven adapters after they had been taken as far as an offline check can go.

**Correction:** Noticed only because the owner asked for the checkpoint twice and I
read the section both times. Nothing in `make verify` looked at it, and it is the one
part of the file a cold session reads first, so a wrong candidate list sends a fresh
start at a task that finished.

**Rule:** Rewrite the "Next action" section on every pass over the checkpoint, not
only when it is obviously old. It is the output of the file, not a record in it, and
a row being added is exactly when the section it summarises becomes wrong.
`scripts/ci/check_memory.py` now refuses a numbered candidate naming an issue the
registry says is FIXED, so the specific failure cannot recur silently, but the check
covers only issues: a candidate phrased as prose is still mine to keep honest.

**Triggers:** Adding a row to `docs/checkpoint.md`. Closing an issue. Being asked to
"do the checkpoint". Any moment the phrase "nothing is in flight" is about to be
written.

## 2026-09-28: reversing a falsification with git checkout destroys uncommitted work

**Mistake:** Twice in one session I broke something deliberately to prove a check could
fail, then reversed the break with `git checkout -- <file>`. Both files had uncommitted
work in them, so the checkout took the falsification and the work together. The first
time it silently removed the three `SCOPED_TABLES` entries I had just written, and the
tests went green again for the wrong reason: the guard entries were gone, so the tests
asserting them were gone too. The second time it removed seven blocks of hand written
prose from `project_map.md`, which had to be reconstructed from scratch. The second
happened after I had already decided to write this lesson and before I had written it.

**Correction:** Nobody corrected me. Both times I noticed because the next command
disagreed with what I believed the file said, which is luck rather than method.

**Rule:** Reverse a falsification by inverting the same edit that made it, in the same
command, never with `git checkout` or `git restore`. Those commands discard everything
uncommitted in the file and a falsification is by definition performed on a file being
worked on. Where the falsification is a one line substitution, do the reverse
substitution and assert the replaced text was present, so a failed reversal is loud. If
the change is too large to invert, commit the work first and then falsify, in that order.

**Triggers:** About to run `git checkout --`, `git restore` or `git stash` on a file
edited in this session. The phrase "let me put that back". Any falsification of a check
whose subject is a file also carrying new work.

## 2026-09-28: a falsification the same length as the original can appear not to revert

**Mistake:** Falsified a botocore shape check by replacing `ServiceName` with
`ServiceTier`, ran it, watched it fail correctly, restored the file, and the test kept
failing with the old message. Read the file three separate ways and it was correct.
Imported the module and printed the value and it was correct. Spent several minutes
concluding the test framework was caching results, then that a proxy was replaying
output, both wrong. The real cause is that pytest's assertion rewriting caches compiled
bytecode keyed on the file's size and modification time, the two strings are both eleven
characters, and the restore produced a byte identical size. The stale `.pyc` was trusted.

**Correction:** Nobody corrected me.

**Rule:** When a check keeps reporting a value the source does not contain, delete the
`__pycache__` entry for that test module before doubting anything else. And prefer a
falsification that changes the file's length, which makes the cache key move: deleting a
line or adding a word is as good a break as swapping one identifier for another of the
same width, and it cannot produce this failure.

**Triggers:** A test failing with a message that names a value `grep` cannot find in the
file. Any reversal of a falsification that appears not to have taken.

## 2026-09-28: a test helper that fills in a default makes the default's own test unable to fail

**Mistake:** Wrote a `quota()` helper for the entity tests that substituted a valid reason
whenever a caller passed none and the usage source was NONE. Convenient for the fifteen
tests that were about something else, and fatal for the one test that mattered: the case
asserting an unmeasurable quota without a reason is refused could not fail, because the
helper supplied the reason the test was trying to omit. It reported success against a
constructor that would have accepted the bad value.

**Correction:** Nobody corrected me. The test passed, which is how I found it: it passed
before the rule it tested had been written.

**Rule:** A test helper may default a field, but it must distinguish "not passed" from
"passed as absent". Use a sentinel rather than None as the default, so an explicit None
reaches the code under test. Before trusting any test that asserts an absence is refused,
check that the absence actually reaches the constructor.

**Triggers:** Writing a factory or builder for tests. A test asserting that something
cannot be constructed. Any helper with a line of the form "if x is None: x = something".

## 2026-09-28: a name is evidence only where it is claimed

**Mistake:** On 2026-09-27 I added a check that every collector is named in
`project_map.md`, after finding seven described nowhere. The check searched the whole map
for the filename. On 2026-09-28 P5 added `finops_ingest/collectors/quotas.py` and the
check passed while the collector was described nowhere, because two other files in the
project are also called `quotas.py`: the port and the fake estate. Scoping the search to
the collectors block then immediately found a second one, `recommendations.py`, which the
2026-09-27 sweep had specifically set out to fix and had not: its whole file match was
satisfied by the adapter and the fake of the same name.

**Correction:** Nobody corrected me. It surfaced because I checked by hand whether my own
collector was listed, having no reason to expect it was missing.

**Rule:** When a check asks whether a thing is documented, scope the search to the place
the documentation is claimed to be, not to the whole document. A filename found anywhere
in a file proves only that some file of that name is mentioned. Falsify the scoped version
by naming the thing only outside its section and watching the check still fail.

**Triggers:** Writing a check that a name appears in a document. Any use of `name in text`
where `text` is a whole file. Adding a module whose basename already exists elsewhere in
the project.
