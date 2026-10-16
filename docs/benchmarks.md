# Benchmarks

`benchmarks/bench.py` times a batch of concurrent requests through
`AsyncHTTPClient` against a loopback server that answers each request after a
fixed delay: with `ThreadedTransport`, the default, which waits for each reply
on a worker thread, and with `AsyncHttpxTransport`, which waits on the event
loop. It also times `HTTPClient` with `HttpxTransport` and the built-in
transport on the same sequential requests.

```bash
python benchmarks/bench.py            # run the benchmarks
python benchmarks/bench.py --help     # options; runs nothing
python benchmarks/bench.py --save     # also write benchmarks/results/<name>.json
```

Compare two runs on their medians, and only between runs from the same machine
and interpreter. The result schema is described in
[`benchmarks/README.md`](https://github.com/jose-pr/pathapi-httpx/blob/main/benchmarks/README.md).
A run on a developer machine is a sanity check; performance claims come from CI
runs.
