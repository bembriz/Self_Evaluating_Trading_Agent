# Commit Candidate — Fase 17B: identidad de estrategia y kernel

> Para HUMAN 17B GATE. NO staging / NO commit / NO push / NO 17C hasta aprobación.

## Objetivo

Implementar Fase 17B (`implementation-plan-1b`): `ImplementationFingerprint`,
`StrategyArtifactIdentity`, `KernelBundle v1`, `KernelFingerprint`,
`KernelIdentity` — compute-only, sin enforcement en PaperRunner.

## Base

`IMPLEMENTATION_BASE_SHA=64a3ecd`. Certificación Paper 0.2.0 RUNNING, intacta.

## Archivos (solo creados; 0 modificados)

- `src/lab/fingerprints.py` (nuevo: `StrategyDefinition`, `SourceResolver`,
  `ImportlibSourceResolver`, `DictSourceResolver`, `implementation_fingerprint`,
  `strategy_artifact_identity`)
- `src/lab/kernel_bundle.py` (nuevo: `KERNEL_BUNDLE_V1_MODULES` (18),
  `strategy_contract_hash`, `real_strategy_contract_source`,
  `kernel_fingerprint`, `KernelIdentity`, `make_kernel_identity`)
- `tests/lab/test_identity.py` (nuevo: truth table 10 casos + validación +
  spec-integration + goldens + subprocess)
- `docs/phases/17B/evidence/` (unit-tests.log, regression-17A.log,
  coverage.json, global-coverage.log, lint.log, format.log, typing.log,
  identity-values.md, log.md)

## Decisiones de diseño aplicadas (del gate)

- Separación `ImplementationFingerprint` (bundle) vs `StrategyArtifactIdentity`
  (id+versión+api+config+fingerprint); kernel no mueve ninguna de las dos.
- Kernel excluye `domain.trading.strategy` completo; hashea solo el contrato
  vía `inspect.getsource(Strategy)`.
- Bundle de 18 módulos (verificados uno por uno en la base): se omiten
  `domain/time/day`, `application.services.decision_context` y
  `application.services.regime_confirmation` porque NO existen aquí
  (hallazgo del real-integration-check; documentado en código y tests).
- `application_git_sha` en ninguna identidad semántica (solo `ExperimentRun`).
- Todo hashing reusa `canonical_json/sha256_hex` de 17A (cero duplicación).
- `SourceResolver` inyectable: sintéticos en unit tests, importlib en integración.

## Tests

- `tests/lab/test_identity.py`: truth table Casos 1–10, orden/duplicados de
  `sources`, extras por kind (deterministic/ml/llm), resolvers, validación de
  `KernelIdentity`, integración con `ExperimentSpec` (kernel ⇒ SpecId),
  4 goldens sintéticos, determinismo en segundo proceso.
- Totales lab: **132 passed** (86 de 17A intactos → REGRESSION_17A PASS).
- Suite ejecutable global: **546 passed, 1 skipped** (integración/e2e excluidas:
  sin PostgreSQL local, causa ambiental preexistente).

## Cobertura exacta

- `src/lab/fingerprints.py`, `kernel_bundle.py`, `experiment_spec.py`: **100%
  stmts + 100% branches** (total `src/lab`: 269 stmts / 114 ramas).
- Global (set ejecutable): **93.36% ≥ 90%**.

## Calidad

- `ruff check`, `ruff format --check`: PASS. `mypy --strict`: PASS.

## Goldens

Sintéticos e independientes (verificados con stdlib json+hashlib y `sha256sum`
sobre literales, no con las funciones bajo test):
impl `c10cfd54…`, artifact `1360bba4…`, kernel(18) `679db0d2…`,
contract `4914a8f5…`.

## Seguridad

Sin secretos/red; 0 dependencias nuevas (stdlib + `inspect`/`importlib`).
`real_strategy_contract_source` importa el dominio de forma perezosa y solo
lectura. `pyproject.toml` intacto.

## Exact changeset (untracked, sin staging)

`src/lab/fingerprints.py`, `src/lab/kernel_bundle.py`,
`tests/lab/test_identity.py`, `docs/phases/17B/` (+ evidencia).
`git diff --stat` sobre boundary protegido: **vacío** (verificado abajo).
Preexistentes (`harness/state/progress.yaml`, `opencode.json`, resto) fuera.

## Riesgos

Bajo. Código puro compute-only sin consumidores; ningún path de runtime lo
importa. `ImportlibSourceResolver` falla cerrado ante módulos ausentes/sin fuente.

## Mensaje propuesto

```
feat(lab): add strategy and kernel identity fingerprints
```
