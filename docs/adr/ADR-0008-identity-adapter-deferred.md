# ADR-0008: Identity adapter deferred and isolated behind two ports

Date: 2026-08-23
Status: Accepted

## Context

Authentication was raised as a requirement: ADFS based, working the way
saml2aws does, with one credential able to see every account. On 2026-08-23
the decision was parked pending further understanding of the environment. See
`tasks/ISSUES.md`, OPEN-01.

Blocking P0 on an unresolved identity decision would stall the entire project,
because everything else depends on P0.

## Decision

Define two ports in `finops-core` and build P0 against them.

```python
IdentityProvider.authenticate(request) -> Principal
EntitlementResolver.resolve(principal)  -> Scope{account_ids, ou_ids, tier, is_global}
```

P0 ships a `LocalConfigIdentityProvider` reading users, accounts and tiers from
a YAML file, hard gated to non production by configuration. The SAML adapter
is implemented later behind the same two interfaces.

Scope is enforced in two places, a request dependency and a repository guard,
so a route that omits the dependency still cannot read out of scope data.

## Consequences

Positive.

- P0 proceeds now. The identity decision changes one adapter, not the data
  model, the API surface, or the frontend.
- The local provider makes development and testing work with no identity
  provider available at all.

Negative.

- The local provider is a production risk if the configuration gate ever
  fails. Mitigated by refusing to start when the environment is production and
  the local provider is selected, and by an integration test that asserts this.
- The eventual SAML design may reveal a requirement, for example per request
  role assumption, that the current port shape does not express cleanly. The
  ports will be revised at that point rather than guessed at now.

## Recorded intent for the eventual adapter

The direction indicated on 2026-08-23 is to use the ADFS SAML assertion as the
source of truth. Its AWS role claim is multi valued, carrying one entry per
account and role the user is entitled to, which is the same list saml2aws
presents as an account picker. That entitlement list becomes the visibility
scope directly, so there is no separate permission table to drift out of sync
with Active Directory.

Three properties the eventual design must preserve.

1. Aggregate reads use the entitlement list as a row level filter. Live drill
   down uses `AssumeRoleWithSAML` into the user's own role, so the call carries
   their identity into CloudTrail.
2. The role name maps to a permission tier. A read only role and an
   administrator role must not grant the same thing inside Meter.
3. Coverage is stated, never implied. The entitlement list only contains
   accounts where a federated role exists, so log archive, shared services and
   newly vended accounts are commonly absent. The interface must say "you can
   see N of M accounts" rather than presenting a partial total as an
   organization total.
