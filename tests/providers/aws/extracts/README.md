# Real AWS extracts

Pruned copies of what AWS publishes, so fakes and adapters are shaped by real data rather than
by memory of it. TASK-P9-002, P9 spec sections 5.3 and 5.4. Each is AWS's own, unedited except
that everything but one product was removed.

| File | Source | Read |
| --- | --- | --- |
| `elasticache-eu-west-1-cache-m5-large.json` | The AWS price list, `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonElastiCache/current/eu-west-1/index.json`, version 20260914063714, published 2026-09-14T06:37:14Z. Product `RPVSXBK67RKQZAHJ`, `cache.m5.large` running Valkey, with its on demand term and its six reserved terms | 2026-10-08 |
| `elasticache-eu-west-1-extended-support.json` | The same file: product `WFGK6RZEMVUFK7WG`, `cache.m5.xlarge` Extended Support, year three, an hourly surcharge rather than a node price | 2026-10-08 |
| `get-products-ec2-ebs-io1.json` | The sample response in the AWS Price List API reference for `GetProducts`, `https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_pricing_GetProducts.html`: a real EC2 product, an io1 volume in Canada (Central), version 20170901182201 | 2026-10-08 |
| `list-price-lists-ec2.json` | The sample response in the same reference for `ListPriceLists`, `https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_pricing_ListPriceLists.html` | 2026-10-08 |
| `describe-instance-types-t2-micro.json` | The example output in the AWS CLI reference for `describe-instance-types`, `https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instance-types.html` | 2026-10-08 |

What the price list taught that the specification had not said: an All Upfront reservation's
hourly price is exactly nought beside its upfront fee, so a nought is refused only when every
price in a term is nought; and the list carries Extended Support products beside the ordinary
ones, which TASK-P9-004's filter must name.

What the API reference taught, TASK-P9-004: `GetProducts` keys a product's terms by SKU and term,
`terms.OnDemand["SKU.TERM"]`, where the offer file nests them under the SKU first, so one parser
cannot read both without knowing which it has; a price list's version is the second last segment
of its ARN; and the version is the publication time, `20170901182201` for `2017-09-01T18:22:01Z`,
as the ElastiCache file's own pair confirms. The ElastiCache file measured 506 products and 1,850
terms in one service and Region, 146 of the products Extended Support surcharges.
