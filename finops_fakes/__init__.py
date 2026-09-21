"""The in memory provider. No cloud account, no network, no clock.

Every core and API test runs against this, which is why it implements all eight
provider ports rather than the two P0 uses. See `finops_fakes.provider` for the
failure plan, which is the part that matters.
"""

from finops_fakes.provider import FakeProvider, FakeSession

__all__ = ["FakeProvider", "FakeSession"]
