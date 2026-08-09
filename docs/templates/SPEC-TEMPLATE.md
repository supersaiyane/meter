# P<n> <name>: design specification

Date: YYYY-MM-DD
Status: Draft | In review | Approved | Superseded
Sub project: P<n>
Depends on:
Blocks:

## 1. Purpose

What this sub project delivers, in one paragraph. State what it deliberately
does not deliver.

## 2. Definition of done

Written as something a person can observe and confirm, not as a list of
components. If a reader cannot tell from this section whether the sub project
is finished, rewrite it.

## 3. Out of scope

List explicitly. Each entry makes adding that thing a visible decision rather
than a drift.

## 4. Module structure

Directory tree with one line per module stating its responsibility. Name the
dependency rules that must not be broken.

## 5. Data model

Every table, every column that matters, and every constraint. State which
values are closed sets, and list the members.

## 6. Error taxonomy

The closed set of failures this sub project can produce, what each one means,
and how each is shown to a user. State explicitly which failures may render as
zero. In this project the answer is almost always none.

## 7. Flow

How data moves. A diagram plus prose. Name every scheduled job and its cadence.

## 8. Interface

API routes, or the equivalent contract this sub project exposes. State what
every response carries regardless of route, for example freshness and scope
coverage.

## 9. User interface

Screen by screen. What is on it, what question it answers, and why it exists.
A screen that answers no question is removed.

## 10. Infrastructure

What Terraform provisions, in which root module, and why. Call out any choice
that looks over engineered until the bill arrives.

## 11. Testing

Table of layer against approach. Then list the specific tests that encode the
rules this design exists to protect, the ones a reasonable person might delete
because they look redundant.

## 12. Risks

Table: risk, impact, mitigation, tracker identifier. A risk with no tracker
identifier is a worry, not a risk.

## 13. Open questions

Reference the OPEN rows in `tasks/ISSUES.md`. State which of them block
delivery of this sub project and which do not.

## 14. Features delivered

Table of FEAT identifiers this specification covers, so `INDEX.md` can be
reconciled against it mechanically.
