# pathapi-httpx — contributor orientation

Orientation for working in a checkout of this repository: layout, environments,
commands, CI and release. It is not the API reference and it does not ship.

| Header | Covers |
| --- | --- |
| [`src/pathapi_httpx/AGENTS.md`](src/pathapi_httpx/AGENTS.md) | The public API: `HttpxTransport`, `AsyncHttpxTransport`, their arguments, what they guarantee and the variables they read. It ships in the wheel, so it stays self-contained (no repo-relative links) and changes in the same commit as any public API change. |

The transport contracts these packages implement (`send()`, `close()` /
`aclose()`, the exceptions, the framing of a body) are documented in the header
of `pathapi`, <https://github.com/jose-pr/pathapi>, and checked by tests that
`pathapi` ships (`python -m pathapi.http.testing`), so the same promises bind
every transport.

## Layout

| Path | Contents |
| --- | --- |
| `src/pathapi_httpx/` | The package (`src/` layout). `py.typed` and the API header ship with it. `__init__.py` exports `HttpxTransport`, `AsyncHttpxTransport` and `__version__`; the classes are in `_sync.py` and `_async.py`, what they share (request building, error mapping, the first-server rule for credentials) in `_common.py`. |
| `pyproject.toml` | The `httpx` entries of the `pathapi.http_transports` and `pathapi.http_async_transports` groups, which is how `pathapi.http` finds the classes; the dependency ranges. |
| `tests/` | The pytest suite. `tests/conftest.py` puts the loopback servers of the transport suite of `pathapi` (`transport_wire`, `transport_guard`) on the path and keeps the run on this machine. `tests/test_transport_suite.py` runs `python -m pathapi.http.testing --http-transports httpx --http-async-transports httpx`. |
| `benchmarks/` | `bench.py` and committed JSON results; see [`benchmarks/README.md`](benchmarks/README.md). Not shipped. |
| `examples/` | Runnable scripts; they start their own loopback server. |
| `docs/`, `mkdocs.yml` | MkDocs site: hand-written pages plus a `mkdocstrings` API reference. |
| `.github/workflows/` | `test.yml`, `release.yml`, `docs.yml`. |
| `CHANGELOG.md` | Keep a Changelog. Released sections are frozen records. |

## Environment

Python 3.9 is the floor (`requires-python = ">=3.9"`) and 3.14 is the latest
supported. Test on both ends before claiming a change works.

Keep one virtualenv per interpreter under `.venv/<version>-<os>-<arch>/`
(gitignored), where `<os>` is `os.name` (`nt`/`posix`) or `darwin`, and `<arch>`
is the architecture the interpreter was built for:

```bash
python -m venv .venv/3.14-posix-x86_64
.venv/3.14-posix-x86_64/bin/python -m pip install -e ".[dev]"
```

On Windows the interpreter is `.venv\<name>\Scripts\python.exe`. `dev` holds the
servers the tests use and the build tools.

`pathapi` 0.1.2 is a dependency. While it is not on PyPI, install it editable
from its checkout first (`pip install -e ../pathapi`), then this package with
`--no-deps`. Edit `pathapi` there and the tests see it at once.

A missing optional library does not fail the suite: its tests are skipped
instead (the TLS tests without `cryptography`), so check `pytest -rs` before
trusting a green run.

## Checks

```bash
python -m pytest -q -rs                              # full suite, the pathapi transport suite included
python -m pytest -q -rs -k "not transport_suite"     # the suite without that run
python -m pathapi.http.testing --http-transports httpx --http-async-transports httpx -q   # that run by itself
python -m black src/ tests/ benchmarks/ examples/    # formatting; --check to verify
mkdocs build --strict                                # docs must build with no warnings
python -m build && python -m twine check dist/*      # sdist + wheel into dist/
```

- **Tests block non-loopback network access** and remove the proxy, CA-bundle
  and `.netrc` settings of the developer's shell (`transport_guard`, from the
  test files `pathapi` ships, applied in `tests/conftest.py`).
  `filterwarnings = error` includes `ResourceWarning`: close what a test opens.
- A test asserts what the server received, not just that no exception was
  raised, and never asserts how fast something happened or how far an
  operation got.
- **The documents are tested**: the README examples run, the header's stubs are
  compared with the code and no document tells the history of the package
  (`tests/test_documents.py`).
- `httpx` follows a redirect's `Location` even for a client told not to: a
  client the transports make overrides `_build_redirect_request`, which is
  private to `httpx`. A change of the `httpx` range needs that method checked
  (`tests/test_httpx_transport.py` fails on a `Location` `httpx` cannot read).

### Benchmarks

`python benchmarks/bench.py --help` lists the options. `--save` writes a JSON
result per (version, interpreter, platform) into `benchmarks/results/`; see
[`benchmarks/README.md`](benchmarks/README.md). A local run is a sanity check;
performance claims in the changelog or release notes come from CI runs
(`test.yml` with `benchmark` set).

