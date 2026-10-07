# FEAT-075: An account picker on every screen, one account or all, searchable

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 plan](../plans/P8-implementation-plan.md), TASK-P8-016 |
| Tasks | TASK-P8-016 |

## What it does

One search box in the top bar of every screen. A reader types an account's number or name, a
service or a resource. Choosing an account shows every screen, the Overview and every export
included, for that account alone, and All accounts, first in the list and the default, combines
them again. Choosing a service opens Cost Explorer filtered to it, and choosing a resource opens
its page, both keeping the account. When nobody is typing in it, the box shows what every screen
is narrowed to, and a narrowed screen names the account under its title.

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

The owner decided two more things on 2026-10-06. A narrowed screen states the choice plainly:
the account is named under the title and coverage is counted against it, so choosing one
account is not reported as a partial view, while a failure or missing data in that account
still shows. And the box searches services and resources as well as accounts, as the drawn
placeholder says: an account narrows every screen, a service opens Cost Explorer filtered to it,
and a resource opens its page.

## How it works

The choice lives in the address as `account`, the account number. It is the key Cost Explorer
and Resources already read as their account filter, so those filters and the choice are one
thing rather than two that can disagree. Every link in the application comes from
`finops-web/src/shell/links.tsx`, which keeps the account on its destination, and
`finops-web/src/shell/__tests__/links.test.tsx` fails the build if any file reaches for the
router's own links, which would drop it.

Every read in `finops-web/src/api/queries.ts` carries the choice to the API as `chosen_account`
and puts it in its cache key, so one account's figures are never served from the cache under
another's name. The API takes it under its own name because `/api/v1/cost/explore` reads
`account` as a list of filter values, and the scope dependency reading that name would narrow a
request for two accounts to one of them without saying so. `get_scope` in
`finops_api/deps.py` looks the account up through the scope the resolver gave, in a short
transaction of its own so the assistant does not hold one open while it waits on a model, and
narrows the scope with `Scope.narrowed_to` in `finops_core/domain/tenant.py`. The repository
guard then applies the narrowed scope, so enforcement is still in two places.

A narrowed scope carries `chosen`. `build_meta` counts coverage against the chosen account
rather than the organization and returns it as `scope_coverage.chosen`; the shell names the
account under the title and the coverage line reads "the chosen account". A workbook made while
an account is chosen says so on its About sheet, in the Scope and Coverage rows.

The box is a React Aria combobox, `finops-web/src/shell/SearchBox.tsx`, and what it offers is
decided in `searchModel.ts` beside it. The accounts come from one read of `/api/v1/accounts`
that a choice never narrows, kept for five minutes and searched in the browser, so typing never
waits on the network. At 1,399 accounts the list shows 50 and says how many more typing would
find. Services come from `/api/v1/cost/by-service`, narrowed like any read. Resources are
searched on the server through `q` on `/api/v1/inventory/resources`, a substring of the name or
the ARN in any letter case, once three characters are typed and typing pauses for 250
milliseconds, eight at a time.

## Failure behaviour

An account the session cannot see and an account that does not exist get the same answer, a 404
saying no account by that number is in the session's scope, so a link cannot be used to learn
which accounts exist. The screens show that failure, and the title says the account is one this
session cannot see. A malformed account number is refused with 422 before any query is built
from it. A chosen account with nothing collected reads as 0 of 1 accounts, partial, and a
failing collection in it still shows. If the accounts, the services or the resources cannot be
read, the box says which rather than offering a list that is missing them.

## Security considerations

The parameter only narrows. The account is looked up through the resolved scope, and
`Scope.narrowed_to` refuses one outside it, so a request can neither build a scope nor widen
one, and the repository guard applies whatever scope results. The lookup writes the audit row
every scoped read writes. The search text is bound as a parameter and matched as written: its
percent signs and underscores are escaped rather than read as wildcards. Its length is bounded
at three to 200 characters.

## Interface

- `?account=<number>` in the address of every screen.
- `chosen_account=<number>` on every API route that takes a scope.
- `scope_coverage.chosen` on every envelope: the chosen account, or null.
- `q=<text>` on `GET /api/v1/inventory/resources`.

## Not doing

- Several accounts at once. The owner chose one account or all on 2026-10-05.
- An index for the resource search. It scans the tenant's resources for the text, bounded by
  the length and the count, and ISS-252 records what an estate of 1,399 accounts will need.

## Status of this document

Written when TASK-P8-016 was delivered, 2026-10-06.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
