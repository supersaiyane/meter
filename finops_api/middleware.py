"""Request scoped identity for logs, so a failure can be traced to a request.

Every line this application logs carries the request id, and the same id goes
into every `audit_event` the request writes and comes back on the response. That
is what turns "a user says a number looked wrong" into a query rather than an
afternoon.

The id is taken from the incoming header when there is one, so a trace that
started at the load balancer or in the frontend is not broken here.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from finops_api.deps import REQUEST_ID_HEADER

LOGGER = logging.getLogger("meter.api.request")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Give every request an id, log it, and hand it back on the response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        fields = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        LOGGER.info("request started", extra=fields)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        LOGGER.info("request finished", extra={**fields, "status": response.status_code})
        return response
