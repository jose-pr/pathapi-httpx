# pathapi-httpx

The **`httpx` HTTP transports for [`pathapi`](https://jose-pr.github.io/pathapi/)**.
`pathapi.http` sends requests with a transport built on the standard
library, and from an event loop with that transport on worker threads. Install
this distribution and `HTTPClient` sends through an `httpx.Client`, and
`AsyncHTTPClient` through an `httpx.AsyncClient` on the caller's loop, with
nothing to configure.

## Installation

```bash
pip install pathapi-httpx
```

HTTP/2 needs `pip install "httpx[http2]"`.

## 30-second tour

```python
import asyncio

from pathapi.http import AsyncHTTPClient
from pathapi_httpx import AsyncHttpxTransport


async def main():
    async with AsyncHttpxTransport() as transport:
        async with AsyncHTTPClient(transport) as client:
            reply = await client.request(
                "GET", "http://files.example.org/reports/today.txt"
            )
            print((await reply.read()).decode())


asyncio.run(main())
```

`PATHAPI_HTTP_TRANSPORT=httpx` and `PATHAPI_HTTP_ASYNC_TRANSPORT=httpx` make
every `HTTPClient` and `AsyncHTTPClient` that was given no transport send
through a new `httpx` client.

## Learn more

- [The transports](api/transport.md): `HttpxTransport` and `AsyncHttpxTransport`, their arguments and what they guarantee.
- [Benchmarks](benchmarks.md): concurrent requests through the thread-backed default and `AsyncHttpxTransport` on loopback.
- [Changelog](changelog.md)
