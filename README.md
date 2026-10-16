# pathapi-httpx

[![Version](https://img.shields.io/pypi/v/pathapi-httpx.svg)](https://pypi.org/project/pathapi-httpx/)
[![Python versions](https://img.shields.io/pypi/pyversions/pathapi-httpx.svg)](https://pypi.org/project/pathapi-httpx/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/jose-pr/pathapi-httpx/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-latest-blue.svg)](https://jose-pr.github.io/pathapi-httpx/)
[![CI](https://img.shields.io/github/actions/workflow/status/jose-pr/pathapi-httpx/test.yml)](https://github.com/jose-pr/pathapi-httpx/actions/workflows/test.yml)

**The `httpx` HTTP transports for [`pathapi`](https://github.com/jose-pr/pathapi).**
`pathapi.http` sends requests with a transport built on the standard library,
and from an event loop with that transport on worker threads. Install this
distribution and `HTTPClient` sends through an `httpx.Client`, and
`AsyncHTTPClient` through an `httpx.AsyncClient` on the caller's loop, with
nothing to configure. It is documented at
<https://jose-pr.github.io/pathapi-httpx/>.

## Features

| You want | Built-in transports | These transports |
| --- | --- | --- |
| Requests from an event loop without a worker thread per request | No: `ThreadedTransport` runs the standard-library transport on threads | Yes: `AsyncHttpxTransport` |
| HTTP/2 | No | Yes: `HttpxTransport(http2=True)` with `httpx[http2]` |
| Your own `httpx.Client` or `httpx.AsyncClient`: mounted transports, limits, proxies, `auth` | No | Yes: `HttpxTransport(client)` |
| `SSL_CERT_FILE`, `SSL_CERT_DIR` and the certifi bundle | The system trust store, or an `ssl_context=` | Yes |
| Proxies from the environment, `proxy=` and `mounts=` | `http://` proxies through a provider | Yes, as `httpx` does them |

- **Credentials belong to one server.** The `auth` of a client is sent to the
  server of the first request and to no other, and the clients of `pathapi.http`
  never take an `Authorization` header to another server on a redirect.
- **Exactly the headers it is given.** A client's default headers and cookies
  are not added: `HTTPClient` and `AsyncHTTPClient` own the headers of a request.
- **No third-party text in an error.** A failure of `httpx` is a
  `TimeoutError`, `ConnectionError`, `ssl.SSLError`, `ValueError` or
  `OSError(EIO)`; what the library says, which can quote a URL, is never passed on.
- **The same promises as the built-in transports.** The tests `pathapi` runs
  over its own transports run over these
  (`python -m pathapi.http.testing --http-transports httpx --http-async-transports httpx`).

## Installation

```bash
pip install pathapi-httpx
```

Requires `pathapi` and `httpx`, which pip installs with it. HTTP/2 needs
`pip install "httpx[http2]"`.

## Quick start

**Send through an `httpx.Client` from threads or a script:**

```python
import httpx
from pathapi.http import HTTPClient
from pathapi_httpx import HttpxTransport

with httpx.Client() as session:
    with HTTPClient(HttpxTransport(session), timeout=(3, 30)) as client:
        reply = client.request("GET", "http://files.example.org/reports/today.txt")
        print(reply.read().decode())
```

The `httpx.Client` stays yours: neither the client nor the transport closes it.

**Send from an event loop** with `httpx.AsyncClient` on that loop:

```python
import asyncio

from pathapi.http import AsyncHTTPClient
from pathapi_httpx import AsyncHttpxTransport


async def main():
    async with AsyncHttpxTransport() as transport:
        async with AsyncHTTPClient(transport) as client:
            replies = await asyncio.gather(
                *(
                    client.request("GET", f"http://files.example.org/reports/{day}.txt")
                    for day in ("mon", "tue", "wed")
                )
            )
            print([len(await reply.read()) for reply in replies])


asyncio.run(main())
```

**Choose them for the whole process.** `PATHAPI_HTTP_TRANSPORT=httpx` and
`PATHAPI_HTTP_ASYNC_TRANSPORT=httpx` make every `HTTPClient` and
`AsyncHTTPClient` that was given no transport send through a new `httpx` client:

```bash
PATHAPI_HTTP_ASYNC_TRANSPORT=httpx python -c "from pathapi.http import AsyncHTTPClient; print(type(AsyncHTTPClient().transport))"
```

## API overview

| Name | Purpose |
| --- | --- |
| `pathapi_httpx.HttpxTransport` | The transport: `send()` and `close()` over an `httpx.Client` |
| `pathapi_httpx.AsyncHttpxTransport` | The async transport: `await send()` and `await aclose()` over an `httpx.AsyncClient` |
| `pathapi_httpx.__version__` | The installed version |

`pathapi.http` finds the classes through the `httpx` entries of its
`pathapi.http_transports` and `pathapi.http_async_transports` entry-point
groups, which this distribution declares. The reference is in the
[API header](https://github.com/jose-pr/pathapi-httpx/blob/main/src/pathapi_httpx/AGENTS.md)
that ships with the package.

## Development

```bash
python -m venv .venv/3.14-posix-x86_64
.venv/3.14-posix-x86_64/bin/python -m pip install -e ".[dev]"
.venv/3.14-posix-x86_64/bin/python -m pytest -q -rs
```

`pathapi` 0.1.2 is a dependency; while it is not on PyPI, install it
editable from its checkout first (`pip install -e ../pathapi`). The test run
includes `python -m pathapi.http.testing --http-transports httpx
--http-async-transports httpx`, the tests `pathapi` runs over its own transports.

### Releasing

This project follows [Semantic Versioning](https://semver.org/) and keeps a
[`CHANGELOG.md`](CHANGELOG.md). Pushing a tag matching `v*` triggers the release
workflow: test gate → build (checking the tag names the version built) → a strict
docs build as a gate → GitHub release → publish. The release workflow never deploys
the docs site itself: for a final release its last job dispatches the docs workflow
at the tag, which owns every Pages deploy.

## License

MIT — see [LICENSE](LICENSE).
