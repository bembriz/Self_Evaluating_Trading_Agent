import re

import pytest
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


@pytest.mark.parametrize("command", ["download", "verify", "market-worker"])
def test_subcommand_help_exits_zero(command: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize(
    ("command", "target"),
    [
        ("download", "interfaces.cli.download.download"),
        ("verify", "interfaces.cli.download.verify"),
        ("market-worker", "interfaces.cli.market_worker.market_worker"),
    ],
)
def test_subcommand_dispatch_returns_zero(
    monkeypatch: pytest.MonkeyPatch, command: str, target: str
) -> None:
    monkeypatch.setattr(target, lambda argv: 0)
    assert main([command]) == 0


def test_main_dispatches_paper_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, list[str] | None] = {}

    def fake(argv: list[str] | None) -> int:
        called["argv"] = argv
        return 0

    from interfaces.cli import paper_runner as cli_paper_runner

    monkeypatch.setattr(cli_paper_runner, "paper_runner", fake)

    assert main(["paper-runner", "--seconds", "1"]) == 0
    assert called["argv"] == ["--seconds", "1"]
