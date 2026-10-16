# Benchmarks

`bench.py` times, through the clients of `pathapi.http`:

- batches of 50 and 200 concurrent GETs, each held by the server before it
  answers (20 ms by default), through `AsyncHTTPClient` with the thread-backed
  default transport (`ThreadedTransport`) and with `AsyncHttpxTransport`;
- 50 sequential GETs of a 1 KiB file through `HTTPClient` with the built-in
  transport and with `HttpxTransport`.

Nothing here contacts an external host: an in-process loopback server answers.
Each sample of a concurrent case builds its transport and its event loop, so
connection setup is counted.

## Reproduce

From the repository root, in a virtualenv with the package installed:

```bash
python -m pip install -e ".[dev]"
python benchmarks/bench.py --save
```

| Option | Effect |
| --- | --- |
| `--save` | Write the run to `benchmarks/results/<name>.json`. |
| `--name NAME` | File name without `.json`. Default `<version>-py<major.minor>-<os>-<arch>`. |
| `--results-dir DIR` | Write somewhere other than `benchmarks/results/`. |
| `--samples N` | Samples per case (1-100). Default 5. |
| `--delay SECONDS` | How long the server holds a request of the concurrent cases. Default 0.02. |
| `--note TEXT` | Free text stored in the JSON. |

## Comparing runs

Compare on the **median**: one sample's time hides run-to-run noise. Only compare
runs from the same machine and interpreter. A run on a developer machine is a
sanity check; performance claims in the changelog or release notes come from CI
runs (`test.yml` with `benchmark` set).

## Result schema (`pathapi-httpx.bench/1`)

One JSON object per run: `schema`, `name`, `source` (`"ci"` or `"local"`),
`note`, `created_utc`, `package` (`name`, `version`), `dependencies` (`pathapi`,
`httpx`), `git` (`commit`, `dirty`; null outside a checkout), `python`,
`interpreter`, `platform`, `processor`, and `metrics`: per case, `min_ms`,
`median_ms`, `max_ms`, `samples` and `calls_per_sample`, in milliseconds per
call (the wall time of a batch divided by its requests).