### CI

Workflows live in `.github/workflows/`.

- `test.yml` runs on `workflow_dispatch` (inputs: `ref`, `pathapi_ref`,
  `benchmark`) or on a pushed `ci-*` tag, never on ordinary pushes. To test a
  commit without the dashboard, push a uniquely named throwaway tag
  (`ci-<topic>-<timestamp>`), follow the run to completion, then delete the tag
  locally and on the remote. Jobs: `test` (Ubuntu on 3.9 to 3.14, Windows and
  macOS on 3.9 and 3.14), `floors` (every dependency at the lower bound
  `pyproject.toml` declares, on 3.9) and `benchmark` (manual runs only). Change
  a range in `pyproject.toml` only, and name the API that needs a raised floor
  in a comment beside it.
- `release.yml` runs on a `v*` tag: test and `floors` gates, build (the tag must
  name the version built, `twine check`), an installed-wheel smoke test (the
  wheel imports without loading `httpx`, ships its files, is found by
  `pathapi.http` through both entry points and sends a request through each
  transport), a strict docs build, then the GitHub release whose notes come from
  that version's `CHANGELOG.md` section. For a final tag only (no `-` in it) it
  then publishes to PyPI through Trusted Publishing and dispatches `docs.yml` at
  the tag.
- `docs.yml` owns every GitHub Pages deploy: on a push to `main` that touches the
  docs sources and on `workflow_dispatch`, which `release.yml` fires for a final
  tag.
- **Which `pathapi` the jobs install.** Every job that installs the package
  first installs `pathapi` from `git+https://github.com/jose-pr/pathapi@<ref>`
  when a ref is given: the `pathapi_ref` input of a manual run of `test.yml` or
  `docs.yml`, else the repository variable `PATHAPI_REF` (the only source for a
  `ci-*` tag and for `release.yml`). With neither, pip takes the release range
  from PyPI. A ref must hold a version inside the range (`pathapi` 0.1.2 or
  newer, and the floor for the `floors` job). Set the variable while the release
  is not on PyPI (`gh variable set PATHAPI_REF --body <branch-or-sha>`), delete it
  afterwards. `release.yml` refuses a final tag while it is set.

## Conventions

- **Formatting is black**, pinned to `target-version = ["py39"]` so it never
  emits syntax the floor cannot parse. No linter or type checker is enforced.
- **Every file is LF** (`.gitattributes` sets `* text=auto eol=lf`). On Windows,
  black writes CRLF: convert the files back to LF after formatting and check
  `git diff --stat` for whitespace-only churn.
- **3.9 compatibility**: any module using `X | Y` in a runtime-evaluated
  annotation needs `from __future__ import annotations`.
- **Comments** say what the code cannot, in one to three lines, about the code
  as it is: no history, and nothing that refers outside this repository.
- **`*.local.*` files** are per-machine overrides: gitignored and excluded from
  both build targets. Keep hostnames and credentials in those, never in tracked
  files.
- Logical commits in `type: description` form (`feat:`, `fix:`, `docs:`,
  `chore:`); keep code with its tests, and docs, config and CI in separate
  commits. No agent attribution in commit messages: no `Co-Authored-By:` naming
  a model or assistant, no `*-Session:` trailers, no session URLs, no
  "generated with" footers.

## Releasing

1. Move the `[Unreleased]` entries under a new `## [x.y.z] - <date>` heading and
   replace the `[Unreleased]` link definition at the bottom of `CHANGELOG.md`
   with one for the new heading and one for `[Unreleased]` (a comparison from
   the new tag).
2. Bump `version` in `pyproject.toml` in the same commit (PEP 440 syntax there;
   SemVer in tags and the changelog).
3. Before 1.0, bump the minor only when the documented API breaks. New methods,
   new optional arguments and fixes are patch releases.
4. Run the full suite on the floor and latest interpreters, `mkdocs build
   --strict`, `python -m build`, `twine check`, and the maintainer's leak check
   (a scan for private references and agent-attribution commit trailers). Judge
   it by exit code.
5. Push `main`, then the `v*` tag. Publishing is irreversible, so the tag is
   pushed only with the maintainer's explicit consent for that specific
   release. The release the dependency range asks of `pathapi` must be on
   PyPI first, and `PATHAPI_REF` deleted.

Once per repository, before the first release: create it on GitHub; register PyPI
Trusted Publishing for the project `pathapi-httpx` (workflow `release.yml`,
environment `pypi`); set Pages to build from GitHub Actions and allow `v*` tags
in the `github-pages` environment
(`gh api -X POST repos/jose-pr/pathapi-httpx/pages -f build_type=workflow`,
`gh api -X POST repos/jose-pr/pathapi-httpx/environments/github-pages/deployment-branch-policies
-f name='v*' -f type=tag`); and let workflows write (Settings, Actions, General,
Workflow permissions).

Changelog entries say what changed and what a user must do about it. They do
not describe how the work was done.
