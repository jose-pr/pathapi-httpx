# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `pathapi_httpx.HttpxTransport` and `pathapi_httpx.AsyncHttpxTransport`, the
  HTTP transports of `pathapi.http` over `httpx.Client` and `httpx.AsyncClient`,
  and `pathapi_httpx.__version__`. They need Python 3.9 or newer,
  `pathapi>=0.1.2,<0.2` and `httpx>=0.28.0,<0.29`.
- The distribution declares the `httpx` entry of the `pathapi.http_transports`
  and of the `pathapi.http_async_transports` groups. Installing it is all that
  `pathapi.http` needs to send through them:
  `HTTPClient(HttpxTransport(client))`, `AsyncHTTPClient(AsyncHttpxTransport())`,
  `PATHAPI_HTTP_TRANSPORT=httpx` and `PATHAPI_HTTP_ASYNC_TRANSPORT=httpx` use
  them, `pathapi.http.get_transport("httpx")` and
  `pathapi.http.get_async_transport("httpx")` load them, and
  `pathapi.http.transport_names()` and `async_transport_names()` list them.
- The tests `pathapi` runs over its own transports run over these
  (`python -m pathapi.http.testing --http-transports httpx --http-async-transports httpx`)
  as part of the test suite.

[Unreleased]: https://github.com/jose-pr/pathapi-httpx/commits/main
