# P7 Insight and LLM layer: implementation plan

Date: 2026-09-28
Status: Provisional, pending approval of `docs/specs/2026-09-28-p7-insight-and-llm-layer-design.md`
Spec: `docs/specs/2026-09-28-p7-insight-and-llm-layer-design.md`
Depends on: P0, P1, P2, P3 delivered. P4 for TASK-P7-008
Tasks: 14

The last sub project, and the first one that can make the other six untrustworthy. Every
screen built so far distinguishes measured from modelled, dates its figures and refuses
to render a failure as a zero. One assistant answering a question with a plausible number
undoes all of it, and nobody would notice until somebody acted on the number.

## How to work this plan

Same contract as P0 through P6. One task, one commit.

**Five rules specific to P7, and the first two are the sub project.**

1. **The model never emits a figure, it cites one.** Spec section 5.2. Prose carries
   placeholders and the interface substitutes cited values, so there is nowhere in a
   sentence for a hallucinated number to live. TASK-P7-002 builds the entity that makes an
   uncited figure unconstructable, and TASK-P7-006 builds the check that refuses one at
   the boundary. Neither is optional and neither is a later hardening pass.

2. **The tools are the MCP tools, which are the HTTP API.** Spec section 5.1, constraint
   8, ADR-0009. No task adds a data path, a query builder or a second scope check. A task
   that finds itself reading a repository directly has found a disagreement with the spec.

3. **A refusal is a first class answer with its own state.** Spec section 5.3. Answer,
   refusal and failure are three outcomes, held apart by a database constraint in
   TASK-P7-003 and by three different renderings in TASK-P7-010.

4. **The refusal set is written before the thing that must pass it.** TASK-P7-005 writes
   the three evaluation sets against the fake model, before TASK-P7-006 builds the
   orchestration they judge. A refusal set written afterwards is a description of what the
   implementation happens to do.

5. **Nothing writes to AWS.** Constraint 6. TASK-P7-014 asserts it by name, the way
   `tests/contract/test_no_quota_writes.py` does for the quota increase, and the same
   distinction applies: authoring a Terraform diff is not applying one.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The port and the shape of an answer | 001 to 004 | A model behind a port, an answer that cannot hold an uncited figure, and the schema | P0 delivered, ADR-0028 accepted |
| B. The judge, before the thing judged | 005 | Three evaluation sets over a deterministic fake | A |
| C. The loop | 006 to 007 | Question to tools to cited answer, and the budget that stops it | B |
| D. The three other roles | 008 to 009 | Narration, and remediation as a pull request | C, P4 delivered |
| E. Surface | 010 to 012 | The guard, the routes, the screens and the digests | C |
| F. The controls | 013 to 014 | Redaction, and the test that keeps the write out | E |

---

### TASK-P7-001: a port over a model, and nothing about a vendor

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 4, ADR-0028 |
| Delivers | Part of FEAT-038 |
| Depends on | ADR-0028 accepted |
| Estimate | M |

**Goal.** `finops_core/ports/llm.py`, the `LlmProvider` protocol over completion with
tool schemas, and `finops_fakes/llm.py`, deterministic.

**The objection, and what answers it.** A port over one adapter is speculative
generality, and this project says so about most abstractions. It earns its place for two
reasons that have nothing to do with hedging ADR-0028. The contract suite needs one
sentence to hold the real adapter and the fake to, which is how every other provider here
is tested. And the evaluation sets in TASK-P7-005 have to run with no model at all, on a
laptop, inside `make verify`, which makes the fake not a convenience but the only thing
those tests can talk to.

**Acceptance criteria.**

- [x] The protocol names completion, tool schemas and a token count, and nothing about
      Bedrock, a model identifier or a region
- [x] The fake is deterministic: the same question returns the same response, asserted by
      calling it twice
- [x] A provider refusal is one of the seven typed causes, and an unavailable model is
      `NotOptedIn` rather than `Unreachable`, because a deployment without Bedrock access
      has not failed, it has not been enabled
- [x] `finops_core` imports no SDK, constraint 1, held by the existing import contract

---

### TASK-P7-002: an answer that cannot hold a figure it did not cite

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 5.2 |
| Delivers | Part of FEAT-038 |
| Depends on | TASK-P7-001 |
| Estimate | M |

**Goal.** `finops_core/domain/insight.py`. `Answer`, `Citation`, `Refusal`.

**The objection, and what answers it.** Enforcing this in the entity looks like belt and
braces over a check the orchestration will do anyway. It is the opposite: the
orchestration check is the one a future route can bypass by building an `Answer` itself,
and constraint 11's reasoning applies to an entity exactly as it does to a table. If
application code is the only thing preventing a bad value, the bad value eventually
exists.

