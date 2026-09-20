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
