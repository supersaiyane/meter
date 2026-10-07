"""A boto3 client in shape, for the services the hub reaches only through the relay.

TASK-P9-001, ADR-0035. The relay runs outside the VPC and answers through S3; this is the hub's
side of it. An adapter is handed one of these where it would have been handed a boto3 client,
and calls it the same way, `client.describe_budgets(...)` or
`client.get_paginator("describe_budgets").paginate(...)`, so `AwsBudgets`, `AwsInvoices` and the
Support reads need no second implementation for the path their calls take.

**A refusal arrives as the ClientError it was.** The relay returns AWS's own code and message,
and they are raised here as a `ClientError`, so the adapter's own `translate` names the cause
exactly as it would for a direct call. A relay that could not reach AWS, or failed itself, is
raised with a code `translate` does not know, which is SchemaDrift: loud, and never a zero.

What builds one of these in production waits on the collector registry nothing assembles yet,
ISS-182, as every other adapter's wiring does.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from functools import cache
from typing import Any

import botocore.session
from botocore import xform_name
from botocore.exceptions import ClientError

from finops_relay.relay import decode

Invoke = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Fetch = Callable[[str], bytes]


@cache
def _operations(service: str) -> dict[str, str]:
    """Each operation's method name, to its API name, from the model boto3 builds clients from."""
    model = botocore.session.get_session().get_service_model(service)
    return {xform_name(name): name for name in model.operation_names}


class RelayClient:
    """One service, in one Region, about one account, reached through the relay."""

    def __init__(
        self,
        *,
        service: str,
        region: str,
        account_id: str | None,
        invoke: Invoke,
        fetch: Fetch,
    ) -> None:
        self._service = service
        self._region = region
        self._account_id = account_id
        self._invoke = invoke
        self._fetch = fetch

    def get_paginator(self, method: str) -> _Paginator:
        return _Paginator(self, method)

    def __getattr__(self, method: str) -> Callable[..., Any]:
        if method.startswith("_"):
            raise AttributeError(method)

        def one_call(**params: Any) -> Any:
            return self._pages(method, params, paginate=False)[0]

        return one_call

    def _pages(self, method: str, params: Mapping[str, Any], *, paginate: bool) -> list[Any]:
        operation = _operations(self._service).get(method)
        if operation is None:
            raise AttributeError(f"{self._service} has no operation {method}")
        answer = self._invoke(
            {
                "service": self._service,
                "operation": operation,
                "params": dict(params),
                "region": self._region,
                "account_id": self._account_id,
                "paginate": paginate,
            }
        )
        error = answer.get("error")
        if error is not None:
            raise ClientError({"Error": dict(error)}, operation)
        return decode(self._fetch(str(answer["key"])))


class _Paginator:
    def __init__(self, client: RelayClient, method: str) -> None:
        self._client = client
        self._method = method

    def paginate(self, **params: Any) -> Iterator[Any]:
        yield from self._client._pages(self._method, params, paginate=True)


def lambda_invoke(client: Any, function_name: str) -> Invoke:
    """The relay invoked through the Lambda endpoint. A function error is the relay failing."""

    def invoke(event: Mapping[str, Any]) -> Mapping[str, Any]:
        response = client.invoke(FunctionName=function_name, Payload=json.dumps(event).encode())
        body = json.loads(response["Payload"].read())
        if response.get("FunctionError"):
            return {"error": {"Code": "RelayFailed", "Message": str(body)[:500]}}
        answer: Mapping[str, Any] = body
        return answer

    return invoke


def s3_fetch(client: Any, bucket: str) -> Fetch:
    """An answer read back through the S3 gateway endpoint."""

    def fetch(key: str) -> bytes:
        body: bytes = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return body

    return fetch
