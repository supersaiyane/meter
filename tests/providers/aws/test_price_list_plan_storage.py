"""The storage a planned database or search domain is priced from. TASK-P16-004, FEAT-095.

Held to AWS's own eu-west-1 price lists, pruned to the products in `extracts`: RDS for
PostgreSQL and Aurora PostgreSQL, Redshift's ra3.xlplus, and OpenSearch's r6g.large with its EBS
storage. Each family the adapter now keeps is kept for its own service only.
"""

from __future__ import annotations

import json
from decimal import Decimal

from finops_core.domain.catalog import Price
from tests.providers.aws.real_prices import offer_items as items
from tests.providers.aws.real_prices import prices_of


def read(service: str, version: str, products: list[str]) -> dict[str, Price]:
    return {
        price.sku_price_id.split(".")[0]: price for price in prices_of(service, version, products)
    }


def test_rds_storage_iops_and_throughput_are_kept_beside_its_instances() -> None:
    offer, products = items("rds-eu-west-1-postgresql-and-aurora.json")
    prices = read("AmazonRDS", offer["version"], products)
    assert len(prices) == 13
    gp3 = prices["S32D6FQC3879C222"]
    assert (gp3.pricing_unit, gp3.recurring_unit_price) == ("GB-Mo", Decimal("0.127"))
    assert gp3.details["volumeType"] == "General Purpose-GP3"
    assert (gp3.details["databaseEngine"], gp3.details["deploymentOption"]) == (
        "PostgreSQL",
        "Single-AZ",
    )
    iops_rows = ("V4N9K7GFJC4BVRHM", "D5Y98VF5R9USR7EB", "CDJD9T62N8GKES69")
    groups = {prices[sku].details.get("groupDescription") for sku in iops_rows}
    assert groups == {
        "RDS Provisioned IOPS",
        "RDS Provisioned GP3 IOPS",
        "RDS Provisioned IO2 IOPS",
    }
    assert prices["3RJ2QZU3S9BTETUC"].pricing_unit == "MBPS-Mo"
    aurora = {prices[sku].details["storage"] for sku in ("EQQGP475ZHNCR63P", "E4WZ2S9A9AVWRJNM")}
    assert aurora == {"EBS Only", "Aurora IO Optimization Mode"}


def test_opensearch_ebs_storage_is_kept_and_its_vector_storage_is_not() -> None:
    offer, products = items("opensearch-eu-west-1-r6g-large-and-storage.json")
    vector = json.loads(products[0])
    vector["product"]["sku"] = "VECTORSVECTORS01"
    vector["product"]["attributes"]["storageMedia"] = "OpenSearch-Vectors-Put-Bytes"
    vector["terms"] = {
        "OnDemand": {
            "VECTORSVECTORS01.JRTCKXETXF": {
                **next(iter(vector["terms"]["OnDemand"].values())),
                "sku": "VECTORSVECTORS01",
            }
        }
    }
    prices = read("AmazonES", offer["version"], [*products, json.dumps(vector)])
    assert "VECTORSVECTORS01" not in prices
    media = sorted(str(one.details.get("storageMedia")) for one in prices.values())
    assert media == sorted(
        [
            "None",
            "GP3",
            "GP3-PIOPS-Storage",
            "GP3-ThroughPut-Storage",
            "GP2",
            "PIOPS-Storage",
            "PIOPS",
            "Magnetic",
        ]
    )
    assert prices["87RMRM8TXMEJH9CW"].details["instanceType"] == "r6g.large.search"


def test_a_redshift_node_and_its_managed_storage_share_the_type_and_differ_by_unit() -> None:
    offer, products = items("redshift-eu-west-1-ra3-xlplus.json")
    prices = read("AmazonRedshift", offer["version"], products)
    units = {sku: (one.pricing_unit, one.recurring_unit_price) for sku, one in prices.items()}
    assert units == {
        "KWKY3TB2FN5GW9K5": ("Hrs", Decimal("1.202")),
        "SGTJP7TQ9WH5KRDD": ("GB-Mo", Decimal("0.024")),
    }


def test_a_family_kept_for_one_service_is_not_kept_for_another() -> None:
    offer, products = items("rds-eu-west-1-postgresql-and-aurora.json")
    storage = [one for one in products if "Database Storage" in one]
    assert storage
    assert read("AmazonElastiCache", offer["version"], storage) == {}
