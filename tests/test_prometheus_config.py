from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((ROOT / "compose.yaml").read_text()))


def _prometheus_yml() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((ROOT / "deploy/prometheus.yml").read_text()))


def test_prometheus_scrapes_paper_runner() -> None:
    cfg = _prometheus_yml()
    targets = cfg["scrape_configs"][0]["static_configs"][0]["targets"]
    assert "paper-runner:9090" in targets


def test_prometheus_retention_at_least_45d() -> None:
    compose = _compose()
    cmd = compose["services"]["prometheus"]["command"]
    flag = next(c for c in cmd if "storage.tsdb.retention.time" in c)
    default = flag.split(":-")[-1].rstrip("}")
    days = int(default.rstrip("d"))
    assert days >= 45


def test_prometheus_has_persistent_tsdb_volume() -> None:
    compose = _compose()
    volumes = compose["services"]["prometheus"]["volumes"]
    assert any("promdata:/prometheus" in v for v in volumes)


def test_paper_runner_metrics_port_not_published_publicly() -> None:
    compose = _compose()
    paper = compose["services"]["paper-runner"]
    assert "ports" not in paper


def test_prometheus_port_loopback_only() -> None:
    compose = _compose()
    ports = compose["services"]["prometheus"]["ports"]
    assert ports
    assert all(p.startswith("127.0.0.1:") for p in ports)


def test_paper_runner_does_not_depend_on_prometheus() -> None:
    # Prometheus no disponible NO debe detener el paper-runner.
    compose = _compose()
    paper = compose["services"]["paper-runner"]
    deps = paper.get("depends_on", {})
    assert "prometheus" not in deps
