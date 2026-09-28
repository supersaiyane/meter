# P7 Insight and LLM layer: design specification

Date: 2026-09-28
Status: Provisional, pending approval
Sub project: P7
Features: FEAT-038, FEAT-039, FEAT-040, FEAT-041, FEAT-042, FEAT-046
Depends on: P1, P2, P3 delivered. P4 for FEAT-039's correlation
Supersedes: nothing

## 1. Purpose

Every other sub project answers a question the product decided to ask. P7 answers the
question somebody actually has, in the words they had it in.

That is the whole value and it is also the whole danger, because the obvious way to
build it destroys everything the previous six sub projects were careful about. A model
given a database and a question produces a confident number, and a confident number
nobody can trace is worse than no answer: every screen here distinguishes measured from
modelled, says when a figure was true, and refuses to render a failure as a zero. One
assistant answering "about forty thousand dollars" undoes the lot.

ADR-0007 settled the shape of the answer before any of this was built. Deterministic
code computes every number, the model is confined to four roles, and every output
carries provenance. This document is what that means in files, tables and routes.

## 2. Definition of done

- A person asks a cost question in English and gets an answer whose every figure is
  traceable to rows the product already computed, with its measured or modelled flag
  and its `as_of` beside it.
- An answer the product cannot support is a **refusal naming what is missing**, never a
  plausible sentence.
- Anomaly narration explains a detected change by correlating it with Config events,
  CloudTrail and deploy timestamps, and says which correlation is a guess.
- A remediation is authored as an infrastructure as code pull request for human
  approval, and nothing applies it.
- Per team digests and executive summaries are composed on a schedule, from the same
  rows the screens show.
- Every exchange is audited, costed, and visible on the platform's own cost screen.
- A secret in a prompt is redacted or the request is blocked, and the event is recorded.

## 3. Out of scope

**Free form SQL, in any form.** ADR-0007 names this and it is worth restating as a
boundary rather than a preference. A model writing SQL against `cost_focus_daily`
bypasses `finops_api/guards.py`, which is one of the two independent enforcement points
constraint 3 requires. A narrowly scoped reader would get the whole organization's bill
and no audit row would say so.

**The model deciding anything.** It does not choose a severity, pick a recommendation,
set a threshold or judge whether a saving was realised. Those are `finops_query`, they
have tests, and they are reproducible.

**Fine tuning or training on customer data.** Not in v1 and not quietly later. It is a
different data processing conversation and it belongs in an ADR of its own.

**A forecast.** ADR-0015's four conditions govern any forecast here and P6's
TASK-P6-012 delivers only the fourth. An assistant asked what next month will cost says
what this month is costing and why it cannot say the other thing.

## 4. Module structure

```
finops_core/
  ports/llm.py             LlmProvider. A protocol over completion with tools, and
                           nothing about a vendor. ADR-0028
  domain/insight.py        Answer, Citation, Refusal, and the rule that an Answer
                           cannot hold a figure without a Citation
finops_providers/
  aws/bedrock.py           The only file importing the Bedrock client. ADR-0028
finops_fakes/
  llm.py                   A deterministic fake. Same question in, same answer out,
                           because an evaluation suite over a sampling model measures
                           the sampler
finops_query/
  insight.py               Question to tool calls to Answer, and the provenance check
                           that refuses an unattributed figure
  narration.py             FEAT-039. Correlation, and which correlations are guesses
  redaction.py             FEAT-046. What must not reach a prompt
finops_ingest/collectors/
  digests.py               FEAT-041. Per team and executive summaries, on a cadence
finops_api/
  routes/assistant.py      The four routes, under the Assistant group per ADR-0020
finops-web/src/screens/
  AssistantScreen.tsx      Ask, and the answer with its citations
  DigestsScreen.tsx        What was composed, and whether it was sent
```

## 5. The decisions this sub project rests on