**Acceptance criteria.**

- [x] An `Answer` whose prose contains a digit outside a placeholder cannot be constructed
- [x] An `Answer` with a placeholder and no matching `Citation` cannot be constructed, and
      neither can one carrying a `Citation` no placeholder uses
- [x] Every `Citation` carries the tool, the field, the value, the `measured` or `modelled`
      flag and the `as_of`. One missing its provenance flag cannot be constructed
- [x] A `Refusal` carries a reason of at least `REASON_MIN_LENGTH`, reusing the constant
      rather than a second literal
- [x] `Answer` and `Refusal` are different types, not one type with a nullable field

---

### TASK-P7-003: three outcomes, held apart by the database

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 6.1, constraint 11 |
| Delivers | Part of FEAT-038 |
| Depends on | TASK-P7-002 |
| Estimate | M |

**Goal.** `migrations/versions/0023_assistant_exchange.py`.

**Acceptance criteria.**

- [x] `answer` present if and only if `outcome` is `ANSWERED`, `refusal_reason` if and
      only if `REFUSED`, `failure_cause` if and only if `FAILED`. All three watched
      refusing, in both directions
- [x] `failure_cause` constrained to the seven typed causes, mirrored from
      `finops_core.errors` the way `ERROR_TYPES` already is
- [x] `est_cost >= 0` and `answered_at >= asked_at`
- [x] `question` stored as typed, with no normalisation, because the wording is the
      evidence when an answer turns out wrong
- [x] Backward compatible, constraint 12

---

### TASK-P7-004: the adapter, and the permission it needs

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 10, ADR-0028 |
| Delivers | Part of FEAT-038 |
| Depends on | TASK-P7-001 |
| Estimate | M |

**Goal.** `finops_providers/aws/bedrock.py`, and the hub role's two Bedrock actions.

**Acceptance criteria.**

- [x] Never run against AWS, stated in the first line, ISS-002
- [x] Held to a contract suite alongside the fake
- [x] Every response field it reads exists in the botocore service model, added to
      `tests/providers/aws/test_response_shapes.py` **before** the adapter is written.
      That order caught the request status defect in P5 and is the only reason it was
      caught before a real account rather than by a customer
- [x] The hub role grants `bedrock:InvokeModel` and
      `bedrock:InvokeModelWithResponseStream` scoped to named model identifiers, never a
      wildcard, asserted against the Terraform
- [x] No member account role gains anything, asserted

---

### TASK-P7-005: the three sets, written before the thing they judge

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 11 |
| Delivers | Nothing visible. It is what makes the rest checkable |
| Depends on | TASK-P7-004 |
| Estimate | L |

**Goal.** `tests/query/insight/`, holding the answer set, the refusal set and the
injection set, over the fake model and the fake estate.

**The objection, and what answers it.** Writing tests before the orchestration means
writing them against an interface that does not exist, and they will need editing when it
does. That is the cost and it is worth paying once: a refusal set written after the
orchestration is a description of what the implementation happens to do, and the whole
value of this set is that it was decided before anybody was invested in passing it. The
pressure on every assistant is to answer more, and each individual softening looks
reasonable.

**Acceptance criteria.**

- [x] The answer set asserts each figure equals what `finops_query` computes for the same
      question. Never that the prose is right, which is not testable
- [x] The refusal set covers at least a cluster with no split cost allocation data, an
      account outside the asker's scope, a question needing a tool that does not exist,
      and a request for next month's cost
- [x] The injection set covers at least a prompt trying to reach another account's data,
      one trying to make the model emit a bare numeral, and one trying to make it repeat a
      secret from the question
- [x] Every set asserts the reason, not only the outcome. A refusal for the wrong reason
      is a wrong answer
- [x] The sets run inside `make verify` with no model and no network

---

### TASK-P7-006: question, tools, cited answer

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec sections 5.1, 5.2 and 7, FEAT-038 |
| Delivers | FEAT-038 |
| Depends on | TASK-P7-005 |
| Estimate | L |

**Goal.** `finops_query/insight.py`. The loop, and the provenance check.

**Acceptance criteria.**

- [x] Tool calls go through `finops_mcp` with the caller's token, never to a repository
      directly. A test asserts this module imports nothing from `finops_api.db`
- [x] An answer whose prose contains a numeral the check did not place is `FAILED` with a
      typed cause, neither stripped nor passed through
- [x] A question with no tool to answer it is `REFUSED`, naming the missing tool
- [x] The three sets from TASK-P7-005 pass, unedited except for the interface they call
- [x] Every exchange records its tool calls in order, so an answer can be replayed

