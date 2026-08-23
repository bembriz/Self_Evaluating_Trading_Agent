"""Entry point del Self-Evaluating Trading Agent."""

from __future__ import annotations

from version import __version__


def main(argv: list[str] | None = None) -> int:
    """Imprime la identidad y devuelve éxito.

    `argv` queda reservado para subcomandos en fases posteriores.
    """
    del argv
    print(f"self-evaluating-trading-agent {__version__}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
