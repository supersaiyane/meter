# FEAT-093: gp2 to gp3 written as an edit to the file that declares the volume

| Field | Value |
| --- | --- |
| Sub project | P15 |
| Status | In build |
| Specification | [P15 spec](../specs/2026-10-15-p15-pull-request-fixes-design.md), section 5.4 |
| Tasks | TASK-P15-005 |
| Decisions | OPEN-43 |
| Issues addressed | ISS-228 |
| Refresh cadence | When a fix is asked for |

## What it does

Writes FEAT-074's gp2 to gp3 recommendation as a change to the Terraform that declares the volume: its type set to gp3, and its IOPS and throughput set where the volume needs more than gp3 includes.

## Why it exists

FEAT-040 writes only deletions, because a change needs the value it sets and the file it sets it in, and nothing read either, ISS-228. gp2 to gp3 is the first fix that loses nothing if it is wrong, which is what makes it the first a policy may let Meter merge, FEAT-094.

## How it works

Built, TASK-P15-005. The `fix_pull_requests` collector reads the mapped folder's `.tf` files through the code host, and `finops_query/gp3_edit.py` finds the one `resource "aws_ebs_volume" "<name>"` block the address from FEAT-057 names, sets `type = "gp3"`, and sets `iops` and `throughput` where the gp3 FEAT-074 priced gives more than gp3 includes. Those two figures are kept on the recommendation since migration 0061, `target_iops` and `target_throughput_mibps`, written by the volume pass, because they were before only in the rationale's sentence. Strings, comments and heredocs are skipped when reading, a line the edit adds joins its run of attributes aligned as `terraform fmt` aligns it where the file already was, and the edit refuses, with the reason, an instance key, a module's resource, a block in no file or in several, one written on one line, a type, IOPS or throughput set by anything but a literal, a block already gp3, an IOPS or throughput gp3 would not need, and a recommendation that records no figures. The pull request says the change is reversible, and that Meter merges it only under the tenant's merge policy, ADR-0038.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The mapped folder, through the app | When a fix is asked for | The repository's base branch at that moment |
| FEAT-074's recommendation | As the waste collector runs | Its own freshness |

## Measured or modelled

The IOPS and throughput set are FEAT-074's, from the volume's measured use, and say so in the body. The saving is modelled until FEAT-029 measures it.

## Failure behaviour

Refused, with the reason, rather than guessed: a type set by a variable or an expression, a resource inside a module, an address with an instance key, a block found in no file or in more than one, and a volume FEAT-074 says gp3 cannot match.

## Security considerations

Reads the mapped folder only, through the app's read permission on contents.

## Interface

Through FEAT-092: the edit is the fix a gp2 to gp3 recommendation opens.

## Not doing

Resizing an instance or any other attribute, OPEN-43. A type set inside a module is refused rather than edited.
