from domain.llm.prompt import Prompt, prompt_hash


def test_prompt_hash_stable() -> None:
    assert prompt_hash("hola") == prompt_hash("hola")
    assert prompt_hash("hola") != prompt_hash("adios")


def test_prompt_hash_sha256_hex() -> None:
    h = prompt_hash("x")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_prompt_object_hash_matches_text() -> None:
    p = Prompt(kind="decision", version="v001", text="contenido")
    assert p.hash == prompt_hash("contenido")
