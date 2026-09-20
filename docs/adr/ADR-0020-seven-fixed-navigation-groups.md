# ADR-0020: Seven fixed navigation groups, and the routes they fix

Date: 2026-09-06
Status: Accepted

## Context

`finops-web/src/shell/sections.ts` is a flat array of five strings, one per
screen built in P0. It is correct for P0 and does not survive the roadmap.

Fifty features across eight sub projects produce roughly twenty four screens. A
flat navigation reaches that number by growing one entry at a time, and at
twenty four entries a user finds a screen by knowing which sub project built it.
**The sub project decomposition is a delivery decision, recorded as ADR-0001. It
is not a user concept**, and a navigation that exposes it makes the audience
learn the build plan in order to use the product.

The choice was reachable earlier and was not made, because until
`docs/12-UI-DESIGN.md` existed there were no interface requirements to decide it
against. That document decided how a number looks and explicitly deferred where
it lives.

## Decision

Seven top level groups, fixed for the life of the product. A sub project adds
screens inside an existing group and never adds a top level entry.

| Group | Answers |
| --- | --- |
| Home | Can I trust this, and where is the money |
| Cost | Where is the money going |
| Waste | What is being spent badly, and what did we recover |
| Governance | What rules and limits constrain the estate |
| Inventory | What do we have, and how is it connected |
| Platform | Is Meter itself working |
| Assistant | Ask, and receive an answer with its provenance |

Every route carries its group as its first segment, so a URL states which of the
seven questions the screen answers. Scope and filters live in the query string,
never in the path.

The full architecture is `docs/13-UI-ARCHITECTURE.md`.

## Why this is an ADR

It fixes every URL in the product. Changing the groups later means changing
every route, every link between screens, every bookmark, and every link already
pasted into a ticket. That is the definition of expensive to reverse.

## Consequences

Positive.

- The navigation is the same size at P7 as at P0.
- A new screen must answer one of seven questions, so a screen with an undecided
  purpose fails to be placed. That refusal is the correct outcome.
- Findings from P2, P3 and P6 can be pooled and ranked on one screen, because
  they are already understood as answers to the same question rather than as
  outputs of three sub projects.
- A group whose sub projects have not landed still lists its screens with their
  arrival, so the roadmap is legible inside the product.

Negative.

- Five built P0 screens change route. The change is small and it is a breaking
  change to any link already shared.
- An edge case screen must be argued into a group rather than added to a list.
  This is the cost of the constraint and also the point of it.
- Group names are now load bearing product vocabulary. Renaming Waste later is
  an ADR, not a copy edit.

## Alternatives rejected

**Keep the flat list.** Cheapest today. Reaches roughly twenty four top level
entries by P4, ordered by nothing a user can reason about, and forces the
audience to learn the sub project decomposition. Rejected on the evidence that
the decomposition is a delivery unit, not a user concept.

**Question led groups**, top level entries reading as verbs: where is my money
going, what is wrong, what do I own. More opinionated and more immediately
legible. Rejected because an edge case screen is genuinely hard to place under a
verb, and a navigation that cannot place a screen without an argument every time
is a navigation the team will route around.

**A two level domain rail**, icons on the far left and a secondary panel of
screens. Scales furthest. Rejected for now on cost rather than merit: it spends
horizontal chrome and one extra click per screen to solve a problem twenty four
screens do not yet have. Seven groups with a flat list inside each is reversible
into a rail later without changing a single route, which is the property that
makes deferring it safe.

**Group by sub project.** Rejected outright. It is the failure this ADR exists
to prevent, and it would put the word P2 in front of a user.
