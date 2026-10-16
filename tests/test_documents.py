"""The documents against the code: the README examples run, the header's stub
is the class as it is, every public name is documented, and no document tells
the history of the package (the changelog is where a change is recorded)."""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import pytest

import pathapi_httpx
from pathapi_httpx import AsyncHttpxTransport, HttpxTransport
from transport_wire import Wire

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = pathlib.Path(pathapi_httpx.__file__).resolve().parent
HEADER = PACKAGE / "AGENTS.md"
README = REPO / "README.md"
DOCUMENTS = [
    README,
    HEADER,
    REPO / "docs" / "index.md",
    *sorted((REPO / "docs").rglob("api/*.md")),
]
HISTORY = re.compile(
    r"\b(previously|formerly|no longer|used to|as before|was changed|"
    r"now returns|now raises|renamed from)\b",
    re.IGNORECASE,
)


def _blocks(path, language="python"):
    text = path.read_text(encoding="utf-8")
    return re.findall(rf"```{language}\n(.*?)```", text, flags=re.DOTALL)


def test_the_readme_examples_run_against_a_loopback_server():
    blocks = _blocks(README)
    assert len(blocks) == 2
    with Wire() as wire:
        for block in blocks:
            code = block.replace("files.example.org", f"127.0.0.1:{wire.port}")
            exec(compile(code, str(README), "exec"), {"__name__": "__readme__"})
    assert sorted(r.target for r in wire.requests) == [
        "/reports/mon.txt",
        "/reports/today.txt",
        "/reports/tue.txt",
        "/reports/wed.txt",
    ]


def _stub(name):
    (block,) = [b for b in _blocks(HEADER) if f"class {name}" in b]
    return next(
        n
        for n in ast.parse(block).body
        if isinstance(n, ast.ClassDef) and n.name == name
    )


def _parameters(arguments):
    names = [a.arg for a in arguments.posonlyargs + arguments.args]
    names += [f"*{arguments.vararg.arg}"] if arguments.vararg else []
    names += [f"{a.arg}:kw" for a in arguments.kwonlyargs]
    names += [f"**{arguments.kwarg.arg}"] if arguments.kwarg else []
    return names


def _real(function):
    names = []
    for parameter in inspect.signature(function).parameters.values():
        if parameter.kind is parameter.VAR_POSITIONAL:
            names.append(f"*{parameter.name}")
        elif parameter.kind is parameter.KEYWORD_ONLY:
            names.append(f"{parameter.name}:kw")
        elif parameter.kind is parameter.VAR_KEYWORD:
            names.append(f"**{parameter.name}")
        else:
            names.append(parameter.name)
    return names


@pytest.mark.parametrize(
    "cls, methods",
    [
        (HttpxTransport, {"__init__", "send", "close"}),
        (AsyncHttpxTransport, {"__init__", "send", "aclose"}),
    ],
)
def test_the_header_stub_is_the_class_as_it_is(cls, methods):
    stub = _stub(cls.__name__)
    found = {
        n.name: n
        for n in stub.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert set(found) == methods
    for name, node in found.items():
        assert _parameters(node.args) == _real(getattr(cls, name)), name
        is_async = inspect.iscoroutinefunction(getattr(cls, name))
        assert isinstance(node, ast.AsyncFunctionDef) == is_async, name
    assert any(
        isinstance(n, ast.AnnAssign) and n.target.id == "client" for n in stub.body
    )


def test_every_public_name_is_in_the_header_the_readme_and_an_api_page():
    api = "\n".join(
        p.read_text(encoding="utf-8") for p in DOCUMENTS if "api" in p.parts
    )
    for name in pathapi_httpx.__all__:
        for label, text in (
            ("header", HEADER.read_text(encoding="utf-8")),
            ("README", README.read_text(encoding="utf-8")),
        ):
            assert re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text), (label, name)
        if name != "__version__":
            assert f"pathapi_httpx.{name}" in api, name


def test_the_package_exports_the_two_classes_and_the_version_only():
    assert pathapi_httpx.__all__ == [
        "AsyncHttpxTransport",
        "HttpxTransport",
        "__version__",
    ]


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_a_document_describes_the_package_as_it_is(document):
    text = document.read_text(encoding="utf-8")
    assert HISTORY.findall(text) == []


def test_the_header_links_only_to_absolute_urls():
    text = HEADER.read_text(encoding="utf-8")
    assert re.findall(r"\]\((?!https?://)[^)]*\)", text) == []
    for private in ("CHANGELOG.md", "docs/", "src/pathapi_httpx"):
        assert private not in text


def test_the_header_opens_as_the_standard_says():
    text = HEADER.read_text(encoding="utf-8")
    assert text.startswith("# `pathapi_httpx` — public API header\n")
    opening = text.split("\n\n")[1]
    assert "ships inside the package" in opening and "self-contained" in opening
    assert "<https://github.com/jose-pr/pathapi-httpx>" in opening


def test_the_readme_has_the_standard_sections_in_order():
    headings = re.findall(r"^## (.*)$", README.read_text(encoding="utf-8"), re.M)
    assert headings == [
        "Features",
        "Installation",
        "Quick start",
        "API overview",
        "Development",
        "License",
    ]


def test_the_example_runs_and_prints_what_it_fetched():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO / "examples" / "async_client.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "contents of /a.txt",
        "contents of /b.txt",
        "contents of /c.txt",
    ]
