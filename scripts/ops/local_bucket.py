"""The local stack's data bucket, made in LocalStack and nowhere else. FEAT-069, TASK-P8-011.

The local API keeps scheduled reports in the bucket `METER_S3_BUCKET` names, which in the local
stack is a LocalStack bucket nobody has made. `make up` runs this inside the api container after
the migration, so the bucket exists before the runner's first look. It makes the bucket once; a
second run finds it and says so.

**Local only, and it refuses first.** It talks to the endpoint `AWS_ENDPOINT_URL` names and
refuses unless that is LocalStack on a local or compose host, so it can never make a bucket in
an AWS account, whatever credentials are in the environment.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Final
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError

from finops_core.config import load_settings

#: Where LocalStack answers: the host, or the compose service from inside the stack.
LOCAL_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1", "localstack"})


def local_endpoint() -> str | None:
    """The configured endpoint when it is LocalStack on a local host, else None."""
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
    return endpoint if (urlsplit(endpoint).hostname or "") in LOCAL_HOSTS else None


#: The one region S3 refuses as a location constraint, because it is the default.
DEFAULT_REGION: Final = "us-east-1"


def ensure(client: Any, bucket: str) -> bool:
    """Make `bucket` unless it exists, in the client's region. True when made, False when found."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        region = client.meta.region_name
        if region in (None, DEFAULT_REGION):
            client.create_bucket(Bucket=bucket)
        else:
            client.create_bucket(
                Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region}
            )
        return True
    return False


def main() -> int:
    endpoint = local_endpoint()
    if endpoint is None:
        print("REFUSED: AWS_ENDPOINT_URL is not LocalStack on a local host, so nothing is made")
        return 2
    settings = load_settings()
    bucket = settings.s3_bucket.strip()
    if not bucket:
        print("OK: METER_S3_BUCKET is empty, so the local stack renders no reports")
        return 0
    # The region is the environment's, AWS_DEFAULT_REGION in the compose file, as for every client.
    client = boto3.client("s3", endpoint_url=endpoint)
    made = ensure(client, bucket)
    print(f"OK: {bucket} {'made' if made else 'already exists'} in LocalStack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
