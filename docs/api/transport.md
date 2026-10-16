# The transports

`HttpxTransport` implements the HTTP transport contract of `pathapi.http`:
`send()` makes one request with an `httpx.Client` and returns an
`HTTPResponse`, and `close()` closes a client the transport made.
`AsyncHttpxTransport` implements the async contract: `await send()` makes one
request with an `httpx.AsyncClient` on the running event loop and returns an
`AsyncHTTPResponse`, and `await aclose()` closes a client the transport made.
`pathapi.http` finds them through the `httpx` entries of its
`pathapi.http_transports` and `pathapi.http_async_transports` entry-point
groups, so `PATHAPI_HTTP_TRANSPORT=httpx`,
`PATHAPI_HTTP_ASYNC_TRANSPORT=httpx`, `pathapi.http.get_transport("httpx")` and
`pathapi.http.get_async_transport("httpx")` name them.

::: pathapi_httpx.HttpxTransport
    options:
      show_if_no_docstring: true
      filters: ["!^_"]

::: pathapi_httpx.AsyncHttpxTransport
    options:
      show_if_no_docstring: true
      filters: ["!^_"]
