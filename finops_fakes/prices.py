"""What the fake estate costs, per resource, per month.

**Every number here is invented.** They are not AWS prices, they are not derived
from a price list, and nothing should ever read them as such. They are roughly
proportional to size so that a ranking ranks and a severity band lands somewhere
plausible, and roughly in the shape of a real bill so a demo reads as one.

This module exists because the bill and the estate had nothing to join on.
`DATA_DICTIONARY.md` decision 6 states the problem: `cur.py` billed one EC2 and one
RDS resource per account, the estate has 36 resources, and only two of them
appeared in both. So the realized savings collector could not find a charge for the
resource a recommendation was about, and TASK-P3-013 worked around it by seeding
three resources with hand written charges.

**One price list, read by two callers.** `cur.py` prices each daily bill line from
it and `estate_metrics.py` prices the saving estimate from it. Two lists would
drift, and then the estimated saving and the realized saving would disagree for a
reason that is an artefact of the fixture rather than a fact about the estate, which
is the one thing FEAT-029 must not be confused by.

Prices are per month and are divided by thirty at the point of use. A month is
thirty days here whatever the calendar says, because a bill line that changed size
in February would make a trend nobody can read.
"""

from __future__ import annotations

from decimal import Decimal

from finops_fakes.utilization import Spec

#: Dollars per month, by EC2 instance type. Shared with the sizing estimate, so a
#: rightsizing saving and the bill line it is about come from the same number.
INSTANCE_USD: dict[str, Decimal] = {
    "t3.micro": Decimal("7.60"),
    "t3.small": Decimal("15.20"),
    "t3.medium": Decimal("30.40"),
    "t3.large": Decimal("60.80"),
    "m5.large": Decimal("70.10"),
    "m5.xlarge": Decimal("140.20"),
    "m5.2xlarge": Decimal("280.40"),
    "m5.4xlarge": Decimal("560.80"),
    "m6g.xlarge": Decimal("112.20"),
    "m6i.large": Decimal("73.00"),
    "m6i.xlarge": Decimal("146.00"),
    "m6i.2xlarge": Decimal("292.00"),
    "m6i.4xlarge": Decimal("584.00"),
    "c5.2xlarge": Decimal("248.20"),
    "c5.4xlarge": Decimal("496.40"),
    "c6i.2xlarge": Decimal("248.20"),
    "c6i.4xlarge": Decimal("496.40"),
    "r5.xlarge": Decimal("183.90"),
    "r5.2xlarge": Decimal("367.80"),
    "r6i.xlarge": Decimal("191.60"),
    "g4dn.xlarge": Decimal("384.20"),
}

#: Dollars per month, by RDS instance class.
DATABASE_USD: dict[str, Decimal] = {
    "db.t4g.medium": Decimal("48.00"),
    "db.m6g.large": Decimal("124.00"),
    "db.m6g.xlarge": Decimal("248.00"),
    "db.r6g.large": Decimal("172.00"),
    "db.r6g.xlarge": Decimal("344.00"),
    "db.r6g.2xlarge": Decimal("688.00"),
}

#: Dollars per month, by ElastiCache node type, per node.
CACHE_NODE_USD: dict[str, Decimal] = {
    "cache.t4g.micro": Decimal("12.00"),
    "cache.t4g.small": Decimal("24.00"),
    "cache.r6g.large": Decimal("148.00"),
    "cache.r6g.xlarge": Decimal("296.00"),
}

#: Dollars per month, by MSK broker instance type, per broker.
BROKER_USD: dict[str, Decimal] = {
    "kafka.m5.large": Decimal("158.00"),
    "kafka.m5.xlarge": Decimal("316.00"),
}

#: Dollars per GiB per month, by EBS volume type. gp2 above gp3 on purpose: the gp2
#: to gp3 migration is a planted finding and it has to actually save money.
VOLUME_USD_PER_GIB: dict[str, Decimal] = {
    "gp2": Decimal("0.10"),
    "gp3": Decimal("0.08"),
    "io2": Decimal("0.125"),
}

#: Dollars per GiB per month for a snapshot. Cheaper than the volume it came from,
#: which is why an orphaned snapshot is a small finding rather than a large one.
SNAPSHOT_USD_PER_GIB = Decimal("0.05")

#: Stored logs, and logs arriving. Ingest dominates, which is why FEAT-027's
#: retention finding is about what arrives rather than about what is kept.
LOG_STORED_USD_PER_GIB = Decimal("0.03")
LOG_INGEST_USD_PER_GIB = Decimal("0.50")

#: A NAT gateway: the hourly charge, plus what it moves.
NAT_HOURLY_USD = Decimal("0.045")
NAT_USD_PER_GIB = Decimal("0.045")

#: A load balancer: the hourly charge, plus a request charge standing in for the
#: real capacity unit charge, which is a function of four dimensions nobody here is
#: modelling.
ALB_HOURLY_USD = Decimal("0.0225")
ALB_USD_PER_MILLION_REQUESTS = Decimal("0.60")