### 5.1 The model's tools are the MCP tools, which are the HTTP API

Constraint 8 says the HTTP API is the single enforcement point and the MCP server is a
facade in front of it that calls it over the network with the caller's token. ADR-0009
argues it: two implementations of an authorization rule is how an authorization bug is
created.

The governed semantic layer FEAT-038 asks for therefore already exists. It is
`finops_mcp`, it already speaks the envelope, and every call through it already passes
the request dependency and the repository guard, writes an `audit_event`, and carries
the coverage and freshness of what it returned.

So the assistant gets tools, not data, and the tools are the ones the asking human has.
Three things fall out, and all three are properties rather than promises.

- **Scope is not reimplemented.** A reader scoped to two accounts asking a question gets
  an answer about two accounts, enforced by the same guard as the screen, because it is
  the same call.
- **Every answer is auditable by construction.** The reads behind it are already in
  `audit_event`, under the asking principal.
- **The assistant cannot see what a screen cannot.** If the product has no route for a
  question, the assistant has no tool for it, and it refuses rather than improvising.

The cost is that the assistant can only answer what the API can answer. That is the
right constraint, and the tool list is the honest inventory of it: five MCP tools exist
today, and P7 adds the ones its features need rather than adding a data path.

### 5.2 The model never emits a figure. It cites one

This is ADR-0007 made mechanical, and it is the single thing most worth getting right.

An `Answer` holds prose and a tuple of `Citation`. A `Citation` names the tool call it
came from, the field, the value, the `measured` or `modelled` flag and the `as_of`. The
prose contains **placeholders**, not numerals, and the interface substitutes the cited
value when it renders.

That inverts the usual failure. A model that hallucinates a number cannot, because there
is nowhere in the prose for a number to live. A model that hallucinates a *claim* still
can, and will, and that is the residual risk this sub project carries rather than
solves. But the figures on the screen are the figures the deterministic layer computed,
so the failure mode is a wrong sentence beside right numbers, which a reader can catch.
The opposite arrangement fails the other way, and a reader cannot.

`finops_query/insight.py` enforces it: an answer whose prose contains a digit that is
not a placeholder is refused before it reaches a route, as a typed error rather than a
silent strip. A test writes a model response with a bare numeral in it and asserts the
refusal.

### 5.3 A refusal is a first class answer

Three states, and they are three.

- **Answer.** Every figure cited, provenance shown.
- **Refusal.** The question is understood and cannot be answered from what the product
  holds. It names what is missing, which is usually a tool, a collector that has never
  run, or a scope the asker does not have. "I do not have container cost for that
  cluster, because split cost allocation data is not enabled" is a useful sentence.
  "Approximately" is not.
- **Failure.** The model was unreachable, over budget, or returned something the
  provenance check rejected. This renders as a typed cause like every other failure
  here, through the existing `TypedError` component.

A product that collapses the second into the first is the one every reader learns to
distrust. A product that collapses it into the third teaches them the assistant is
broken when it is being careful.

## 6. Data model

### 6.1 `assistant_exchange`

| Column | Why |
| --- | --- |
| `exchange_id`, `tenant_id`, `principal_id` | Who asked, under which tenant |
| `question` | As typed. Never normalised, because the wording is evidence when an answer turns out wrong |
| `outcome` | `ANSWERED`, `REFUSED` or `FAILED`. The three of section 5.3 |
| `answer` | The prose with its placeholders. Null on a refusal or a failure |
| `refusal_reason` | Required when `REFUSED` and forbidden otherwise, the same biconditional 0020 uses for a quota |
| `failure_cause` | One of the seven typed causes, required when `FAILED` |
| `citations` | JSONB. The tool, field, value, provenance and `as_of` of every figure |
| `tool_calls` | JSONB. Which tools were called, in order, so an answer can be replayed |
| `model_id`, `input_tokens`, `output_tokens`, `est_cost` | What it cost. Constraint 7 |
| `asked_at`, `answered_at` | Ours. Not `as_of` and `collected_at`: an exchange records our own work, like `IngestRun`, and giving it an `as_of` would invite the question of what the value means. The `as_of` of each cited figure is in `citations`, where it belongs |

