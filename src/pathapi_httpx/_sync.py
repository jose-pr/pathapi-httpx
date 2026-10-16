"""`httpx.Client` as an HTTP transport for `pathapi.http`."""

from __future__ import annotations

import typing as _ty
import weakref as _weakref

from pathapi.http import HTTPResponse, prepare_request

from ._common import (
    CHUNK,
    Pin,
    build_request,
    failure,
    header_pairs,
    import_httpx,
    owned_client,
    read_already,
    requested_url,
)


class _Body:
    """The raw (still encoded) body of an `httpx` response."""

    def __init__(self, owner, response):
        # The transport stays alive while its reply is open: collecting it
        # would close the client the reply is reading from.
        self._owner = owner
        self._response = response
        self._chunks = response.iter_raw()

    def read(self, amount: int) -> bytes:
        try:
            return next(self._chunks, b"")
        except Exception as error:
            raise failure(error) from None

    def close(self) -> None:
        self._chunks.close()
        self._response.close()


class HttpxTransport:
    """Sends requests with an `httpx.Client`.

    `client` is the client to use (the caller's: `close()` leaves it open), or
    `None` for a new one built from `client_args` (`verify`, `cert`, `http2`,
    `proxy`, `mounts`, `limits`, `trust_env`, `auth`, ...) that `close()`
    closes. `client_args` with a `client` is `TypeError`.

    The transport sends one request and follows no redirect, whatever the
    client says. It sends exactly the headers it is given: the default headers
    and the cookies of a client are not added. The client's `auth` is used for
    the server of the first request only; a request to any other server
    carries just the `Authorization` it was given.

    Failures are `TimeoutError`, `ConnectionError`, `ssl.SSLError`,
    `ValueError` or `OSError(EIO)`; what `httpx` says is never passed on."""

    def __init__(self, client: "_ty.Any" = None, **client_args):
        httpx = self._httpx = import_httpx()
        if client is not None:
            if client_args:
                raise TypeError(
                    "client arguments apply to a client the transport makes"
                )
            if not callable(getattr(client, "send", None)):
                raise TypeError("a client is an object with a send() method")
        self._owns_client = client is None
        if client is None:
            client = owned_client(httpx.Client)(
                **{**client_args, "follow_redirects": False}
            )
            # Without a finalizer a client that is dropped leaves its sockets
            # to the garbage collector.
            self._finalizer = _weakref.finalize(self, client.close)
        self.client = client
        self._pin = Pin()

    def __repr__(self) -> str:
        return "HttpxTransport()"

    def __enter__(self) -> "HttpxTransport":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        """Closes the client if this transport made it, and does so when the
        transport is collected without having been closed. Harmless when
        called again."""
        if self._owns_client:
            self._finalizer.detach()
            self.client.close()

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: "_ty.Mapping[str, str]",
        body: "bytes | _ty.BinaryIO | _ty.Iterable[bytes] | None" = None,
        timeout: "float | tuple | None",
        stream: bool = False,
    ) -> HTTPResponse:
        """One request, one response, as `HTTPTransport.send()`."""
        prepared = prepare_request(
            method, url, headers=headers, body=body, timeout=timeout
        )
        request = build_request(self._httpx, prepared, prepared.body)
        auth = self._pin.auth(prepared, self._httpx.USE_CLIENT_DEFAULT)
        try:
            response = self.client.send(
                request, stream=True, follow_redirects=False, auth=auth
            )
        except Exception as error:
            raise failure(error) from None
        try:
            pairs = header_pairs(response)
        except BaseException:
            response.close()
            raise
        body = read_already(response)
        result = HTTPResponse(
            response.status_code,
            response.reason_phrase,
            pairs,
            requested_url(request),
            body if body is not None else _Body(self, response),
            decode=prepared.decode and body is None,
        )
        return result if stream else result.buffered()
