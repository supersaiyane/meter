# FEAT-016: Query owner attribution

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Attaches a human owner to every expensive query: Grafana folder to team mapping, the last editor from the Grafana API, and the CloudTrail principal that ran it.

## Why it exists

ISS-021. An unowned finding is never fixed. This is the difference between a report and a resolution.

## How it works

Resolves a human owner for every expensive query, from three sources in priority order: the Grafana folder to team mapping, the dashboard's last editor from the Grafana API, and the CloudTrail principal that ran the query.

## What is already known

The prototype already extracts the CloudTrail principal. Folder and editor attribution is new.

## Failure behaviour

A query with no resolvable owner is reported as unowned rather than assigned to a default. A wrongly assigned owner is worse than an absent one, because it gets ignored by the person it was sent to and never reaches the person who could act.

## Security considerations

`folder_team_map` holds email addresses, which is personal data. It is classified and retained under `docs/09-DATA-CLASSIFICATION.md` like any other class P table.

## Interface

`query_finding.owner_email` and `owner_source`, so a reader can see which of the three sources produced it. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 7.1.

## Read surface

The API sends `owner` as null when nothing resolved it, never the word `unattributed`. The screen renders that word. Putting it on the wire would make it untranslatable, would sort among real addresses, and would be indistinguishable from a mailbox somebody had actually created.

## Not doing

Does not create or manage teams. The folder mapping is entered, not derived.