Constraints, per constraint 11: `refusal_reason` non empty if and only if `outcome` is
`REFUSED`; `failure_cause` present if and only if `FAILED`; `answer` present if and only
if `ANSWERED`; `est_cost >= 0`; `answered_at >= asked_at`.

### 6.2 `team_digest`

FEAT-041. One row per team per period, with the prose, its citations and what was sent.
`sent_at` is nullable and null means composed and not sent, which is a real state on the
first run and after a send failure rather than an absence to hide.

### 6.3 `redaction_event`

FEAT-046. What was found, which rule found it, whether the request was redacted or
blocked, and the exchange it belonged to. **Never the secret itself**, and never enough
of it to reconstruct one: a table of redacted secrets is a worse leak than the prompt
would have been.

## 7. Flow

```
person types a question
        |
        v
finops_query/redaction.py  ---> a secret found: BLOCKED, event recorded, nothing sent
        |
        v
finops_query/insight.py
        |  builds a prompt carrying the tool schemas and no data
        v
finops_core/ports/llm.py --> finops_providers/aws/bedrock.py --> Bedrock, in the hub
        |
        |  the model asks for tools
        v
finops_mcp  --> the HTTP API --> the guard --> the repository --> audit_event
        |
        |  tool results, enveloped, with coverage and freshness
        v
the model writes prose with placeholders
        |
        v
the provenance check: every placeholder cited, no bare numerals
        |                                        |
     passes                                    fails
        v                                        v
   ANSWERED                                   FAILED, SchemaDrift
```

Cadence: the assistant is on demand. `digests.py` is weekly, in `collector_schedule`
with its reason and its cost, per ADR-0012.

## 8. Interface

| Route | Group | Answers |
| --- | --- | --- |
| `POST /assistant/ask` | Assistant | A question, and an answer, a refusal or a typed failure |
| `GET /assistant/exchanges` | Assistant | What has been asked and what came back |
| `GET /assistant/digests` | Assistant | Composed digests, and whether they were sent |
| `GET /assistant/redactions` | Assistant | What was blocked, and by which rule |

`POST /assistant/ask` writes, and that needs saying because constraint 6 is often read as
forbidding writes generally. It forbids a write **into a member account**. This writes an
`assistant_exchange` row into Meter's own database, which is what the recommendation
lifecycle and the two P2 remediation routes already do. Nothing in P7 writes to AWS.

## 9. User interface

`/assistant` and `/assistant/digests` already exist in `sections.ts` marked as arriving
with this sub project, so P7 clears markers rather than adding rows, unlike P6. Two more
rows are added inside the same group, for exchanges and redactions.

**The answer is not the interesting part of the screen. The citations are.** Every figure
is a `Figure` component with its existing provenance treatment, and each carries a
reference to the tool call behind it, expandable to the call and its envelope. A reader
who does not trust the sentence can check the number without leaving the page.

**A refusal looks like a refusal, not like an error and not like an answer.** It uses the
`StateBoundary` vocabulary the product already has, with the missing thing named and,
where there is one, a link to the screen that would show it once the gap closes.

**The cost of the conversation is on the page.** Tokens and estimated cost per exchange,
because a FinOps product that hides what its own assistant costs has picked the one
feature it is not allowed to be coy about.

## 10. Infrastructure

No new stack. The hub task role gains `bedrock:InvokeModel` and
`bedrock:InvokeModelWithResponseStream`, scoped to named model identifiers, per ADR-0028.
Nothing is granted in a member account and the org reader role is unchanged.

A per tenant monthly token budget lives in settings. The assistant refuses when it is
exhausted rather than continuing to spend, and the refusal names the budget.

