"""Anti-drift: la version del producto vive en src/version.py y pyproject.toml.

Evita que __version__ (import en runtime) y [project].version (empaquetado/instalacion)
diverjan silenciosamente.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from version import __version__

EXPECTED_VERSION = "0.2.0"

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    pyproject_path = _PROJECT_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        pyproject = tomllib.load(handle)
    return str(pyproject["project"]["version"])


def test_runtime_version_equals_pyproject_version() -> None:
    assert __version__ == _pyproject_version()


def test_runtime_version_is_expected() -> None:
    assert __version__ == EXPECTED_VERSION


def test_pyproject_version_is_expected() -> None:
    assert _pyproject_version() == EXPECTED_VERSION
