# ADR-0007: The language model never computes a number

Date: 2026-08-23
Status: Accepted

## Context

The requirement asks whether a language model can produce the best sizing
suggestions. It can produce plausible ones. Plausible is the problem.

A FinOps platform succeeds or fails on whether an engineering team believes a
number enough to change infrastructure. One hallucinated savings figure, found
by an engineer who checks, permanently destroys that trust across the whole
product, including the parts that were correct.

## Decision

Deterministic components compute every number. Detection, sizing arithmetic,
cost modelling and savings estimates are code, with tests, and are reproducible.

The language model is confined to four roles.

1. Natural language to cost question, over a governed semantic layer with tool
   calling against Meter's own APIs. Never free form SQL against CUR.
2. Anomaly narration. Deterministic detection finds what changed. The model
   correlates the CUR delta with Config change events, CloudTrail and deploy
   timestamps to explain why, and drafts the ticket.
3. Remediation authoring. Generate the Terraform or CloudFormation diff, or
   the Grafana panel patch, and open a pull request for human approval.
4. Summarization. Weekly per team digests and executive summaries.

Every model output carries provenance: which rows, which time range, and the
measured or modelled flag of each figure it cites.

## Consequences

Positive.

- Every number in the product is reproducible and defensible in a review.
- The model is used where it is genuinely strong, which is correlation across
  heterogeneous evidence and writing readable explanations.
- Model spend is bounded and predictable, because the model is not in the
  read path of every dashboard.

Negative.

- More engineering work than delegating analysis to a model.
- The tool contract between the model and Meter's APIs has to be designed and
  maintained.

## Alternatives rejected

**Free form SQL generation against the CUR tables.** Rejected twice over. It
is a hallucination risk, and it is a query cost risk inside a product whose
entire purpose is preventing runaway query cost.

**Model produced sizing recommendations.** Rejected. Sizing must be defensible
to the engineer who owns the workload, and a model cannot show its arithmetic.
