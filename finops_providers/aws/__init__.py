"""The AWS adapter. The only package in this project that imports boto3.

Constraint 1 in CLAUDE.md, proved by `lint-imports` on every build: nothing in
`finops_core` reaches a cloud SDK, so a second provider is a sibling of this
package rather than a rewrite of everything above it.
"""

from finops_providers.aws.accounts import AwsAccountDiscovery
from finops_providers.aws.credentials import AwsCredentialBroker, AwsSession

__all__ = ["AwsAccountDiscovery", "AwsCredentialBroker", "AwsSession"]
