"""Keeps the test run on this machine and independent of it, and puts the
loopback servers of the `pathapi` transport suite within reach.

Every connection that is not to the loopback interface raises, and the proxy,
CA-bundle and `.netrc` settings of the developer's shell are not there to be
read."""

from __future__ import annotations

import sys
import tempfile

import pytest

from pathapi.http.testing import suite_directory

# `transport_wire` (loopback servers scripted at the byte level) and
# `transport_guard`.
sys.path.insert(0, str(suite_directory()))

import transport_guard  # noqa: E402


def pytest_configure(config):
    home = tempfile.TemporaryDirectory(prefix="pathapi-httpx-home-")
    patch = pytest.MonkeyPatch()
    transport_guard.isolate_environment(patch, home.name)
    config.add_cleanup(home.cleanup)
    config.add_cleanup(patch.undo)


_ENV_BEFORE = pytest.StashKey[dict]()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    item.stash[_ENV_BEFORE] = transport_guard.environment_snapshot()
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    result = yield
    before = item.stash.get(_ENV_BEFORE, None)
    changed = (
        transport_guard.changed_variables(
            before, transport_guard.environment_snapshot()
        )
        if before is not None
        else {}
    )
    if changed:
        transport_guard.restore_environment(before)
        raise AssertionError(
            "the test left the process environment changed (use monkeypatch): "
            + ", ".join(f"{k}: {old!r} -> {new!r}" for k, (old, new) in changed.items())
        )
    return result


@pytest.fixture(autouse=True)
def _block_non_loopback_network(monkeypatch):
    blocked = []
    transport_guard.install_network_guard(monkeypatch, blocked)
    yield blocked
    if blocked:
        pytest.fail(f"non-loopback network access attempted: {blocked}")


@pytest.fixture
def transport():
    """An `HttpxTransport` on a new client, closed after the test."""
    from pathapi_httpx import HttpxTransport

    with HttpxTransport() as made:
        yield made


@pytest.fixture
def run_async():
    """Runs a coroutine on a new event loop with an `AsyncHttpxTransport`,
    closes the transport and returns what the coroutine returned."""
    import asyncio

    from pathapi_httpx import AsyncHttpxTransport

    def run(scenario, **client_args):
        async def main():
            async with AsyncHttpxTransport(**client_args) as made:
                return await scenario(made)

        return asyncio.run(main())

    return run
