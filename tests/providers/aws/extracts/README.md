# Real AWS extracts

Pruned copies of what AWS publishes, so fakes and adapters are shaped by real data rather than
by memory of it. TASK-P9-002, P9 spec sections 5.3 and 5.4. Each is AWS's own, unedited except
that everything but one product was removed.

| File | Source | Read |
| --- | --- | --- |
| `elasticache-eu-west-1-cache-m5-large.json` | The AWS price list, `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonElastiCache/current/eu-west-1/index.json`, version 20260914063714, published 2026-09-14T06:37:14Z. Product `RPVSXBK67RKQZAHJ`, `cache.m5.large` running Valkey, with its on demand term and its six reserved terms | 2026-10-08 |
| `describe-instance-types-t2-micro.json` | The example output in the AWS CLI reference for `describe-instance-types`, `https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instance-types.html` | 2026-10-08 |

What the price list taught that the specification had not said: an All Upfront reservation's
hourly price is exactly nought beside its upfront fee, so a nought is refused only when every
price in a term is nought; and the list carries Extended Support products beside the ordinary
ones, which TASK-P9-004's filter must name.
