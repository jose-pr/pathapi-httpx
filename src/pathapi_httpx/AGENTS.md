# `pathapi_httpx` — public API header

Header-file-style reference for the `pathapi_httpx` package: every public
export with its signature, arguments, contract and gotchas, so the package can
be used without reading its source. It ships inside the package and is
self-contained. Development documentation lives with the source at
<https://github.com/jose-pr/pathapi-httpx>.

Names are imported from `pathapi_httpx`, which exports two classes,
`HttpxTransport` and `AsyncHttpxTransport`, and `__version__`. A module or name
that starts with an underscore is private and nothing there is contract.

`pip install pathapi-httpx`. Required dependencies: `pathapi>=0.1.2,<0.2` and
`httpx>=0.28.0,<0.29`. `httpx` is imported when a transport is built, not when
this package is. HTTP/2 needs `h2`: `pip install "httpx[http2]"`.

`pathapi_httpx.__version__` is the version of the installed
distribution, read from its metadata. The rendered documentation is at
<https://jose-pr.github.io/pathapi-httpx/> and the project overview is the
`README.md` shipped next to this file (`pathapi_httpx/README.md`).

## The `httpx` transports (`pathapi_httpx`)

```python
class HttpxTransport:
    client: httpx.Client
    def __init__(self, client=None, **client_args): ...
    def send(
        self, method, url, *, headers, body=None, timeout, stream=False,
    ) -> HTTPResponse: ...
    def close(self) -> None: ...

class AsyncHttpxTransport:
    client: httpx.AsyncClient
    def __init__(self, client=None, **client_args): ...
    async def send(
        self, method, url, *, headers, body=None, timeout, stream=False,
    ) -> AsyncHTTPResponse: ...
    async def aclose(self) -> None: ...
```

`HttpxTransport` is an HTTP transport for `pathapi.http` and
`AsyncHttpxTransport` an async one (the contracts are "The transport contract"
and "The async transport contract" in the `pathapi` header): `send()` makes one
request with an `httpx` client and returns a `pathapi.http.HTTPResponse`, or
for the async one an `AsyncHTTPResponse` read with coroutines. `pathapi.http`
finds them through the `httpx` entries of its `pathapi.http_transports` and
`pathapi.http_async_transports` entry-point groups, which this distribution
declares, so installing the distribution is all that is needed:

- `HTTPClient(HttpxTransport(client))` and
  `AsyncHTTPClient(AsyncHttpxTransport(client))` send every request of the
  client through the `httpx` client. `HTTPClient` and `AsyncHTTPClient` follow
  the redirects and never close a transport they were given.
- `PATHAPI_HTTP_TRANSPORT=httpx` makes every `HTTPClient` that was given no
  transport build `HttpxTransport()`, and `PATHAPI_HTTP_ASYNC_TRANSPORT=httpx`
  every `AsyncHTTPClient` build `AsyncHttpxTransport()`; so do
  `pathapi.http.default_transport()`, `default_async_transport()` and
  `get_transport("httpx")()`, `get_async_transport("httpx")()`.

Use `HttpxTransport` for what the built-in transport does not do: HTTP/2, a
client of your own with its `mounts`, `limits`, proxies and `auth`,
`SSL_CERT_FILE` and the certifi bundle. Use `AsyncHttpxTransport` to send from
an event loop on its own sockets: `ThreadedTransport` (the default async
transport) needs a worker thread for every request that is waiting.

- **`client`** — the `httpx.Client` (`httpx.AsyncClient` for the async
  transport) to send with, an object with a `send()` method (an async one for
  the async transport; `TypeError` otherwise). `None` makes a new one from
  `client_args`. The attribute `client` is the one in use. `close()` (`await
  aclose()`) closes a client this transport made and leaves a caller's open, so
  a client passed in is still usable afterwards; both transports are context
  managers that close (`async with` for the async one). A client the
  synchronous transport made is also closed when the transport is collected;
  the async one must be closed with `aclose()`. A response that is still open
  keeps its transport alive.
- **`client_args`** — keyword arguments of `httpx.Client(...)` /
  `httpx.AsyncClient(...)` for the client the transport makes: `verify` (a
  `bool` or an `ssl.SSLContext`), `cert`, `http2`, `proxy`, `mounts`,
  `transport`, `limits`, `trust_env`, `auth`, ... `client_args` together with a
  `client` is `TypeError`. `follow_redirects` is always `False`, whatever is
  given.
- **`send(method, url, *, headers, body=None, timeout, stream=False)`** is
  `HTTPTransport.send()` (`await send()` of `ThreadedTransport.send()`):
  `ValueError` before anything is sent for what `pathapi.http.prepare_request()`
  refuses, one request and no redirect followed (a client told to
  `follow_redirects` still returns the redirect), the response body read whole
  with `stream=False`. A `timeout` of `(connect, read)` is `httpx.Timeout`'s
  `connect` and `pool`, and `read` and `write`. A body that is a binary file or
  an iterable of `bytes` is read by the async transport on a worker thread.
- **Exactly the headers it is given.** `httpx` adds no `User-Agent`, `Accept`
  or `Connection` and no cookie of the client's jar, and the default headers of
  the client are not sent: `HTTPClient` and `AsyncHTTPClient` decide the headers
  of a request.
- **Credentials belong to one server.** The `auth` of the client is used for
  the server of the first request: its scheme, host and port. A request to any
  other server carries the `Authorization` it was given and nothing the client
  holds. An `auth` of the client wins over an `Authorization` header on that
  first server. Redirects are followed by `HTTPClient`, which drops
  `Authorization` when one leaves the server.
- **Failures** are `TimeoutError`, `ConnectionError`, `ssl.SSLError`,
  `ValueError` (the request was not valid) or `OSError(EIO)` (a reply that is
  not valid HTTP, is cut short or has more than 100 header fields, or a
  `Location` that a client given to the transport cannot read). The text of an
  `httpx` exception, which can quote a URL, is never passed on, and the
  exception is not chained. An exception raised by the request body passes
  through. `repr()` shows nothing of the client or the arguments.

`pathapi_httpx.__version__` is a `str`.

## Checking the transports

`pathapi` ships the tests that hold a transport to the promises of the
built-in ones. With this distribution and `pytest` installed:

```
python -m pathapi.http.testing --http-transports httpx --http-async-transports httpx -q
```

## Environment variables

### `PATHAPI_HTTP_TRANSPORT` and `PATHAPI_HTTP_ASYNC_TRANSPORT`

Read by `pathapi.http`. `httpx` makes an `HTTPClient` (an `AsyncHTTPClient`)
that was given no transport build `HttpxTransport()` (`AsyncHttpxTransport()`).
The name is case-sensitive, and one that no installed distribution declares is
`ValueError` naming the choices.

### `httpx` variables

A client the transport makes has `trust_env=True`, so `httpx` reads
`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and `NO_PROXY`, and `SSL_CERT_FILE`
and `SSL_CERT_DIR` (unless `verify=` is given). Pass `trust_env=False` to
ignore them.

## Gotchas

`HttpxTransport()` builds an `httpx.Client` the moment it is constructed; a
client it made is closed by `close()`, by leaving a `with` block, and when the
transport is collected, so a transport you build is yours to close. An
`HTTPClient` closes only a transport it built itself, which is why
`HTTPClient(HttpxTransport(client))` does not close one.

An `httpx.AsyncClient` keeps its connections on the event loop that first sent
with it: an `AsyncHttpxTransport` is used from one loop, and a transport for
another `asyncio.run()` is a new one.

A client given to the transport that is mounted on `httpx.MockTransport` works:
its replies are read whole already, and `send()` returns them as they are.
