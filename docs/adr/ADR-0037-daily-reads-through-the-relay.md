# ADR-0037: A read made once a day may go through the relay where an endpoint exists

Date: 2026-10-13
Status: Accepted. The owner chose the path on 2026-10-13, OPEN-39, for P14
Supersedes: nothing. It amends ADR-0035's rule, an endpoint for every service that has one

## Context

ADR-0035 reaches every AWS service the hub calls through an interface endpoint where the service
has one, and through the relay, a Lambda function outside the VPC, only where it has none. P14
reads the commitments each member account holds, every day: Savings Plans, which have no endpoint,
and reservations for EC2, RDS, ElastiCache, OpenSearch, Redshift and MemoryDB, which do. The hub
already pays for an EC2 endpoint in each collection Region. The other five do not exist, and the
rule would add one for each in both collection Regions, ten endpoints, for one describe call per
account and Region per service per day.

## Decision

1. A read may go through the relay, even where its service has an interface endpoint, when it is
   made once a day or less, is read only, and is allow listed in the relay with its one IAM action
   and the role it is made as, as every relay call already is.
2. P14's reservation reads for RDS, ElastiCache, OpenSearch, Redshift and MemoryDB, and its
   Savings Plans read, go through the relay as the member account's collector role. EC2
   reservations use the EC2 endpoint the hub already has.
3. Any read made more often than daily still takes an endpoint, so the relay does not become the
   default path for the hub's traffic.

## Cost

Modelled, from ADR-0035's figure of USD 16.06 a month per endpoint at the hub's Region's list
price: ten endpoints, five services in two collection Regions, about USD 160.60 a month. Through
the relay, the same reads are a few hundred Lambda invocations a month, each a fraction of a second,
about a cent a month at Lambda's list price, before the S3 requests the answers travel through,
which add a similar amount.

## Alternatives

- **The endpoints, keeping the rule.** About USD 160.60 a month for reads made once a day.
  Rejected by the owner on cost.
- **Cost Explorer's reservation reports alone.** They give use and coverage, not each reservation's
  term and end, which is the gap P14 exists to close. Rejected.

## Consequences

- The relay's allow list grows by six calls, each held by `tests/contract/test_network_paths.py`
  and by the relay's IAM policy in the hub stack, as every relay call is.
- A relayed read is slower than an endpoint read by the Lambda invocation and an S3 round trip,
  which a daily collector does not notice.
- Nothing here has been applied. The first apply waits on an AWS account, ISS-002.
