"""Almacén de prompts versionados basado en archivos (PRD §37).

`FilePromptStore` lee prompts inmutables desde `base_dir/<kind>/<version>.md`.
El contenido se trata como texto opaco: la integridad la garantiza el hash
SHA-256 del value object `Prompt`.
"""

from __future__ import annotations

from pathlib import Path

from application.ports.llm import PromptNotFound
from domain.llm.prompt import Prompt


class FilePromptStore:
    """Carga prompts versionados desde el sistema de archivos."""

    def __init__(self, base_dir: str | Path = "prompts") -> None:
        self._base_dir = Path(base_dir)

    def load(self, kind: str, version: str) -> Prompt:
        path = self._base_dir / kind / f"{version}.md"
        if not path.is_file():
            raise PromptNotFound(f"Prompt no encontrado: {kind}/{version}")
        text = path.read_text(encoding="utf-8")
        return Prompt(kind=kind, version=version, text=text)
