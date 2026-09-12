"""Máquina mínima de promoción hasta HOLDOUT_READY (Fase 17G, MVP-A).

Promueve según EVIDENCIA, no según fases de software: INFRASTRUCTURE_PASS
(17F implementado) no implica STRATEGY_PROMOTION_PASS (edge demostrado).

Estados: DRAFT → PARITY_PASSED → ROBUSTNESS_PASSED → HOLDOUT_READY.
HOLDOUT_PASSED / RELEASE_CANDIDATE / PAPER_APPROVED requieren MVP-B y se
rechazan explícitamente. HOLDOUT_READY no consume el holdout (sigue PRISTINE).

Persistencia file-first: ``<root>/<strategy_identity>.state.json`` con hash
de integridad; historial append-only; manipulación falla cerrado.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, NoReturn

from lab.experiment_spec import canonical_bytes, sha256_hex

DRAFT = "DRAFT"
PARITY_PASSED = "PARITY_PASSED"
ROBUSTNESS_PASSED = "ROBUSTNESS_PASSED"
HOLDOUT_READY = "HOLDOUT_READY"

POST_MVP_A_STATES = ("HOLDOUT_PASSED", "RELEASE_CANDIDATE", "PAPER_APPROVED")

_HEX64_RE = re.compile(r"[0-9a-f]{64}")


class PromotionRejected(ValueError):
    """Transición rechazada (salto, evidencia insuficiente o estado final)."""


class UnsupportedStateError(ValueError):
    """Estado posterior a MVP-A: requiere MVP-B / post-certification."""


class StateTamperedError(ValueError):
    """Archivo de promoción manipulado o corrupto."""


@dataclass(frozen=True, slots=True)
class ParityEvidence:
    """Evidencia mínima DRAFT → PARITY_PASSED (research nunca promociona)."""

    runtime_parity: bool
    double_run_reproducibility: bool


@dataclass(frozen=True, slots=True)
class RobustnessEvidence:
    """Evidencia PARITY_PASSED → ROBUSTNESS_PASSED (solo candidatos con edge)."""

    profitable_windows: int
    losing_windows: int
    expectancy: float | None
    robustness_interpretation: str
    edge_present: bool
    promotable: bool


@dataclass(frozen=True, slots=True)
class HoldoutReadinessEvidence:
    """Evidencia ROBUSTNESS_PASSED → HOLDOUT_READY (no consume el holdout)."""

    spec_id: str
    strategy_identity: str
    kernel_fingerprint: str
    split_version: int
    holdout_state: str
    human_approved: bool
    approver: str


def _require_hex(name: str, value: str) -> None:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be SHA-256 hex")


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """Un apunte append-only del historial (transición o nota de research)."""

    origin: str
    target: str
    timestamp: str
    evidence: str
    reason: str


def _seal(body: dict[str, Any]) -> str:
    return sha256_hex(canonical_bytes(body))


class Promotion:
    """Promoción inmutable con persistencia file-first y hash de integridad."""

    def __init__(
        self,
        root: Path,
        strategy_identity: str,
        spec_id_value: str,
        state: str,
        history: tuple[HistoryEntry, ...],
    ) -> None:
        self._root = root
        self._strategy_identity = strategy_identity
        self._spec_id = spec_id_value
        self._state = state
        self._history = history

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> tuple[HistoryEntry, ...]:
        return self._history

    @property
    def strategy_identity(self) -> str:
        return self._strategy_identity

    @property
    def spec_id(self) -> str:
        return self._spec_id

    def _path(self) -> Path:
        return self._root / f"{self._strategy_identity}.state.json"

    def _body(self) -> dict[str, Any]:
        return {
            "strategy_identity": self._strategy_identity,
            "current_state": self._state,
            "spec_id": self._spec_id,
            "history": [asdict(entry) for entry in self._history],
        }

    def _persist(self) -> None:
        body = self._body()
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({**body, "state_hash": _seal(body)}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def create(
        cls, root: Path | str, *, strategy_identity: str, spec_id_value: str, timestamp: str
    ) -> Promotion:
        """Nueva promoción en DRAFT (falla si ya existe)."""
        _require_hex("strategy_identity", strategy_identity)
        _require_hex("spec_id", spec_id_value)
        path = Path(root) / f"{strategy_identity}.state.json"
        if path.is_file():
            raise PromotionRejected(f"PROMOTION_EXISTS: {strategy_identity}")
        promotion = cls(Path(root), strategy_identity, spec_id_value, DRAFT, ())
        promotion._persist()
        return promotion

    @classmethod
    def load(cls, root: Path | str, strategy_identity: str) -> Promotion:
        """Carga verificando el hash de integridad (fail closed)."""
        _require_hex("strategy_identity", strategy_identity)
        path = Path(root) / f"{strategy_identity}.state.json"
        if not path.is_file():
            raise FileNotFoundError(f"promoción desconocida: {strategy_identity}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        body = {
            key: payload[key]
            for key in ("strategy_identity", "current_state", "spec_id", "history")
        }
        if payload.get("state_hash") != _seal(body):
            raise StateTamperedError(f"promoción manipulada: {strategy_identity}")
        history = tuple(HistoryEntry(**entry) for entry in body["history"])
        return cls(
            Path(root), body["strategy_identity"], body["spec_id"], body["current_state"], history
        )

    def _step(self, target: str, *, timestamp: str, evidence: str, reason: str) -> Promotion:
        entry = HistoryEntry(
            origin=self._state,
            target=target,
            timestamp=timestamp,
            evidence=evidence,
            reason=reason,
        )
        stepped = Promotion(
            self._root,
            self._strategy_identity,
            self._spec_id,
            target,
            (*self._history, entry),
        )
        stepped._persist()
        return stepped

    def _demand_state(self, expected: str, target: str) -> None:
        if self._state != expected:
            raise PromotionRejected(f"STATE_JUMP: {self._state} -> {target} not allowed")

    def advance_to_parity(self, evidence: ParityEvidence, *, timestamp: str) -> Promotion:
        """DRAFT → PARITY_PASSED con paridad + reproducibilidad demostradas."""
        self._demand_state(DRAFT, PARITY_PASSED)
        if not evidence.runtime_parity or not evidence.double_run_reproducibility:
            raise PromotionRejected("PARITY_EVIDENCE_INCOMPLETE")
        return self._step(
            PARITY_PASSED,
            timestamp=timestamp,
            evidence=json.dumps(asdict(evidence), sort_keys=True),
            reason="parity evidence complete",
        )

    def advance_to_robustness(self, evidence: RobustnessEvidence, *, timestamp: str) -> Promotion:
        """PARITY_PASSED → ROBUSTNESS_PASSED solo con edge demostrado."""
        self._demand_state(PARITY_PASSED, ROBUSTNESS_PASSED)
        if evidence.robustness_interpretation == "STABLE_NEGATIVE":
            raise PromotionRejected("NEGATIVE_WALK_FORWARD: STABLE_NEGATIVE is rejection")
        if not evidence.edge_present:
            raise PromotionRejected("NO_DEMONSTRATED_EDGE: edge_present is false")
        if not evidence.promotable:
            raise PromotionRejected("NOT_PROMOTABLE: candidate flagged not promotable")
        if evidence.profitable_windows <= 0:
            raise PromotionRejected("NEGATIVE_WALK_FORWARD: no profitable windows")
        if evidence.expectancy is None or evidence.expectancy <= 0:
            raise PromotionRejected("NEGATIVE_WALK_FORWARD: expectancy not positive")
        return self._step(
            ROBUSTNESS_PASSED,
            timestamp=timestamp,
            evidence=json.dumps(asdict(evidence), sort_keys=True),
            reason="robustness evidence shows edge",
        )

    def advance_to_holdout_ready(
        self, evidence: HoldoutReadinessEvidence, *, timestamp: str
    ) -> Promotion:
        """ROBUSTNESS_PASSED → HOLDOUT_READY (no consume el holdout)."""
        self._demand_state(ROBUSTNESS_PASSED, HOLDOUT_READY)
        _require_hex("spec_id", evidence.spec_id)
        _require_hex("strategy_identity", evidence.strategy_identity)
        _require_hex("kernel_fingerprint", evidence.kernel_fingerprint)
        if evidence.split_version != 1:
            raise PromotionRejected(f"SPLIT_MISMATCH: {evidence.split_version}")
        if evidence.holdout_state != "PRISTINE":
            raise PromotionRejected(f"HOLDOUT_NOT_PRISTINE: {evidence.holdout_state}")
        if not evidence.human_approved or not evidence.approver.strip():
            raise PromotionRejected("HUMAN_APPROVAL_REQUIRED")
        return self._step(
            HOLDOUT_READY,
            timestamp=timestamp,
            evidence=json.dumps(asdict(evidence), sort_keys=True),
            reason="candidate frozen for future holdout; holdout untouched",
        )

    def add_research_note(self, note: str, *, timestamp: str) -> Promotion:
        """Nota de research: queda en historial sin cambiar el estado."""
        return self._step(
            self._state,
            timestamp=timestamp,
            evidence=json.dumps({"research_note": note}, sort_keys=True),
            reason="research-note",
        )

    def request_post_mvp_a(self, target: str) -> NoReturn:
        """Estados posteriores a MVP-A: rechazo explícito (requieren MVP-B)."""
        if target in POST_MVP_A_STATES:
            raise UnsupportedStateError(f"{target} requires MVP-B / post-certification")
        raise ValueError(f"unknown promotion state: {target}")
