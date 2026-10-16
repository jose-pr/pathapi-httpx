"""Fetch several files at once from an event loop with `AsyncHttpxTransport`.

The script starts a small server on the loopback interface, so it needs no
network: an `AsyncHTTPClient` over `AsyncHttpxTransport` sends the requests
together on the running loop, each from the same pool of connections.
"""

from __future__ import annotations

import asyncio
import http.server
import threading

from pathapi.http import AsyncHTTPClient
from pathapi_httpx import AsyncHttpxTransport


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"contents of {self.path}\n".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def main(base: str) -> None:
    async with AsyncHttpxTransport() as transport:
        async with AsyncHTTPClient(transport, timeout=(3, 30)) as client:
            names = ("a.txt", "b.txt", "c.txt")
            replies = await asyncio.gather(
                *(client.request("GET", f"{base}/{name}") for name in names)
            )
            for reply in replies:
                print((await reply.read()).decode(), end="")


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        asyncio.run(main(f"http://127.0.0.1:{server.server_port}"))
    finally:
        server.shutdown()
        server.server_close()
