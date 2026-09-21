"""How much history a judgement needs before it is allowed to be made.

One constant, in the domain, because two features already depend on it and they
must not drift.

`finops_query.anomaly` refuses to judge a day against fewer than this many days of
baseline. `finops_core.domain.waste` refuses to construct a recommendation resting
on fewer. Those are the same rule about the same thing, and the day they disagree
is the day one screen calls an estate too young to judge while another recommends
terminating its instances.

It lives here rather than in `finops_query` because the layer contract runs
`finops_query > finops_providers > finops_core`: the domain cannot import upward,
and this is a fact about what the domain will vouch for rather than a detail of any
particular arithmetic.
"""

from __future__ import annotations

#: Days of history a pair or a resource needs before any verdict is given.
#:
#: Fourteen is two full weekly cycles. Below it a new account looks exactly like an
#: anomaly and a new instance looks exactly like an idle one, and a product that
#: reports either teaches the reader to ignore the screen.
#:
#: It is a floor, not a target. Fourteen days of data is enough to say something
#: and not enough to say it confidently, which is why `Confidence` is a separate
#: figure that keeps rising well past this line.
MINIMUM_HISTORY = 14
