"""The tests `pathapi` runs over its own HTTP transports, run over these:
`HTTPClient` and `AsyncHTTPClient` against loopback servers and the transport
contracts against servers scripted at the byte level."""

from __future__ import annotations

import re
import subprocess
import sys

COMMAND = [
    sys.executable,
    "-m",
    "pathapi.http.testing",
    "--http-transports",
    "httpx",
    "--http-async-transports",
    "httpx",
    "-p",
    "no:cacheprovider",
]
COUNTS = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed)")


def _run(*options, timeout):
    return subprocess.run(
        [*COMMAND, *options], capture_output=True, text=True, timeout=timeout
    )


def _counts(output):
    """The counts of the last line of a pytest run, such as
    `{"passed": 190, "skipped": 4}`."""
    lines = [line for line in output.splitlines() if COUNTS.search(line)]
    return (
        {word: int(number) for number, word in COUNTS.findall(lines[-1])}
        if lines
        else {}
    )


def test_the_transport_suite_of_pathapi_passes_over_the_httpx_transports():
    result = _run("-q", "-rs", timeout=1800)
    output = result.stdout + result.stderr
    counts = _counts(result.stdout)
    report = (
        f"counts {counts}\n"
        + "\n".join(result.stdout.splitlines()[-40:])
        + result.stderr[-2000:]
    )
    assert result.returncode == 0, report
    assert counts.get("passed", 0) > 0 and "failed" not in counts, report
    assert "non-loopback" not in output, report
    assert "loopback-only guard" not in output, report


def test_the_suite_runs_each_test_that_depends_on_a_transport_once_for_each_half():
    # Node ids are relative to the root directory; on a runner where the suite and
    # the checkout are on different drives they would lose their file part.
    from pathapi.http.testing import suite_directory

    result = _run("--collect-only", "-q", f"--rootdir={suite_directory()}", timeout=600)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    listed = [line for line in result.stdout.splitlines() if "::" in line]
    shown = "\n".join(listed[:5] + ["..."] + listed[-5:]) + result.stderr[-1000:]
    assert any("test_transport_send.py::" in line for line in listed), shown
    assert any("test_async_transport.py::" in line for line in listed), shown
    assert any("test_async_client.py::" in line for line in listed), shown
    kinds = [line.partition("[")[2].rstrip("]").split("-") for line in listed]
    assert sum("httpx" in ids for ids in kinds) > 150
    assert not any("builtin" in ids for ids in kinds)
