"""Scheduled report files in the hub's data bucket. FEAT-069, TASK-P8-011.

The `ReportStore` adapter. Every file a schedule renders is written under the tenant's prefix by
the runner, and read back by the route that hands it to its recipient after checking their scope
again. The bucket's own default encryption and public access block apply, so nothing is set per
object beyond the type.

A key with nothing under it is NoData, which the port promises, rather than the SchemaDrift the
general translation would make of S3's `NoSuchKey`: the run record names a file that is gone,
and saying so is more use than calling it a change in the API.
"""

from __future__ import annotations

from typing import Any, Final

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.errors import NoData
from finops_providers.aws.client import botocore_config, error_code, translate

COLLECTOR: Final = "report_store"
SERVICE: Final = "s3"
#: What S3 says when a key holds nothing.
MISSING_KEY_CODES: Final = frozenset({"NoSuchKey", "404"})


class S3ReportStore:
    """Report files in one bucket, one object per file."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ReportStore:
        """The store the API writes to: the data bucket the hub stack names."""
        return cls(boto3.client(SERVICE, config=botocore_config(settings)), settings.s3_bucket)

    def put(self, key: str, body: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=body, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as failure:
            raise translate(failure, scope_key=self._where(key), collector=COLLECTOR) from failure

    def get(self, key: str) -> bytes:
        try:
            answer = self._client.get_object(Bucket=self._bucket, Key=key)
            body: bytes = answer["Body"].read()
        except ClientError as failure:
            if error_code(failure) in MISSING_KEY_CODES:
                raise NoData(
                    scope_key=self._where(key),
                    collector=COLLECTOR,
                    detail="the run names a file that is not in the bucket",
                ) from failure
            raise translate(failure, scope_key=self._where(key), collector=COLLECTOR) from failure
        except BotoCoreError as failure:
            raise translate(failure, scope_key=self._where(key), collector=COLLECTOR) from failure
        return body

    def _where(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"
