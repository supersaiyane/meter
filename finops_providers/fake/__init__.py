"""The in memory provider. No cloud account, no network, no clock.

Every core and API test runs against this, which is why it implements all eight
ports rather than the two P0 uses. See `finops_providers.fake.provider` for the
failure plan, which is the part that matters.
"""

from finops_providers.fake.provider import FakeProvider, FakeSession

__all__ = ["FakeProvider", "FakeSession"]
