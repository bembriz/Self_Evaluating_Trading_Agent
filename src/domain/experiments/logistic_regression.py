"""Regresión logística binaria en Python puro (PRD §30). Dominio puro, determinista.

Sin numpy/sklearn (ADR-0004). Entrenamiento por gradient descent batch con pesos
inicializados a cero (determinista, sin aleatoriedad) y regularización L2 opcional.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _sigmoid(z: float) -> float:
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class LogisticRegression:
    def __init__(
        self,
        learning_rate: float = 1.0,
        max_iter: int = 500,
        l2: float = 0.0,
        tol: float = 1e-6,
    ) -> None:
        self._learning_rate = learning_rate
        self._max_iter = max_iter
        self._l2 = l2
        self._tol = tol
        self.weights: list[float] = []
        self.bias: float = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> None:
        n = len(X)
        d = len(X[0]) if n > 0 else 0
        self.weights = [0.0] * d
        self.bias = 0.0
        if n == 0:
            return
        for _ in range(self._max_iter):
            grad_w = [0.0] * d
            grad_b = 0.0
            for xi, yi in zip(X, y, strict=True):
                err = _sigmoid(_dot(self.weights, xi) + self.bias) - yi
                for j in range(d):
                    grad_w[j] += err * xi[j]
                grad_b += err
            for j in range(d):
                grad_w[j] = grad_w[j] / n + self._l2 * self.weights[j]
            grad_b /= n
            max_update = max(
                [abs(self._learning_rate * g) for g in grad_w]
                + [abs(self._learning_rate * grad_b)],
                default=0.0,
            )
            for j in range(d):
                self.weights[j] -= self._learning_rate * grad_w[j]
            self.bias -= self._learning_rate * grad_b
            if max_update < self._tol:
                break

    def predict_proba(self, X: Sequence[Sequence[float]]) -> list[float]:
        if not self.weights:
            return [_sigmoid(self.bias) for _ in X]
        return [_sigmoid(_dot(self.weights, xi) + self.bias) for xi in X]

    def predict(self, X: Sequence[Sequence[float]], threshold: float = 0.5) -> list[int]:
        return [1 if p >= threshold else 0 for p in self.predict_proba(X)]
