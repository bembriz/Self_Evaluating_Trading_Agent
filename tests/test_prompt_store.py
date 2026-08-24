from pathlib import Path

import pytest

from application.ports.llm import PromptNotFound
from infrastructure.llm.prompts import FilePromptStore


def test_load_prompt_by_kind_and_version(tmp_path: Path) -> None:
    (tmp_path / "decision").mkdir()
    (tmp_path / "decision" / "v001.md").write_text("eres un agente de trading", encoding="utf-8")
    store = FilePromptStore(base_dir=tmp_path)
    p = store.load("decision", "v001")
    assert p.kind == "decision"
    assert p.version == "v001"
    assert p.text == "eres un agente de trading"
    assert len(p.hash) == 64


def test_load_missing_prompt_raises(tmp_path: Path) -> None:
    store = FilePromptStore(base_dir=tmp_path)
    with pytest.raises(PromptNotFound):
        store.load("decision", "v999")
