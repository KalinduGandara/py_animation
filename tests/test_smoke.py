"""Smoke tests: package layout and tooling wiring (NFR-005)."""

import importlib
import tomllib
from pathlib import Path

import pytest

SUBPACKAGES = ["bouncekit", "bouncekit.world", "bouncekit.render", "bouncekit.export"]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_version_exposed() -> None:
    import bouncekit

    assert isinstance(bouncekit.__version__, str)


def test_entry_point_declared_and_resolvable() -> None:
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text())
    target = data["project"]["scripts"]["bouncekit"]
    assert target == "bouncekit.cli:main"
    module, _, attr = target.partition(":")
    assert callable(getattr(importlib.import_module(module), attr))


def test_import_prints_nothing() -> None:
    import subprocess
    import sys

    out = subprocess.run([sys.executable, "-c", "import bouncekit"],
                         capture_output=True, text=True, check=True)
    assert out.stdout == ""
