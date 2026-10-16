"""The packaging manifest: dependency bounds, the entry point that is how
`pathapi.http` finds the transport, and what the distributions leave out."""

from __future__ import annotations

import importlib.metadata as metadata
import pathlib

import pytest

packaging_requirements = pytest.importorskip("packaging.requirements")

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = pytest.importorskip("tomli")

PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def project():
    if not PYPROJECT.is_file():
        pytest.skip("pyproject.toml is not part of an installed copy")
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _declared_requirements(project):
    specs = list(project["project"].get("dependencies", []))
    for extra, deps in project["project"]["optional-dependencies"].items():
        if extra not in ("dev", "docs"):
            specs += deps
    for spec in specs:
        yield packaging_requirements.Requirement(spec)


def _bounds(requirement):
    operators = {s.operator for s in requirement.specifier}
    return (
        bool(operators & {">=", ">", "==", "~="}),
        bool(operators & {"<", "<=", "==", "~="}),
    )


def test_every_dependency_declares_a_floor(project):
    unbounded = [str(r) for r in _declared_requirements(project) if not _bounds(r)[0]]
    assert unbounded == []


def test_every_dependency_declares_a_ceiling(project):
    unbounded = [str(r) for r in _declared_requirements(project) if not _bounds(r)[1]]
    assert unbounded == []


def test_the_runtime_dependencies_are_pathapi_and_httpx(project):
    names = [
        packaging_requirements.Requirement(spec).name
        for spec in project["project"]["dependencies"]
    ]
    assert names == ["pathapi", "httpx"]


def test_the_installed_metadata_requires_pathapi_and_httpx_only():
    try:
        requires = metadata.requires("pathapi-httpx")
    except metadata.PackageNotFoundError:
        pytest.skip("the distribution is not installed")
    names = {
        packaging_requirements.Requirement(spec).name
        for spec in requires or ()
        if "extra ==" not in spec
    }
    assert names == {"pathapi", "httpx"}


def test_the_transports_are_declared_for_pathapi_to_find(project):
    entry_points = project["project"]["entry-points"]
    assert entry_points == {
        "pathapi.http_transports": {"httpx": "pathapi_httpx:HttpxTransport"},
        "pathapi.http_async_transports": {"httpx": "pathapi_httpx:AsyncHttpxTransport"},
    }
    assert "scripts" not in project["project"]


def test_pathapi_is_asked_for_the_release_that_has_the_async_client(project):
    (spec,) = [
        packaging_requirements.Requirement(s)
        for s in project["project"]["dependencies"]
        if s.startswith("pathapi")
    ]
    assert spec.specifier.contains("0.1.2") and not spec.specifier.contains("0.1.1")
    assert not spec.specifier.contains("0.2.0")


def test_httpx_is_asked_for_from_the_floor_of_its_series(project):
    (spec,) = [
        packaging_requirements.Requirement(s)
        for s in project["project"]["dependencies"]
        if s.startswith("httpx")
    ]
    assert spec.specifier.contains("0.28.0") and not spec.specifier.contains("0.27.2")
    assert not spec.specifier.contains("0.29.0")


def test_the_extras_are_the_tools_only(project):
    extras = project["project"]["optional-dependencies"]
    assert set(extras) == {"dev", "docs"}


def test_distributions_leave_out_the_contributor_notes_and_agent_config(project):
    targets = project["tool"]["hatch"]["build"]["targets"]
    sdist = targets["sdist"]["exclude"]
    wheel = targets["wheel"]["exclude"]
    assert "/AGENTS.md" in sdist
    assert "CLAUDE*" in sdist
    assert "CLAUDE*" in wheel
    assert "*.local.*" in sdist and "*.local.*" in wheel
