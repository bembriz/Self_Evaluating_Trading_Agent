import re

from pytest import CaptureFixture

from main import main
from version import __version__


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__) is not None


def test_main_returns_zero(capsys: CaptureFixture[str]) -> None:
    assert main() == 0
    out = capsys.readouterr().out
    assert "self-evaluating-trading-agent" in out
    assert __version__ in out
