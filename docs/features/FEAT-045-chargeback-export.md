# FEAT-045: Chargeback and showback export

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Delivered |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md), section 16, and [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.5 |
| Tasks | TASK-P1-018, TASK-P8-009 |
| Refresh cadence | On demand |
| Source | Adopted from a competitive review on 2026-08-23 |

The title said CSV until 2026-10-05. TASK-P8-009 delivered this feature through FEAT-067, the
export every screen has, and the file is now a workbook or a CSV.

## What it does

`GET /cost/showback` returns one billing period, one row per account, service and tag value,
with the unallocated bucket included as a named row. The Exports screen shows the rows, and the
Export menu beside its title writes them as an Excel workbook or as a CSV of every row.

## Why it exists

Finance does not work inside our interface. A FinOps tool that cannot hand finance a file is
missing its actual consumer, and the gap was invisible until a competitive review made it
obvious.

## How it works

**Read from the repository the screens read, not from a second query.** That is the whole
design. `CostRepository.for_export` uses the same table, the same scope predicate and the same
unallocated bucket as `/cost/by-account` and `/cost/allocation`, grouped three ways instead of
one so the file can be pivoted.

The consequence is the property worth having: summing the file's Effective Cost column gives
the figure on `/cost/summary`, which is the figure the spend screen shows, and the Exports
screen states that figure before anyone opens the file. `tests/api/test_cost_showback.py`
asserts it by summing the CSV and comparing, rather than against a total written into the test,
so any drift fails. It asserts the same for a narrowed scope, because a file that reconciles
only for a global reader reconciles against nothing for everybody else.

**Every figure names its measure in its heading.** The FOCUS names, `Effective Cost` and
`Billed Cost`, never `Cost`. The two differ by exactly the commitment discount, and nothing in a
bare number in a spreadsheet cell says which one is in it.

**The route used to write the CSV by hand.** Until 2026-10-05 it was `GET /cost/export`, a CSV
exempt from the envelope. It now returns its rows in the envelope like every other route, and
its file comes from the one export responder, so `ENVELOPE_EXEMPT` holds no route that returns
tenant data.

## What is already known

The rows carry what the envelope carries, as columns: `as_of`, `collected_at`,
`accounts_in_file` and `accounts_in_organization`, on every row rather than in a header block.
A spreadsheet is sorted, filtered, mailed on and pasted a row at a time into a deck, and only
the cells survive that. The workbook also carries them on its About sheet, with every failure
in the view.

The unallocated bucket is a row, never omitted. An export that silently excludes what could
not be attributed reconciles to nothing, and it reports a smaller estate than exists.

## Failure behaviour

A tenant with no cost collected gets 404, for the screen and for either file, not an empty file
with a heading row. An empty file says the estate spent nothing, which is a claim nobody has
earned the right to make. Constraint 5.

A tag key nobody used returns the whole period with every row in the unallocated bucket, rather
than nothing. An export returning nothing because a key was misspelled looks exactly like an
estate with no spend.

## Security considerations

Scoped by the same repository guard as every other read, and asserted three ways: a narrow
scope exports less, exports only its own accounts, and its file still agrees with its own
summary. Every file is recorded in `report_run`, and a tag value that would be a formula is
written as text. Both are FEAT-067's, which this route uses unchanged.

## Interface

`GET /cost/showback?tag=<key>&period=<date>`, with `format=xlsx` or `format=csv` for the file.
The tag key defaults to `team`. The Exports screen, `/report/exports`, states the total the file
must add up to, shows the rows, and offers them in the Export menu.

## Not doing

A workbook layout of our own design. The workbook is FEAT-067's, a Data sheet and an About
sheet that says what the figures are, and nothing presented as a decision nobody made.
