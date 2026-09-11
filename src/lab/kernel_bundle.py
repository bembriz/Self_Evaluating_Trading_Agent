"""KernelBundle v1 + KernelIdentity (Fase 17B, compute-only).

El KernelBundle cubre el código conductualmente relevante del camino Mode 2
(orquestación PaperRunner incluida). Lista declarativa y versionada: sin
inferencia dinámica de dependencias.

Exclusión crítica: `domain.trading.strategy` NO se incluye completo porque
contiene el `Strategy` Protocol Y `EmaRsiBaseline`; hashearlo entero haría que
un cambio de estrategia concreta moviera KernelIdentity. En su lugar se
hashea únicamente el texto fuente del contrato (`inspect.getsource(Strategy)`).

Desviaciones documentadas vs DESIGN-1B (verificadas en la base de
implementación 64a3ecd; prohibido inventar módulos):
- `domain/time/day.py`: no existe (sin módulo de tiempo en el árbol).
- `application.services.decision_context`: no existe en esta base
  (el contexto de decisión vive inline donde se usa).
- `application.services.regime_confirmation`: no existe en esta base
  (sin tracker de confirmación; `domain.market.regime` sí incluido).
Si aparecen en el futuro, entran vía `KERNEL_BUNDLE_VERSION = 2`.

Sin enforcement en PaperRunner (compute-only, 17B).
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

from lab.experiment_spec import canonical_bytes, sha256_hex
from lab.fingerprints import SourceResolver

KERNEL_BUNDLE_VERSION = 1

KERNEL_BUNDLE_V1_MODULES = (
    "application.services.paper_runner",
    "application.services.paper_engine",
    "application.ports.paper_trading",
    "domain.market.candle",
    "domain.market.stream",
    "domain.market.indicators",
    "domain.market.regime",
    "domain.risk.engine",
    "domain.risk.config",
    "domain.risk.guards",
    "domain.risk.sizing",
    "domain.risk.stops",
    "domain.portfolio.portfolio",
    "domain.trading.decision",
    "domain.trading.signal",
    "domain.trading.fill",
    "domain.trading.fees",
    "domain.trading.slippage",
)

_HEX64_RE = re.compile(r"[0-9a-f]{64}")


def strategy_contract_hash(source_text: str) -> str:
    """Hash del texto fuente del contrato Strategy (no del módulo)."""
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("source_text must be a non-empty str")
    return sha256_hex(source_text.encode("utf-8"))


def real_strategy_contract_source() -> str:
    """Fuente real del `Strategy` Protocol (import perezoso, solo lectura)."""
    from domain.trading.strategy import Strategy

    return inspect.getsource(Strategy)


def kernel_fingerprint(resolver: SourceResolver, contract_source: str) -> str:
    """Fingerprint del kernel: bundle + contrato. Sin estrategia concreta."""
    modules = {
        name: sha256_hex(resolver.get_source(name).encode("utf-8"))
        for name in KERNEL_BUNDLE_V1_MODULES
    }
    payload = {
        "kernel_bundle_version": KERNEL_BUNDLE_VERSION,
        "modules": modules,
        "strategy_contract": strategy_contract_hash(contract_source),
    }
    return sha256_hex(canonical_bytes(payload))


@dataclass(frozen=True)
class KernelIdentity:
    """Identidad del kernel v1 (compute-only). Sin application_git_sha."""

    kernel_bundle_version: int
    kernel_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.kernel_bundle_version, int) or self.kernel_bundle_version < 1:
            raise ValueError("kernel_bundle_version must be a positive int")
        if _HEX64_RE.fullmatch(self.kernel_fingerprint) is None:
            raise ValueError("kernel_fingerprint must be SHA-256 hex")


def make_kernel_identity(resolver: SourceResolver, contract_source: str) -> KernelIdentity:
    """Construye la identidad v1 desde un resolver y el contrato."""
    return KernelIdentity(
        kernel_bundle_version=KERNEL_BUNDLE_VERSION,
        kernel_fingerprint=kernel_fingerprint(resolver, contract_source),
    )
