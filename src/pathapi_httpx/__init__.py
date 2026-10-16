"""The `httpx` HTTP transports for `pathapi.http`.

Installing this distribution is enough: `pathapi.http` finds `HttpxTransport`
through the `httpx` entry of its `pathapi.http_transports` group and
`AsyncHttpxTransport` through the `httpx` entry of `pathapi.http_async_transports`,
so `HTTPClient(HttpxTransport())`, `AsyncHTTPClient(AsyncHttpxTransport())`,
`PATHAPI_HTTP_TRANSPORT=httpx` and `PATHAPI_HTTP_ASYNC_TRANSPORT=httpx` send
through them. `httpx` is imported when a transport is built, not when this
package is.
"""

from __future__ import annotations

from ._async import AsyncHttpxTransport
from ._sync import HttpxTransport
from ._version import __version__

__all__ = ["AsyncHttpxTransport", "HttpxTransport", "__version__"]
