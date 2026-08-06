# Context index

Function level index. Name, file and line, purpose, and callers.

Last updated: 2026-08-23
Update trigger: any new or removed public function or class.

## Current state

No application code exists yet. This file is created now so that the update
habit starts with the first commit of code rather than being retrofitted.

## Format

Each entry follows this shape.

```
### <module>

| Symbol | File and line | Purpose | Called by |
| --- | --- | --- | --- |
```

## Index

Empty. The first entries will be added with the `finops-core` domain and ports
commit.

## Reference: the eight ports, once implemented

Recorded here in advance because every other module depends on their shape.
Signatures are indicative and will be replaced with real file and line
references when the code lands.

| Port | Purpose |
| --- | --- |
| `AccountDiscovery` | Enumerate accounts and the organization tree |
| `CredentialBroker` | Produce a scoped session for a target account |
| `CostExport` | Locate and read billing data |
| `MetricSource` | Read time series for a resource |
| `ResourceInventory` | Enumerate resources and their relationships |
| `QuotaSource` | Read limits and current usage |
| `IdentityProvider` | Authenticate a request into a principal |
| `EntitlementResolver` | Resolve a principal into a visibility scope |
