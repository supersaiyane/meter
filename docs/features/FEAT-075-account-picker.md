# FEAT-075: An account picker on every screen, one account or all, searchable

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 plan](../plans/P8-implementation-plan.md), TASK-P8-016 |
| Tasks | TASK-P8-016 |

## What it does

A search box with a dropdown in the top bar of every screen. A reader types an account's
number or name, chooses it, and every screen, the Overview and every export included, shows
that account alone. All accounts is first in the list and the default, so the Overview opens on
the whole estate combined.

## Why it exists

The owner runs 1,399 AWS accounts and said on 2026-10-05 that the data cannot only be read as
one sum: a person responsible for one account has to be able to see that account's complete
picture without filtering screen by screen.

## What is already known

The owner chose on 2026-10-05: one account or all, rather than several at once or a picker on
each screen; the choice kept in the address, so a shared link opens the same account; and the
search and the dropdown in one control. The narrowing is applied where scope already is, at the
request dependency, so every route obeys it at once and it can only narrow what the session may
see, never widen it. Scope enforcement in two places is unchanged.

## Status of this document

Planned as TASK-P8-016. The sections a built feature carries, how it works, its failure
behaviour, its security considerations, its interface and what it does not do, are written when
it is built.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
