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
