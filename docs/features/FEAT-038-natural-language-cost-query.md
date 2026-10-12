# FEAT-038: Natural language cost query

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Delivered |
| Specification | [P7 spec](../specs/2026-09-28-p7-insight-and-llm-layer-design.md), sections 5.1, 5.2 and 7 |
| Tasks | TASK-P7-001 to TASK-P7-007 |
| Refresh cadence | Live |

## What it does

Ask a cost question in plain English and get an answer built from Meter's own typed APIs.

## Why it exists

The requirement asked whether a language model could help. This is where it genuinely does.

## What is already known

Tool calling against the MCP server, over a governed semantic layer. Never free form SQL against CUR, which is both a hallucination risk and a query cost risk inside a product built to prevent runaway query cost. See ADR-0007 and ADR-0009.

## How it works

**As built, 2026-10-04, TASK-P7-001 to TASK-P7-007.** `finops_query/insight.py` runs the
loop. The model is offered the tool table in `finops_api/tools.py`, the rows the MCP server
publishes, each one a route the screens already read, and two terminal tools, `answer` and
`refuse`. Every tool call goes back through the API in process, as the person asking and
under their scope, so it passes the same dependency, guard and audit row as a call from a
screen. The tools are the semantic layer, and there is no SQL the model can write.

The model never writes a figure. An answer is prose holding `{{name}}` placeholders and no
numerals, and each placeholder is a citation naming a call id and a path into that call's
result, such as `data[name=AmazonEC2].effective_cost`. The loop reads the value from the
result itself, with its provenance, its `as_of` and the unit its tool declares for that
field, ISS-231, and `Answer` refuses to exist holding a
figure no citation placed. A numeral in the prose, a citation of a call that never
returned, a path that cannot be read, a selector matching more than one row, or a model
that stops without a terminal tool is a typed SchemaDrift failure, never a best effort
answer.

Some gaps are decided by the loop rather than the model. An unknown tool, a null figure, a
selector with no match where the row states its own reason, an empty list beside
`meta.failures`, a forecast figure and a figure with no `as_of` each become a refusal naming
the gap. A selector with no match otherwise becomes a SCOPE refusal, because the row may
exist outside what this person can see.

`finops_api/assistant.py` orders the guards. The question is screened for secrets first,
FEAT-046. Then a deployment with no model reports itself as not enabled, then the monthly
token budget refuses before any model is reached, and only then does the loop run, on the
screened text. Every question writes one `assistant_exchange` row whatever its outcome,
with its tokens and an estimated cost. The cost is **modelled**, from the two configured
prices per million tokens, and the budget counts tokens rather than dollars, so a price
change cannot move it. The model is Bedrock in the hub account, ADR-0028, behind
`LlmProvider`, and nothing above `finops_providers` names a vendor. Never run against AWS,
ISS-002.

## Failure behaviour

Three outcomes, each its own shape in the API, the database and the screen. A refusal names
its gap, TOOL, FIGURE, SCOPE, BUDGET or SECRET, with a reason and, where one exists, the
screen that would show the figure. The budget refusal names the budget, the month, the
spend so far, the date it resets and the setting that raises it. A failure names one of the
seven causes. A deployment with no model configured answers every question as NotOptedIn,
not enabled, and spends nothing. A question past `METER_ASSISTANT_MAX_CONCURRENT_QUESTIONS`
is answered at once as Throttled and spends nothing, ISS-225, and a figure whose unit its
tool does not declare is SchemaDrift rather than a guess, ISS-231.

Bedrock's errors are translated rather than passed through. A model not enabled for the
account is NotOptedIn, an identifier Bedrock does not recognise is Misconfigured, a timeout
or a service fault is Unreachable, and a guardrail or content filter is SchemaDrift, because
an answer it withheld cannot be checked. A cap of six tool rounds ends a loop that does not
converge. The word one passes the figure check, ISS-229.

## Security considerations

The model sees only what the asker could read on a screen, because every tool call carries
their token and passes the same guard. Prompts go no further than Bedrock in the hub
account, and the hub role may invoke only the models named in `assistant_model_ids`, which
refuses a wildcard, and only through each model's inference profile tagged
`finops:module = assistant`, ISS-230. Prompt injection is a test set,
`tests/query/insight/test_injection_set.py`. An exchange is readable only by the person who
asked, ADR-0029, and a question holding a credential never reaches the model, FEAT-046. The
exchanges are kept 90 days, `retention_assistant`, and erasure tombstones them, ISS-226, both
decided by the owner on 2026-10-12, OPEN-14.

## Interface

`POST /assistant/ask` and `GET /assistant/exchanges`, rendered by the `/assistant` screen,
FEAT-042. Each exchange carries the tool calls it made, so a cited figure can be traced to
the call that returned it.

## Not doing

**Free form SQL.** The tools are the only way to data. **Arithmetic by the model.** A
figure no tool returns cannot be cited, so an answer that needs one becomes a refusal.
**Memory across questions.** Each question stands alone. **A per person limit**, OPEN-12.
