"""What the synchronous and the asynchronous transport share: the request as
`httpx` is given it, the reply as `pathapi.http` is given it, and the errors."""

from __future__ import annotations

import errno as _errno
import ssl as _ssl
import urllib.parse as _urlparse

from pathapi.http import PreparedRequest

CHUNK = 64 * 1024
"""Most bytes of a request body read in one call."""

MAX_HEADERS = 100
"""Most header fields of a reply a transport accepts, as the built-in one."""

_DEFAULT_PORTS = {"http": 80, "https": 443}


def import_httpx():
    try:
        import httpx
    except ImportError as error:
        raise ImportError(
            "httpx could not be imported; reinstall pathapi-httpx", name="httpx"
        ) from error
    return httpx


def origin(url: str) -> "tuple[str, str, int | None]":
    """The scheme, host and port a URL names."""
    parts = _urlparse.urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        port = -1
    return scheme, (parts.hostname or "").lower(), port or _DEFAULT_PORTS.get(scheme)


class OnlyThis:
    """Authentication that adds nothing of its own. A client's `auth` belongs to
    the server of the first request; a request to any other carries the
    `Authorization` it was given or none."""

    def __init__(self, authorization: "str | None"):
        self._authorization = authorization

    def __call__(self, request):
        request.headers.pop("Authorization", None)
        if self._authorization is not None:
            request.headers["Authorization"] = self._authorization
        return request


class Pin:
    """The origin of the first request a transport sends."""

    def __init__(self) -> None:
        self._origin: "tuple | None" = None

    def auth(self, prepared: PreparedRequest, default):
        """`default` (the client's own `auth`) for the first server; for any
        other, an object that sends only the `Authorization` of the request."""
        here = origin(prepared.url)
        if self._origin is None:
            self._origin = here
        if self._origin == here:
            return default
        given = next(
            (v for k, v in prepared.headers.items() if k.lower() == "authorization"),
            None,
        )
        return OnlyThis(given)


def build_request(httpx, prepared: PreparedRequest, content):
    """The `httpx.Request` for `prepared`: exactly its headers, none of a
    client's defaults, with its `(connect, read)` timeout."""
    connect, read = prepared.timeout
    timeout = httpx.Timeout(connect=connect, read=read, write=read, pool=connect)
    try:
        return httpx.Request(
            prepared.method,
            prepared.url,
            headers=prepared.headers,
            content=content,
            extensions={"timeout": timeout.as_dict()},
        )
    except httpx.InvalidURL:
        raise ValueError("the request URL is not valid") from None


_OWNED: "dict[type, type]" = {}


def owned_client(base: type) -> type:
    """`base` (`httpx.Client` or `httpx.AsyncClient`) as a client that does not
    read the `Location` of a redirect it will not follow: `httpx` otherwise
    fails a reply whose `Location` it cannot parse, where the caller of a
    transport is to be given that reply."""
    made = _OWNED.get(base)
    if made is None:

        class Client(base):  # type: ignore[valid-type, misc]
            def _build_redirect_request(self, request, response):
                return request

        made = _OWNED[base] = Client
    return made


def requested_url(request) -> str:
    """The URL a request went to, as `HTTPResponse.url` states it: no fragment,
    `/` for an empty path."""
    url = request.url
    return f"{url.scheme}://{url.netloc.decode('ascii')}{url.raw_path.decode('ascii')}"


def read_already(response) -> "bytes | None":
    """The body of a response that `httpx` has read whole and decoded (one a
    mounted `httpx.MockTransport` made), else `None`."""
    return response.content if response.is_stream_consumed else None


def header_pairs(response) -> "list[tuple[str, str]]":
    """The headers of `response` as received, a name sent twice as two pairs;
    more than `MAX_HEADERS` of them are `OSError(EIO)`."""
    if len(response.headers.raw) > MAX_HEADERS:
        raise OSError(_errno.EIO, f"the response has more than {MAX_HEADERS} headers")
    return [
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in response.headers.raw
    ]


def _find(error: BaseException, kind: type) -> "BaseException | None":
    """An exception of `kind` among the causes of `error`."""
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, kind):
            return current
        pending.extend(
            nxt
            for nxt in (current.__cause__, current.__context__, *current.args)
            if isinstance(nxt, BaseException)
        )
    return None


def failure(error: BaseException) -> BaseException:
    """`error`, raised by `httpx` or by what it reads, as the exception a
    transport raises: `TimeoutError`, `ConnectionError`, `ssl.SSLError`,
    `ValueError` or `OSError(EIO)`. What `httpx` says, which can quote a URL,
    is not passed on."""
    httpx = import_httpx()
    if isinstance(error, httpx.TimeoutException):
        return TimeoutError(_errno.ETIMEDOUT, "the request timed out")
    sslerror = _find(error, _ssl.SSLError)
    if sslerror is not None:
        return sslerror
    if isinstance(error, httpx.RemoteProtocolError) and str(error).startswith(
        "Server disconnected"
    ):
        return ConnectionError("the server closed the connection without a reply")
    if isinstance(error, httpx.ProtocolError):
        return OSError(_errno.EIO, "the response is not valid HTTP")
    if isinstance(error, (httpx.NetworkError, httpx.ProxyError)):
        return ConnectionError(f"connection failed ({type(error).__name__})")
    if isinstance(error, httpx.InvalidURL):
        # The URLs of a request were checked, so this is the `Location` of a
        # reply, read by a client that was given to the transport.
        return OSError(_errno.EIO, "the redirect of the reply names no usable URL")
    if isinstance(error, httpx.UnsupportedProtocol):
        return ValueError(f"the request is not valid ({type(error).__name__})")
    if isinstance(error, (OSError, ValueError, TypeError)) and (
        type(error).__module__ == "builtins"
    ):
        return error
    return OSError(_errno.EIO, f"request failed ({type(error).__name__})")