#: An unassociated Elastic IP. The charge exists because it is unassociated, which
#: is what makes it a finding at all.
EIP_MONTHLY_USD = Decimal("3.60")

#: An alarm, and a custom metric. Small, and small is the point: the FEAT-027
#: findings about them are about how many there are, not what one costs.
ALARM_MONTHLY_USD = Decimal("0.10")
CUSTOM_METRIC_MONTHLY_USD = Decimal("0.30")

#: Hours and days in the month these prices describe. Thirty days whatever the
#: calendar says, because a bill line that changed size in February makes a trend
#: nobody can read.
HOURS_PER_MONTH = Decimal("720")
DAYS_PER_MONTH = Decimal("30")

#: What a resource nobody priced costs. Deliberately small, so a kind added to the
#: estate without a price here produces a finding nobody acts on rather than a
#: headline nobody checked. A test asserts every estate resource is priced, which is
#: what stops one staying unpriced.
UNPRICED = Decimal("5.00")


def _number(spec: Spec, key: str, default: Decimal = Decimal("0")) -> Decimal:
    value = spec.config.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return Decimal(str(value))


def _text(spec: Spec, key: str) -> str:
    value = spec.config.get(key)
    return value if isinstance(value, str) else ""


def _compute(spec: Spec) -> Decimal:
    price = INSTANCE_USD.get(_text(spec, "instance_type"), UNPRICED)
    if spec.kind == "instance":
        return price
    # A group bills for the instances it is actually running, and `base_nodes` is
    # what it sits at when nothing is happening. The scaling shows up in the metrics
    # rather than here, because a bill line moving with the group's size would make
    # every trend a scaling event.
    return price * (_number(spec, "base_nodes") or _number(spec, "min_size", Decimal("1")))


def _database(spec: Spec) -> Decimal:
    price = DATABASE_USD.get(_text(spec, "instance_class"), UNPRICED)
    storage = _number(spec, "storage_gib") * VOLUME_USD_PER_GIB["gp3"]
    # Multi AZ doubles both, which is the one real pricing rule kept here: a
    # rightsizing on a multi AZ database saves twice what it appears to.
    multiplier = Decimal("2") if spec.config.get("multi_az") else Decimal("1")
    return (price + storage) * multiplier


def _log_group(spec: Spec) -> Decimal:
    stored = _number(spec, "stored_gib") * LOG_STORED_USD_PER_GIB
    arriving = (
        _number(spec, "mib_per_hour") / Decimal("1024") * HOURS_PER_MONTH * LOG_INGEST_USD_PER_GIB
    )
    return stored + arriving


def _load_balancer(spec: Spec) -> Decimal:
    requests = (
        _number(spec, "requests_per_hour")
        * HOURS_PER_MONTH
        / Decimal("1000000")
        * ALB_USD_PER_MILLION_REQUESTS
    )
    return ALB_HOURLY_USD * HOURS_PER_MONTH + requests


def monthly_usd(spec: Spec) -> Decimal:
    """What one estate resource costs per month. Invented, see the module docstring.

    Derived from the configuration the estate already carries rather than written
    down per resource, so a resource whose size changes changes its bill and a
    resource added to the estate is priced by what it is.
    """
    if spec.kind in ("instance", "asg", "asg_eks"):
        return _compute(spec)
    if spec.kind == "rds":
        return _database(spec)
    if spec.kind == "cache":
        node = CACHE_NODE_USD.get(_text(spec, "node_type"), UNPRICED)
        return node * _number(spec, "nodes", Decimal("1"))
    if spec.kind == "msk":
        broker = BROKER_USD.get(_text(spec, "broker_instance_type"), UNPRICED)
        storage = _number(spec, "storage_gib_per_broker") * VOLUME_USD_PER_GIB["gp3"]
        return (broker + storage) * _number(spec, "brokers", Decimal("1"))
    if spec.kind == "volume":
        per_gib = VOLUME_USD_PER_GIB.get(_text(spec, "volume_type"), VOLUME_USD_PER_GIB["gp3"])
        return _number(spec, "size_gib") * per_gib
    if spec.kind == "snapshot":
        return _number(spec, "size_gib") * SNAPSHOT_USD_PER_GIB
    if spec.kind == "log_group":
        return _log_group(spec)
    if spec.kind == "nat":
        moved = _number(spec, "gib_per_hour") * HOURS_PER_MONTH * NAT_USD_PER_GIB
        return NAT_HOURLY_USD * HOURS_PER_MONTH + moved
    if spec.kind == "alb":
        return _load_balancer(spec)
    if spec.kind == "eip":
        return EIP_MONTHLY_USD
    if spec.kind == "alarm":
        return ALARM_MONTHLY_USD
    if spec.kind == "custom_metric":
        return CUSTOM_METRIC_MONTHLY_USD
    return UNPRICED


def daily_usd(spec: Spec) -> Decimal:
    """One day of `monthly_usd`, at four decimal places like every other figure."""
    return (monthly_usd(spec) / DAYS_PER_MONTH).quantize(Decimal("0.0001"))