## 11. Testing

This is the section that makes P7 buildable to this project's standard, and the one
worth the most argument.

**The fake model is deterministic.** `finops_fakes/llm.py` returns a scripted response
per question, so every test above it is reproducible. An evaluation suite run against a
sampling model measures the sampler.

**Three test sets, and the second and third are the ones that matter.**

1. **The answer set.** Questions with a known correct answer over the fake estate, each
   asserting the figures match what `finops_query` computes for the same question. Not
   that the prose is right, which is not testable, but that no figure differs from the
   deterministic one. That is the whole claim.
2. **The refusal set.** Questions the assistant must decline, each with the reason it
   must give: a cluster with no split cost allocation data, an account outside the
   asker's scope, a question needing a tool that does not exist, a request for next
   month's cost. A product that answers these is the product this one exists not to be,
   and the set is where that is enforced rather than hoped for.
3. **The injection set.** Prompts trying to make the model call a tool outside the
   asker's scope, emit a bare numeral, or repeat a secret from the question. The scope
   case cannot succeed, because the tool call carries the caller's token and the guard is
   the same one, and the test asserts the refusal rather than assuming the architecture.

**A provenance test over every answer in every set**: no bare numerals, every placeholder
cited, every citation resolving to a real tool result.

**A cost test.** An exchange records tokens and an estimated cost, and a test asserts a
non zero cost reaches `assistant_exchange`, because a self metering product whose newest
feature reported zero would be making the exact mistake it was built to catch.

## 12. Risks

**The model writes a confident wrong sentence about correct numbers.** Not solved, and
section 5.2 says why it is the better failure. Mitigated by putting the citations next to
the prose so a reader can check, and by keeping answers short enough to read.

**The refusal set erodes.** The pressure on every assistant is to answer more, and each
individual softening looks reasonable. The set is a test file, so softening it is a diff
somebody reviews.

**Cost runs away.** A question is cheap and a thousand are not. The per tenant budget is
in section 10 and the spend is on the platform screen, which is the one place in this
product where a cost overrun is certain to be noticed.

**Bedrock does not carry the model P7 needs in Ireland or London.** ADR-0028 names this
as the price of the hosting decision and says what to do, which is to reopen the ADR
rather than add an egress path.

## 13. Open questions

| ID | Question | Effect if unanswered |
| --- | --- | --- |
| OPEN-10 | Which Bedrock model, and is it available in Ireland and London | The port and the adapter are written either way. A model identifier is configuration |
| OPEN-11 | Where does a digest go, email or Slack or both | FEAT-041 composes and stores regardless. `sent_at` stays null until there is a sender, which is a real state and is already modelled |
| OPEN-12 | Is there a per person or per question limit, separate from the token budget | The budget in section 10 is per tenant per month. A per person limit is a policy decision nobody has made |

## 14. Features delivered

FEAT-038, FEAT-039, FEAT-040, FEAT-041, FEAT-042 and FEAT-046.

FEAT-042 is not a separate mechanism. "Find anything in the tool" is the same tool
calling loop with the navigation as one more tool, and it is called out here because
building it as a second path would be a second place to enforce scope.

## 15. Exit criteria

1. A question answered with every figure cited, its provenance shown and its `as_of`
   beside it.
2. The refusal set passes, including the out of scope question and the forecast question.
3. The injection set passes, including the attempt to read another account.
4. No answer in any set contains a numeral the provenance check did not place.
5. A week of digests composed, with `sent_at` null and the screen saying so.
6. A redaction event recorded for a prompt carrying a secret, with the secret absent from
   the row.
7. Bedrock spend visible on the platform cost screen, tagged `finops:module`.
8. `POST /assistant/ask` writes nothing to AWS, asserted by the same kind of source scan
   `tests/contract/test_no_quota_writes.py` uses.

None of these has been met against a real account or a real model. ISS-002, and OPEN-10.
