# 17B — Identity values reales (evidencia, NO identidades release)

Calculados con `ImportlibSourceResolver` sobre el árbol en
`IMPLEMENTATION_BASE_SHA=64a3ecd`, `uv run python` (stdlib + código del repo,
solo lectura). No persisten como config de runtime; no tocan certificación.

```text
BASELINE_IMPLEMENTATION_FINGERPRINT=aa24cc93f03208c6b9aa55028c0c612458f03dad2389285ae0ee2822bb5ad154
BASELINE_STRATEGY_ARTIFACT_IDENTITY=cb60149d3d1c5495f929884ce5a7f157067c5dd6ae560df43b2a96864b430941
KERNEL_BUNDLE_VERSION=1
CURRENT_KERNEL_FINGERPRINT=4be1a009cac0f4a0e63ce7bc9211c08d5e6c39162adf139259742e7bd48be985
```

Notas:

- Bundle baseline = módulo completo `domain.trading.strategy` (incluye
  `EmaRsiBaseline` + Protocol): correcto como *bundle de estrategia*; el kernel
  lleva solo el hash del contrato (`inspect.getsource(Strategy)`), de modo que
  un cambio en `EmaRsiBaseline` mueve la primera sin mover el segundo.
- KernelBundle v1 = 18 módulos (desviaciones documentadas en `kernel_bundle.py`:
  sin `domain/time/day`, sin `application.services.decision_context`, sin
  `application.services.regime_confirmation`; ninguno existe en esta base).
- Goldens de `tests/lab/test_identity.py` usan fixtures sintéticas y NO dependen
  de estos valores (cambian legítimamente con edits del repo).
