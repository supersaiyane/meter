# FEAT-039: Anomaly narration

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | In build |
| Specification | [P7 spec](../specs/2026-09-28-p7-insight-and-llm-layer-design.md), section 2 |
| Tasks | TASK-P7-008 |
| Refresh cadence | Follows FEAT-023 |

## What it does

Explains why a cost anomaly happened by correlating the cost delta with Config change events, CloudTrail and deploy timestamps, and drafts the ticket.

## Why it exists

Correlating heterogeneous evidence and writing a readable explanation is what a language model is actually good at.

## What is already known

Deterministic detection finds what changed. The model only explains. It never computes a figure, see ADR-0007.

## How it works

**As built, 2026-10-04, TASK-P7-008.** `finops_query/narration.py` narrates one anomaly from
its `cost_anomaly` row, taken unchanged, and the change events it is given. An event from
the forty eight hours before the anomaly's day, or from that day itself, becomes a
correlation carrying its source, Config, CloudTrail or a deploy, and its distance in time,
nearest first. The prose
says correlated and never caused, and `assert_correlational` rejects the causal words, so
the claim is checked on the text rather than promised by a prompt.

The first cut is a deterministic template, not a model. The narration is an `Answer` like
any other, its figures cited from the anomaly row, so it calls no model and spends no
tokens. This differs from what was known before the spec, which expected a model to write
the explanation and to draft a ticket. Neither happens yet.

**Why In build.** No collector reads Config history, CloudTrail or deploy timestamps, and
nothing in the product calls `narrate`, ISS-227. Against a real account today every source
would be reported as not read.

## Failure behaviour

A source that was not read says so, by name and with the reason, rather than reporting no
events, the same distinction the topology coverage draws. An anomaly with no event in the
window gets a narration saying none was found, not a speculation.

## Security considerations

It reads nothing itself. The change history collector it needs will be read only, like
every collector, constraint 6.

## Interface

None yet, ISS-227. The function is `narrate(anomaly, events, readings)`, where `readings`
says for each source whether it was read and, if not, why.

## Not doing

**Claiming a cause.** A correlation that borrows the anomaly's credibility for a claim
nothing verified is the failure this feature exists to avoid. **Drafting the ticket** in
this cut.
