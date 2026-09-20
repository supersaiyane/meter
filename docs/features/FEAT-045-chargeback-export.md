# FEAT-045: Chargeback and showback export, CSV

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Specified |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md), section 16 |
| Tasks | TASK-P1-018 |
| Refresh cadence | On demand |
| Source | Adopted from a competitive review on 2026-08-23 |

The title said CSV and Excel until 2026-09-20. Excel is not built, and a document
promising a format the product does not produce is a document that will be quoted
back. The reason is under Not doing.

## What it does

`GET /cost/export` returns one billing period as CSV, one row per account, service
and tag value, with the unallocated bucket included as a named row.

## Why it exists

Finance does not work inside our interface. A FinOps tool that cannot hand finance a
file is missing its actual consumer, and the gap was invisible until a competitive
review made it obvious.

## How it works

**Generated from the repository the screens read, not from a second query.** That is
the whole design. `CostRepository.for_export` uses the same table, the same scope
predicate and the same unallocated bucket as `/cost/by-account` and
`/cost/allocation`, grouped three ways instead of one so the file can be pivoted.

The consequence is the property worth having: summing the file's amortized column
gives the figure on `/cost/summary`, which is the figure the spend screen shows.
`tests/api/test_cost_export_route.py` asserts that by summing the file and
comparing, rather than against a total written into the test, so any drift fails. It
asserts the same for a narrowed scope, because a file that reconciles only for a
global reader reconciles against nothing for everybody else.

**Every figure names its measure in the header.** `effective_cost_amortized_usd` and
`billed_cost_usd`, not `cost`. The two differ by exactly the commitment discount, and
nothing in a bare number in a spreadsheet cell says which one is in it, so a column
headed `cost` is a column somebody argues about later.

## What is already known

The export carries what the `meta` envelope carries, as columns rather than as an
envelope: `as_of`, `collected_at`, `accounts_in_file` and
`accounts_in_organization`. A spreadsheet that leaves the product without its
freshness and coverage becomes a number in a board pack with no way back to what it
meant.

They are on **every row** rather than in a header block, because a spreadsheet is not
read the way a response is. It gets sorted, filtered, mailed on and pasted a row at a
time into a deck, and only the cells survive that.

The unallocated bucket is a row in the export, never omitted. An export that silently
excludes what could not be attributed reconciles to nothing, and it reports a smaller
estate than exists.

## Failure behaviour

A tenant with no cost collected gets 404, not an empty file with a header row. An
empty CSV says the estate spent nothing, which is a claim nobody has earned the right
to make. Constraint 5.

A tag key nobody used exports the whole period with every row in the unallocated
bucket, rather than an empty file. An export returning nothing because a key was
misspelled looks exactly like an estate with no spend.

The screen says when a download fails and why. A button that silently does nothing is
one a reader presses four times and then distrusts the whole screen, and a browser
without object URLs gets a sentence rather than a broken page.

## Security considerations

Scoped by the same repository guard as every other read, and asserted three ways: a
narrow scope exports less, exports only its own accounts, and its file still agrees
with its own summary. An export is the easiest place to leak an estate, because it is
the one response nobody reads on screen before saving it.

This is the only route in `ENVELOPE_EXEMPT` that returns tenant data. The exemption
is recorded there with its reason: a JSON wrapper round a CSV is a wrapper somebody
strips by hand, and the envelope's purpose is met by the four columns above.

## Interface

`GET /cost/export?tag=<key>&period=<date>` and `/cost/export`. The screen holds no
data of its own on purpose. Its job is to state, before the download, the total the
file must add up to, so the reader can check our arithmetic in about ten seconds. It
also lists every column, so nobody has to open the file to learn what is in it.

## Not doing

**Excel is not built.** An `.xlsx` workbook carries formatting, column widths, a
sheet name and often a frozen header, and every one of those reads as a decision
somebody made about these figures. Nobody has made them, and inventing them puts our
presentation between finance and their own numbers. A spreadsheet opens a CSV
directly, so the format costs a reader nothing. It becomes worth building when
somebody asks for a specific workbook layout, which is a request with an answer in
it.

**Excel formula injection is therefore not a live risk here**, and would be if the
workbook were built: a tag value beginning with an equals sign is a formula when
Excel opens it. Worth writing down now so the first `.xlsx` commit does not have to
rediscover it.
