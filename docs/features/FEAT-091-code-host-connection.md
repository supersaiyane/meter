# FEAT-091: The code host connection and the repository mapping

| Field | Value |
| --- | --- |
| Sub project | P15 |
| Status | In build |
| Specification | [P15 spec](../specs/2026-10-15-p15-pull-request-fixes-design.md), sections 5.1, 5.3 and 6 |
| Tasks | TASK-P15-002, TASK-P15-003 and TASK-P15-008 |
| Decisions | OPEN-13, OPEN-42 |
| Issues addressed | ISS-228 |
| Refresh cadence | On change |

## What it does

Connects a GitHub App installation to a tenant, and maps each Terraform state file Meter reads to the repository, base branch and folder whose Terraform wrote it, so a fix goes where its resource is declared.

## Why it exists

FEAT-040 writes a fix and has nowhere to send it, OPEN-13. A fix for a resource belongs in the folder that declares the resource, and only the organization knows which repository that is.

## How it works

Built so far, TASK-P15-002: for each request `finops_providers/github/app.py` signs a token naming the app with its private key, valid for ten minutes, asks GitHub which installation holds the repository, and exchanges the token for an installation token narrowed to that repository and to what the request needs; no token is stored or put in a detail. The key is read from `meter/<env>/codehost/` by `CodeHostKeyReader` when a request is about to be made, a path the hub task role may read and no wider. `finops_providers/github/code_host.py` opens, reads, follows and merges through it, and `make first-contact` lists the installation's repositories, reading only. TASK-P15-003: `code_host_connection` holds the app's id and the Secrets Manager name of its key, never the key, and no installation id, since the installation is found from the repository each time; the API refuses a name outside this environment's code host path, and the database any name outside a code host path. `repository_mapping` holds, per state FEAT-057 reads, the repository, the base branch and the folder, and `GET /v1/remediation/repositories` names the states read with no mapping, whose fixes would have nowhere to go. Both are the organization's: a narrowed reader is answered 404 with the reason, and a change needs a person whose scope is the whole organization, audited ALLOWED or DENIED. Not built yet, TASK-P15-008: the settings screen.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| A person, through the API | On change | Immediate |

## Measured or modelled

Neither: configuration, made by a person and audited.

## Failure behaviour

A resource whose state file has no mapping, or no `resource_management` row, gets no pull request, and the screen says which is missing. A key Meter cannot read is `AccessDenied` on the fix, never a silent skip.

## Security considerations

The app's key is the first write credential Meter holds. Only the worker's task role may read `meter/<env>/codehost/`, a database check holds the stored name to that path, and the connection and the mapping are changed only by a person whose scope is the organization, audited ALLOWED or DENIED.

## Interface

`GET` and `PUT /v1/remediation/connection` and `/v1/remediation/repositories`, and the settings screen.

## Not doing

GitLab or Bitbucket, and a personal access token. The port takes another host when one is asked for.
