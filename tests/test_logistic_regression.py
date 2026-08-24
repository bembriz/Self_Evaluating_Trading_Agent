import pytest

from domain.experiments.logistic_regression import LogisticRegression


def test_linearly_separable_reaches_perfect_accuracy() -> None:
    X = [[-2.0], [-1.0], [-0.5], [0.5], [1.0], [2.0]]
    y = [0, 0, 0, 1, 1, 1]
    model = LogisticRegression(learning_rate=1.0, max_iter=2000)
    model.fit(X, y)
    assert model.predict(X) == y


def test_predict_proba_in_unit_interval() -> None:
    X = [[-2.0], [0.0], [2.0]]
    y = [0, 0, 1]
    model = LogisticRegression()
    model.fit(X, y)
    probas = model.predict_proba(X)
    assert all(0.0 <= p <= 1.0 for p in probas)
    assert probas[2] > probas[0]


def test_deterministic_two_fits_identical() -> None:
    X = [[i * 0.1, (i % 3) * 0.5] for i in range(40)]
    y = [1 if i % 2 == 0 else 0 for i in range(40)]
    m1 = LogisticRegression()
    m2 = LogisticRegression()
    m1.fit(X, y)
    m2.fit(X, y)
    assert m1.weights == m2.weights
    assert m1.bias == m2.bias


def test_l2_reduces_weight_norm() -> None:
    X = [[-1.0], [1.0], [2.0], [-2.0]]
    y = [0, 1, 1, 0]
    plain = LogisticRegression(l2=0.0, max_iter=3000)
    regularized = LogisticRegression(l2=0.5, max_iter=3000)
    plain.fit(X, y)
    regularized.fit(X, y)
    assert sum(w * w for w in regularized.weights) < sum(w * w for w in plain.weights)


def test_predict_respects_threshold() -> None:
    X = [[-2.0], [-1.0], [1.0], [2.0]]
    y = [0, 0, 1, 1]
    model = LogisticRegression()
    model.fit(X, y)
    probas = model.predict_proba(X)
    assert model.predict(X, threshold=0.9) == [1 if p >= 0.9 else 0 for p in probas]


def test_empty_fit_returns_uniform_proba() -> None:
    model = LogisticRegression()
    model.fit([], [])
    assert model.predict_proba([[1.0, 2.0]]) == pytest.approx([0.5])
