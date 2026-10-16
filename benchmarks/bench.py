"""pathapi-httpx benchmark runner.

Times batches of concurrent requests through `AsyncHTTPClient` with the
thread-backed default transport and with `AsyncHttpxTransport`, and sequential
requests through `HTTPClient` with the built-in transport and with
`HttpxTransport`, against an in-process loopback server. Run
`python benchmarks/bench.py --help` for the options. `--save` writes the run as
JSON into `benchmarks/results/`; the schema is in `benchmarks/README.md`.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import http.server
import json
import os
import platform
import statistics
import subprocess
import sys
import sysconfig
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

SCHEMA = "pathapi-httpx.bench/1"
BODY = b"x" * 1024
DELAY = 0.02
"""Seconds the server holds a request to /slow before it answers (`--delay`)."""


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/slow"):
            time.sleep(DELAY)
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)


class _Server(http.server.ThreadingHTTPServer):
    request_queue_size = 512  # a batch connects all at once


def _summary(per_call, calls):
    per_call = sorted(per_call)
    return {
        "min_ms": round(per_call[0], 6),
        "median_ms": round(statistics.median(per_call), 6),
        "max_ms": round(per_call[-1], 6),
        "samples": len(per_call),
        "calls_per_sample": calls,
    }


def _concurrent(url, samples):
    from pathapi.http import AsyncHTTPClient, get_async_transport

    results = {}
    for count in (50, 200):
        for name, label in (
            ("builtin", "thread-backed default"),
            ("httpx", "AsyncHttpxTransport"),
        ):

            async def batch():
                transport = get_async_transport(name)()
                try:
                    client = AsyncHTTPClient(transport, timeout=(10, 60))

                    async def one(n):
                        reply = await client.request("GET", f"{url}/slow/{n}")
                        return await reply.read()

                    started = time.perf_counter()
                    await asyncio.gather(*(one(n) for n in range(count)))
                    return time.perf_counter() - started
                finally:
                    await transport.aclose()

            taken = [asyncio.run(batch()) / count * 1000.0 for _ in range(samples)]
            case = f"{count} concurrent GETs held {DELAY * 1000:.0f} ms, {label}"
            results[case] = _summary(taken, count)
    return results


def _sequential(url, samples):
    from pathapi.http import HTTPClient, get_transport

    results = {}
    for name in ("builtin", "httpx"):
        transport = get_transport(name)()
        try:
            client = HTTPClient(transport)
            client.request("GET", url + "/small.bin").read()
            taken = []
            for _ in range(samples):
                started = time.perf_counter()
                for _ in range(50):
                    client.request("GET", url + "/small.bin").read()
                taken.append((time.perf_counter() - started) / 50 * 1000.0)
            results[f"50 sequential GETs of a 1 KiB file, {name} transport"] = _summary(
                taken, 50
            )
        finally:
            transport.close()
    return results


def _git():
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return {"commit": commit, "dirty": dirty}


def main(argv=None) -> int:
    global DELAY
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", action="store_true", help="write the run as JSON")
    parser.add_argument("--name", help="file name without .json")
    parser.add_argument(
        "--results-dir", type=Path, default=REPO_ROOT / "benchmarks" / "results"
    )
    parser.add_argument(
        "--samples", type=int, default=5, help="samples per case (1-100)"
    )
    parser.add_argument("--note", help="free text stored in the JSON")
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY,
        help="seconds the server holds a /slow request (default %(default)s)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.samples <= 100:
        parser.error("--samples is between 1 and 100")

    DELAY = args.delay
    import httpx
    import pathapi
    import pathapi_httpx

    server = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        metrics = {
            **_concurrent(url, args.samples),
            **_sequential(url, args.samples),
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    for label, values in metrics.items():
        print(f"{label}: median {values['median_ms']:.3f} ms per call")
    if args.save:
        version = pathapi_httpx.__version__
        python = f"py{sys.version_info.major}.{sys.version_info.minor}"
        system = f"{platform.system().lower()}-{platform.machine().lower()}"
        name = args.name or f"{version}-{python}-{system}"
        document = {
            "schema": SCHEMA,
            "name": name,
            "source": "ci" if "GITHUB_ACTIONS" in os.environ else "local",
            "note": args.note,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "package": {"name": "pathapi-httpx", "version": version},
            "dependencies": {
                "pathapi": pathapi.__version__,
                "httpx": httpx.__version__,
            },
            "git": _git(),
            "python": platform.python_version(),
            "interpreter": platform.python_implementation(),
            "platform": sysconfig.get_platform(),
            "processor": platform.processor() or platform.machine(),
            "metrics": metrics,
        }
        args.results_dir.mkdir(parents=True, exist_ok=True)
        target = args.results_dir / f"{name}.json"
        target.write_bytes((json.dumps(document, indent=2) + "\n").encode("utf-8"))
        print("wrote", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