**As built, 2026-10-04.** The first criterion is met in substance and not in its
letter. Tool calls go through the API's routes with the caller's token, from the one tool
table the MCP server also reads, rather than through `finops_mcp` itself. The layer
contract forbids `finops_api` from importing `finops_mcp`, and the facade contract forbids
`finops_mcp` from importing the Bedrock adapter, so no package could have composed both.
The table moved to `finops_api/tools.py`, which describes the API's own routes, and the
MCP server imports it from there and stays a facade over the network. `finops_query/insight.py`
imports nothing from `finops_api`, asserted by name.

---

### TASK-P7-007: the budget that stops it

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 10 |
| Delivers | Part of FEAT-038 |
| Depends on | TASK-P7-006 |
| Estimate | S |

**Goal.** A per tenant monthly token budget in settings, and the refusal when it is
exhausted.

**Acceptance criteria.**

- [x] The budget is configuration rather than a constant. It is a deployment decision, not
      a design one
- [x] Exhaustion is a `REFUSED` naming the budget and when it resets, not a `FAILED`:
      nothing is broken
- [x] The figure counted is tokens actually spent, read from `assistant_exchange`, not an
      estimate maintained separately
- [x] A test exhausts the budget and asserts the next question is refused

---

### TASK-P7-008: narration, and which correlations are guesses

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 2, FEAT-039 |
| Delivers | FEAT-039 |
| Depends on | TASK-P7-006, P4 delivered |
| Estimate | L |

**Goal.** `finops_query/narration.py`. A detected anomaly, explained.

**The objection, and what answers it.** A correlation presented as a cause is the classic
failure of this feature, and it is worse here than usual because the deterministic half is
correct: `cost_anomaly` really did find a day that did not look like the days before it,
so the reader already trusts the row. A narration saying "caused by the deployment at
14:02" borrows that trust for a claim nothing verified. Every correlation is therefore
labelled as one, with its distance in time, and the prose says correlated rather than
caused.

**Acceptance criteria.**

- [x] The anomaly, its severity and its figures come from `cost_anomaly` unchanged. The
      model narrates and computes nothing
- [x] Every correlated event carries its source, Config or CloudTrail or a deploy
      timestamp, and its distance in time from the change
- [x] The prose says correlated, never caused, asserted by a test reading the text
- [x] An anomaly with no correlating event gets a narration saying so, not a speculation
- [x] A slice whose Config history could not be read says that, rather than reporting no
      events, which is the same distinction the topology coverage makes

---

### TASK-P7-009: remediation as a pull request, and nothing applied

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 3, FEAT-040 |
| Delivers | FEAT-040 |
| Depends on | TASK-P7-006 |
| Estimate | L |

**Goal.** Author the Terraform or CloudFormation diff for a recommendation, as a pull
request for human approval.

**The objection, and what answers it.** The same objection FEAT-034 answered for a quota
increase, and the same answer: it is worse for the human by exactly one review, and it
buys the sentence that this product has never changed anything in a customer account.
FEAT-057 already knows which file manages a resource, so a diff has somewhere to go, and a
resource with no `resource_management` row gets a refusal rather than a guess about where
it lives.

**Acceptance criteria.**

- [x] The diff is authored and opened as a pull request. Nothing applies, merges or
      approves
- [x] A resource with no known infrastructure as code address is refused, naming that.
      FEAT-057 supplies the address and its absence is a real state rather than a gap
- [x] The pull request body carries the recommendation, its saving, its provenance and the
      blast radius band from FEAT-044
- [x] A test asserts no code path calls an apply, a merge or an approve

---

### TASK-P7-010: the guard, the routes, and three renderings

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec sections 6, 8 and 9, constraint 3 |
| Delivers | Part of FEAT-042 |
| Depends on | TASK-P7-007 |
| Estimate | L |

**Goal.** The three tables in `SCOPED_TABLES`, then the four routes.

**Acceptance criteria.**

- [x] A test reads each table out of scope and is refused, before a route exists
- [x] `assistant_exchange` is scoped by principal as well as by tenant, and a test asserts
      one person cannot read another's questions. This is the first table in the product
      whose row belongs to a person rather than to an account, so it needs a decision
      recorded rather than an existing shape reused
- [x] Answer, refusal and failure render as three visibly different things
- [x] Every route returns the envelope
- [x] `POST /assistant/ask` is the only write, and it writes one row

**As built, 2026-10-04.** `assistant_exchange` is in `SCOPED_TABLES` under a new rule,
`ByPrincipal`, ADR-0029, and its two routes, ask and the exchange list, are here. The
other two tables do not exist until TASK-P7-012 and TASK-P7-013 create them, so each of
those tasks adds its own table's guard entry, its out of scope test and its route, in
that order. The tool calls go back through the application in process, as the asker,
and ISS-225 records the bound that puts on questions running at once.

---

