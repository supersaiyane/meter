# FEAT-093: gp2 to gp3 written as an edit to the file that declares the volume

| Field | Value |
| --- | --- |
| Sub project | P15 |
| Status | Specified |
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

Not built yet. The worker lists the mapped folder's `.tf` files and reads them. `finops_query` finds the one `resource "aws_ebs_volume" "<name>"` block the address from FEAT-057 names, sets `type = "gp3"`, and sets `iops` and `throughput` from FEAT-074's rule where they exceed gp3's included 3,000 IOPS and 125 MiB/s. It is pure text arithmetic, tested on real Terraform without GitHub.

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
