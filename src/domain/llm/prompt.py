"""Prompt versionado (PRD §37): value object inmutable con hash de contenido.

El ``hash`` es el SHA-256 del texto y sirve para detectar cambios silenciosos de
prompt: cualquier modificación del texto produce un hash distinto.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def prompt_hash(text: str) -> str:
    """Hash SHA-256 (hex, 64 caracteres) del texto del prompt."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Prompt:
    """Prompt inmutable con ``kind``, ``version`` y ``text``."""

    kind: str
    version: str
    text: str

    @property
    def hash(self) -> str:
        """Hash SHA-256 del ``text``."""
        return prompt_hash(self.text)