### TASK-P7-011: the screen where the citations matter more than the prose

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 9, FEAT-042 |
| Delivers | FEAT-042 |
| Depends on | TASK-P7-010 |
| Estimate | L |

**Goal.** `AssistantScreen.tsx`, and `arrives` cleared for `/assistant`.

**Acceptance criteria.**

- [x] Every figure is a `Figure` with its provenance treatment, and each is traceable on
      screen to the tool call behind it
- [x] A refusal names what is missing and links to the screen that would show it, where
      one exists
- [x] Tokens and estimated cost are shown per exchange
- [x] `arrives` cleared in `sections.ts` for `/assistant`
- [x] No accessibility violations

---

### TASK-P7-012: digests, composed whether or not anybody can send them

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec sections 6.2 and 9, FEAT-041 |
| Delivers | FEAT-041 |
| Depends on | TASK-P7-010 |
| Estimate | M |

**Goal.** `finops_ingest/collectors/digests.py`,
`migrations/versions/0024_team_digest.py`, the schedule row, and `DigestsScreen.tsx`.

**The objection, and what answers it.** Building a digest with no sender is building half
a feature. It is the half carrying the risk: composing a summary from the right rows with
the right provenance is the work, and a sender is an adapter behind a port once OPEN-11 is
answered. `sent_at` null is a real state the screen states, which is the shape FEAT-060
already used for a budget with no collected period.

**Acceptance criteria.**

- [x] A digest is composed from the same rows the screens show, with citations
- [x] `sent_at` nullable, and null renders as composed and not sent, with the reason
- [x] Weekly, in `collector_schedule` with its reason and its cost, ADR-0012
- [x] One team failing does not fail the run
- [x] `arrives` cleared in `sections.ts` for `/assistant/digests`

---

### TASK-P7-013: what must not reach a prompt

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 6.3, FEAT-046 |
| Delivers | FEAT-046 |
| Depends on | TASK-P7-011 |
| Estimate | M |

**Goal.** `finops_query/redaction.py`,
`migrations/versions/0025_redaction_event.py`.

**The objection, and what answers it.** ADR-0028 put the model inside the account, so this
is no longer the control standing between customer data and a third party. It is still
built, because a secret in a prompt is a secret in a log whoever receives it, and because
the day somebody reopens ADR-0028 this is the thing that has to already exist.

**Acceptance criteria.**

- [x] The event records which rule matched and never the secret, nor enough of it to
      reconstruct one. A test asserts the stored row does not contain the planted secret
- [x] Blocked and redacted are two outcomes, and which applies is per rule rather than
      global
- [x] A blocked request sends nothing, asserted by a fake provider that fails if called
- [x] The rules are the ones `gitleaks` already uses where possible, rather than a second
      list that drifts from it

---

### TASK-P7-014: the test that keeps the write out

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | P7 spec section 15, constraint 6 |
| Delivers | Part of FEAT-040 |
| Depends on | TASK-P7-013 |
| Estimate | M |

**Goal.** `tests/contract/test_no_llm_writes.py`.

**The objection, and what answers it.** `test_no_quota_writes.py` already asserts an
absence and this is a second file doing the same kind of thing. The subject is different
and so is the failure: that one names one API, and this one has to cover a remediation
path that authors infrastructure code, where the tempting shortcut is not a write API call
at all but a `terraform apply` in a subprocess.

**Acceptance criteria.**

- [x] No production module names an apply, a merge or an approve for a pull request, with
      comments and docstrings stripped before searching, for the reason
      `test_no_quota_writes.py` gives
- [x] No production module invokes a subprocess whose first argument is `terraform`, `aws`
      or `kubectl`
- [x] The hub role grants no write action in a member account, asserted against the
      Terraform
- [x] The capability tests beside it assert the authoring still works, because a check
      that only forbids can be satisfied by shipping nothing

---

## What this plan does not answer

**OPEN-10.** Which Bedrock model, and whether it is available in Ireland and London. The
port and the adapter are written either way and a model identifier is configuration. If
the answer is that the needed model is not there, ADR-0028 says what to do about it, and
it is not to add an egress path.

**OPEN-11.** Where a digest goes. TASK-P7-012 composes and stores; a sender is an adapter
behind a port and one task, once somebody has decided between email and Slack.

**OPEN-12.** A per person question limit, separate from the per tenant token budget.

**ISS-002.** Neither the Bedrock adapter nor anything else in this product has made a real
call.

**Whether the model is good enough.** Not answerable from here, and the plan is arranged
so the answer does not change the architecture: the figures come from the deterministic
layer whatever the model does, so a weaker model produces worse prose beside the same
numbers. The failure degrades rather than inverts, which is the property spec section 5.2
was chosen for.
