from domain.llm.cost import compute_cost


def test_compute_cost_zero_tokens() -> None:
    assert compute_cost(0, 0, 0.27, 1.10) == 0.0


def test_compute_cost_per_million_tokens() -> None:
    assert compute_cost(1_000_000, 0, 0.27, 1.10) == 0.27
    assert compute_cost(0, 1_000_000, 0.27, 1.10) == 1.10
    assert compute_cost(500_000, 500_000, 0.27, 1.10) == 0.135 + 0.55
