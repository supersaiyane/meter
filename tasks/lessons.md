# Lessons

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
