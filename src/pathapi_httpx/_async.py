"""`httpx.AsyncClient` as an async HTTP transport for `pathapi.http`."""

from __future__ import annotations

import asyncio as _asyncio
import inspect as _inspect
import typing as _ty

from pathapi.http import AsyncHTTPResponse, prepare_request

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

_END = object()


async def _pieces(body) -> "_ty.AsyncIterator[bytes]":
    """A file or an iterable of bytes as an async iterator, each read made on a
    worker thread so that it cannot block the loop."""
    if hasattr(body, "read"):
        while True:
            chunk = await _asyncio.to_thread(body.read, CHUNK)
            if not chunk:
                return
            yield chunk
    else:
        pieces = iter(body)
        while True:
            chunk = await _asyncio.to_thread(next, pieces, _END)
            if chunk is _END:
                return
            yield chunk


class _Body:
    """The raw (still encoded) body of an `httpx` response."""

    def __init__(self, owner, response):
        self._owner = owner
        self._response = response
        self._chunks = response.aiter_raw()

    async def read(self, amount: int) -> bytes:
        try:
            return await self._chunks.__anext__()
        except StopAsyncIteration:
            return b""
        except Exception as error:
            raise failure(error) from None

    async def aclose(self) -> None:
        await self._chunks.aclose()
        await self._response.aclose()


class AsyncHttpxTransport:
    """Sends requests with an `httpx.AsyncClient`, on the event loop that
    awaits them.

    `client` is the client to use (the caller's: `aclose()` leaves it open), or
    `None` for a new one built from `client_args` (`verify`, `cert`, `http2`,
    `proxy`, `mounts`, `limits`, `trust_env`, `auth`, ...) that `aclose()`
    closes. `client_args` with a `client` is `TypeError`. Like any
    `httpx.AsyncClient`, it keeps connections of the loop it first sent on.

    The transport sends one request and follows no redirect, whatever the
    client says. It sends exactly the headers it is given: the default headers
    and the cookies of a client are not added. The client's `auth` is used for
    the server of the first request only; a request to any other server
    carries just the `Authorization` it was given. A request body that is a
    file or an iterable is read on a worker thread.

    Failures are `TimeoutError`, `ConnectionError`, `ssl.SSLError`,
    `ValueError` or `OSError(EIO)`; what `httpx` says is never passed on."""

    def __init__(self, client: "_ty.Any" = None, **client_args):
        httpx = self._httpx = import_httpx()
        if client is not None:
            if client_args:
                raise TypeError(
                    "client arguments apply to a client the transport makes"
                )
            if not _inspect.iscoroutinefunction(getattr(client, "send", None)):
                raise TypeError("a client is an object with an async send() method")
        self._owns_client = client is None
        if client is None:
            client = owned_client(httpx.AsyncClient)(
                **{**client_args, "follow_redirects": False}
            )
        self.client = client
        self._pin = Pin()

    def __repr__(self) -> str:
        return "AsyncHttpxTransport()"

    async def __aenter__(self) -> "AsyncHttpxTransport":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Closes the client if this transport made it. Harmless when called
        again."""
        if self._owns_client:
            await self.client.aclose()

    async def send(
        self,
        method: str,
        url: str,
        *,
        headers: "_ty.Mapping[str, str]",
        body: "bytes | _ty.BinaryIO | _ty.Iterable[bytes] | None" = None,
        timeout: "float | tuple | None",
        stream: bool = False,
    ) -> AsyncHTTPResponse:
        """One request, one response, as `ThreadedTransport.send()`."""
        prepared = prepare_request(
            method, url, headers=headers, body=body, timeout=timeout
        )
        content = prepared.body
        if content is not None and not isinstance(content, (bytes, bytearray)):
            content = _pieces(content)
        request = build_request(self._httpx, prepared, content)
        auth = self._pin.auth(prepared, self._httpx.USE_CLIENT_DEFAULT)
        try:
            response = await self.client.send(
                request, stream=True, follow_redirects=False, auth=auth
            )
        except Exception as error:
            raise failure(error) from None
        try:
            pairs = header_pairs(response)
        except BaseException:
            await response.aclose()
            raise
        body = read_already(response)
        result = AsyncHTTPResponse(
            response.status_code,
            response.reason_phrase,
            pairs,
            requested_url(request),
            body if body is not None else _Body(self, response),
            decode=prepared.decode and body is None,
        )
        return result if stream else await result.buffered()
